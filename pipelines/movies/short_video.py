"""
Idea to Short Movie Video Pipeline

End-to-end pipeline that generates a complete short film video (5-20 minutes)
from an idea/premise. Combines story generation, character extraction,
storyboarding, and video production.

Flow:
1. Resolve S3 entities (brand/game/characters) for consistency
2. Generate story and script (Screenwriter + ShortMovieDirector)
3. Extract characters from script OR use S3 characters
4. Generate storyboard frames for each scene (using S3 portraits if available)
5. Generate video clips for each shot
6. Concatenate into final video with audio
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from typing import Optional, Dict, Any, List, Literal

import yaml

from configs.constants.content_constants import CONTENT_FORMAT_LIVE_ACTION, CONTENT_FORMAT_ANIMATED
from langchain.chat_models import init_chat_model

from agents.creative.writing import Screenwriter
from agents.producers.analysis import CharacterExtractor
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.directors.film import ShortMovieDirector
from agents.planners.strategy import IdeationEngine
from agents.producers.visuals import StoryboardArtist
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.media.video import concat_videos
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.viral_extractor import extract_viral_shorts
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from utils.media.image import (
    download_image as _download_image,
    composite_character_on_image,
    composite_multiple_characters,
    composite_prop_on_image,
    composite_multiple_props,
    get_character_position_from_description,
    get_character_scale_from_shot_type,
    get_prop_position_from_description,
    get_prop_scale_from_context,
)
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.checkpoint import CheckpointManager
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene
from interfaces.entities.character_sheet import CharacterView, CharacterExpression


class ShortMovieVideoPipeline:
    """
    Pipeline to generate complete short film videos from an idea.
    
    Unlike short_movie (script only), this pipeline produces actual video output.
    """

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        working_dir: str = ".working_dir/short_video",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
        character_portrait_overrides: Optional[Dict[str, str]] = None,
        global_reference_images: Optional[List[str]] = None,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate
        self.character_portrait_overrides = character_portrait_overrides or {}
        self.global_reference_images = global_reference_images or []

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="short_video",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        # Short film mode for screenwriter (NOT shorts mode - uses full film prompts)
        film_mode = {
            "enabled": True,
            "format": "short_film",  # This uses full film prompts, not viral shorts
            "max_scenes": 15,
            "target_duration_minutes": 15,
        }
        self.screenwriter = Screenwriter(chat_model=self.chat_model, shorts_mode=film_mode, pipeline_kind="short_film")
        self.short_movie_director = ShortMovieDirector(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="short_film")
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="short_film")
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="short_video", run_id=self.run_id, local_dir=self.working_dir)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)

    @classmethod
    def init_from_config(cls, config_path: str):
        """Initialize pipeline from YAML config file."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))

        def _resolve_env(value):
            if not isinstance(value, str):
                return value
            if value.startswith("${") and value.endswith("}"):
                return os.getenv(value[2:-1], "")
            if value.startswith("ENV:"):
                return os.getenv(value[4:], "")
            return value

        def _resolve_path(path_value: Optional[str]) -> Optional[str]:
            if not path_value:
                return None
            return path_value if os.path.isabs(path_value) else os.path.join(base_dir, path_value)

        # Chat model
        chat_model_args = config["chat_model"]["init_args"]
        chat_model_args = {k: _resolve_env(v) for k, v in chat_model_args.items()}
        chat_model = init_chat_model(**chat_model_args)

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)

        # Trend analyzer (optional)
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=_resolve_path(config["working_dir"]) or config["working_dir"],
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
            character_portrait_overrides=config.get("character_portrait_overrides", {}),
            global_reference_images=config.get("global_reference_images", []),
        )

    async def __call__(
        self,
        premise: Optional[str] = None,
        genre: str = "drama",
        target_duration_minutes: int = 15,
        audience: Optional[str] = None,
        style: str = "cinematic",
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        content_format: Literal["live_action", "animated"] = CONTENT_FORMAT_ANIMATED,
        generate_storyboard_images: bool = True,
        generate_videos: bool = True,
        max_scenes: Optional[int] = None,
        restitch_only: bool = False,
        # S3 Entity Integration for character consistency
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete short film video from a premise.

        Args:
            premise: Film premise/logline (optional if auto_ideate=True)
            genre: Film genre (drama, comedy, thriller, action, sci-fi, etc.)
            target_duration_minutes: Target duration (5-20 minutes)
            audience: Target audience (G, PG, teens, adults, family, etc.)
            style: Visual/narrative style
            trendy: Whether to incorporate trending themes
            auto_ideate: If True, automatically generate film premise
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
            content_format: 'live_action' or 'animated'
            generate_storyboard_images: Generate storyboard frames
            generate_videos: Generate video clips for each scene
            max_scenes: Limit number of scenes to process (for testing)
            brand_id: S3 brand ID for character loading (e.g., 'intelli-verse-x')
            game_id: S3 game ID for character loading
            character_names: Specific character names to include from S3

        Returns:
            Dictionary with story, script, characters, scenes, and final video path
        """
        output_json_path = os.path.join(self.working_dir, "shortmovie_video_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate and not restitch_only:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Initialize context
        brand_ctx: Optional[BrandContext] = None
        game_ctx: Optional[GameContext] = None
        
        # ==== PHASE 0: S3 Entity Resolution ====
        self.logger.info("Phase 0: Resolving S3 entities for character consistency...")
        
        s3_characters: Optional[List[CharacterInScene]] = None
        s3_portrait_registry: Optional[Dict] = None
        character_profiles_block = ""
        brand_game_context = ""
        
        # Build tag string for entity resolver
        tag_parts = []
        if brand_id: tag_parts.append(f"@brand:{brand_id}")
        elif brand_hint: tag_parts.append(brand_hint)
        if game_id: tag_parts.append(f"@game:{game_id}")
        if character_names:
            for name in character_names:
                tag_parts.append(f"@character:{name}")
        
        # Resolve S3 entities if any hints provided
        if tag_parts or brand_id or game_id or (auto_ideate and brand_hint):
            resolution = resolve_s3_entities(
                texts=[premise or "", " ".join(tag_parts)],
                brand_hint=brand_id or brand_hint,
                game_hint=game_id,
                working_dir=self.working_dir,
            )
            brand_ctx = resolution.get("brand_context")
            game_ctx = resolution.get("game_context")
            
            if resolution.get("characters"):
                s3_characters = resolution["characters"]
                self.logger.info(f"  Loaded {len(s3_characters)} characters from S3")
            
            if resolution.get("portrait_registry"):
                s3_portrait_registry = resolution["portrait_registry"]
            
            if resolution.get("character_profiles_block"):
                character_profiles_block = resolution["character_profiles_block"]
            
            if resolution.get("context_block"):
                brand_game_context = resolution["context_block"]
            
            # Add S3 reference images to global references
            if resolution.get("reference_images"):
                existing_paths = {item["path"] for item in self.global_reference_images}
                for item in resolution["reference_images"]:
                    if item["path"] not in existing_paths:
                        self.global_reference_images.append(item)

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="film")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating short movie in {ideation_mode} mode...")
            
            if ideation_mode == "brand" and (brand_ctx or game_ctx):
                ideation_result = await self.ideation_engine.ideate_for_brand(
                    content_type="movie",
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                    trend_context=trend_context,
                )
            
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(
                    content_type="movie",
                    mode=ideation_mode,
                    audience=audience or "General",
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            premise = ideation_result.idea
            audience = audience or ideation_result.target_audience
            genre = genre or ideation_result.tone or "drama"
            
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_result.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated short movie premise: {ideation_result.title}")

        if not premise:
            raise ValueError("Either provide a 'premise' or set 'auto_ideate=True'")

        # ==== PHASE 1: Story & Script Generation ====
        self.logger.info("Phase 1: Generating story and script...")
        
        # Initialize variables that may not be set when resuming
        director_brief = None
        trend_context_block = ""
        
        story_path = os.path.join(self.working_dir, "story.txt")
        if os.path.exists(story_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing story: {story_path}")
            with open(story_path, "r", encoding="utf-8") as f:
                story = f.read()
        else:
            # Fetch trends if trendy flag is set
            trend_context: Optional[TrendContext] = None
            trend_context_block = ""
            if trendy and self.trend_analyzer:
                self.logger.info("Fetching real-time trends...")
                trend_context = await self.trend_analyzer.fetch_trends(category="film")
                trend_context_block = trend_context.to_context_block()
                with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                    json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

            format_note = (
                "Content format: ANIMATED. Write for animation: stylized, expressive; imaginative visuals."
                if content_format == CONTENT_FORMAT_ANIMATED
                else "Content format: live-action."
            )
            
            user_requirement = f"""
Genre: {genre}
Style: {style}
Target audience: {audience or 'General'}
Target duration: {target_duration_minutes} minutes
{format_note}
Format: Short film with clear three-act structure
"""
            # Add brand/game context if available
            if brand_game_context:
                user_requirement = f"{user_requirement}\n\n{brand_game_context}"
            
            # Add character profiles for consistent dialogue and behavior
            if character_profiles_block:
                user_requirement = f"{user_requirement}\n\n{character_profiles_block}"
            
            if trend_context_block:
                user_requirement = f"{user_requirement}\n\n{trend_context_block}"

            # Director brief
            director_brief = await self.short_movie_director.direct(
                premise=premise,
                genre=genre,
                target_duration_minutes=target_duration_minutes,
                style=style,
                audience=audience,
                additional_context=f"{format_note}\n{trend_context_block or ''}".strip() or None,
            )
            user_requirement = f"{user_requirement}\n\n{director_brief.to_context_block()}"

            # Director reasoning: ShortMovieDirector creative brief
            write_director_reasoning(
                working_dir=self.working_dir,
                pipeline_name="short_video",
                director_name="ShortMovieDirector",
                rationale=(
                    "ShortMovieDirector sets the creative brief for story, script, and downstream visuals: tone, "
                    "pacing, three-act structure, and style. The brief aligns premise, genre, target_duration, "
                    "format, and audience. S3 character profiles and brand context, when present, steer dialogue "
                    "and behavior. This drives StoryboardArtist and video generation per scene."
                ),
                inputs={
                    "premise": premise[:150],
                    "genre": genre,
                    "target_duration_minutes": target_duration_minutes,
                    "style": style,
                    "audience": audience,
                    "content_format": content_format,
                },
                outputs={"director_brief": "Feeds into user_requirement for Screenwriter and storyboard."},
            )

            # Develop story
            self.logger.info("Developing story...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "story_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Idea: {premise}\nRequirement: {user_requirement}")

            story = await self.screenwriter.develop_story(idea=premise, user_requirement=user_requirement)
            with open(story_path, "w", encoding="utf-8") as f:
                f.write(story)

        # ==== Character Resolution ====
        characters: List[CharacterInScene] = []
        character_portraits_registry: Dict[str, Any] = {}
        is_s3_characters = False
        
        characters_path = os.path.join(self.working_dir, "characters.json")
        registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")

        if os.path.exists(characters_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing characters: {characters_path}")
            with open(characters_path, "r", encoding="utf-8") as f:
                characters_data = json.load(f)
                characters = [CharacterInScene(**c) for c in characters_data]
            
            if os.path.exists(registry_path):
                with open(registry_path, "r", encoding="utf-8") as f:
                    character_portraits_registry = json.load(f)
            
            is_s3_characters = any(c.identifier_in_scene in (character_names or []) for c in characters)
        else:
            if s3_characters:
                # Use S3 characters for consistency across scenes
                self.logger.info(f"Using {len(s3_characters)} S3 characters for consistency...")
                characters = s3_characters
                character_portraits_registry = s3_portrait_registry or {}
                is_s3_characters = True
            else:
                # Extract characters from story
                self.logger.info("Extracting characters from story...")
                characters = await self.character_extractor.extract_characters(story)
            
            with open(characters_path, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)
            
            # ==== Generate Character Portraits for ALL Characters ====
            if characters and self.image_generator:
                char_portraits_dir = os.path.join(self.working_dir, "character_portraits")
                os.makedirs(char_portraits_dir, exist_ok=True)
                
                for char in characters:
                    char_id = char.identifier_in_scene or f"character_{char.idx}"
                    if char_id in character_portraits_registry:
                        continue
                    
                    self.logger.info(f"  Generating portrait for character: {char_id}")
                    char_dir = os.path.join(char_portraits_dir, char_id.replace(" ", "_"))
                    os.makedirs(char_dir, exist_ok=True)
                    
                    front_path = os.path.join(char_dir, "front.png")
                    if not os.path.exists(front_path) or self.force_regenerate:
                        char_desc = f"{char.static_features or ''}"
                        if char.description: char_desc = f"{char_desc}. {char.description}"
                        if char.personality: char_desc = f"{char_desc}. Personality: {char.personality}"
                        
                        portrait_prompt = f"""Character portrait of {char_id}. {char_desc}. 
{style} style, {content_format.replace('_', ' ')}. 
Clean background, full body visible, facing camera, high quality character design sheet.
This is the CANONICAL reference portrait - all future appearances must match this exactly."""
                        
                        try:
                            # Save debug prompt
                            debug_dir = os.path.join(char_dir, "debug")
                            os.makedirs(debug_dir, exist_ok=True)
                            with open(os.path.join(debug_dir, "portrait_prompt.txt"), "w", encoding="utf-8") as f:
                                f.write(portrait_prompt)

                            portrait_output = await self.image_generator.generate_single_image(prompt=portrait_prompt)
                            if portrait_output:
                                portrait_output.save(front_path)
                        except Exception as e:
                            self.logger.warning(f"    Failed to generate portrait for {char_id}: {e}")
                    
                    if os.path.exists(front_path):
                        character_portraits_registry[char_id] = {
                            "front": {"path": front_path, "description": f"Front view portrait of {char_id}"}
                        }
                
                if character_portraits_registry:
                    with open(registry_path, "w", encoding="utf-8") as f:
                        json.dump(character_portraits_registry, f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Script
        script_path = os.path.join(self.working_dir, "script.json")
        if os.path.exists(script_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing script: {script_path}")
            with open(script_path, "r", encoding="utf-8") as f:
                script_scenes = json.load(f)
        else:
            self.logger.info("Writing script...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "script_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Story: {story[:1000]}\nRequirement: {user_requirement}")

            script_scenes = await self.screenwriter.write_script_based_on_story(
                story=story,
                user_requirement=user_requirement,
            )
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script_scenes, f, ensure_ascii=False, indent=2)

        # Limit scenes if requested
        if max_scenes and len(script_scenes) > max_scenes:
            self.logger.info(f"Limiting to {max_scenes} scenes (was {len(script_scenes)})")
            script_scenes = script_scenes[:max_scenes]

        # Phase 1 reasoning: rationale behind the story and script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="short_video",
            phase_label="Phase 1: Story and script",
            content_type="script",
            rationale=(
                "The short film script uses a three-act structure and film-mode screenwriting. ShortMovieDirector "
                "sets the creative brief; Screenwriter develops the story from the premise and writes scene-by-scene. "
                "Characters come from S3 (when brand_id/game_id/character_names are set) for visual consistency, "
                "or from CharacterExtractor. character_profiles_block and brand_game_context steer dialogue and "
                "behavior. Target duration, genre, style, format, and trends shape the narrative. This script "
                "drives storyboard and video generation in later phases."
            ),
            inputs={
                "premise": premise[:200] + "…" if len(premise) > 200 else premise,
                "genre": genre,
                "target_duration_minutes": target_duration_minutes,
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "is_s3_characters": is_s3_characters,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
                "script_scenes_count": len(script_scenes),
            },
            outputs={
                "story.txt": "Developed story from premise.",
                "characters.json": "Characters (from S3 or extracted from story).",
                "script.json": "Scene-by-scene script (and character_portraits_registry.json if S3).",
            },
        )

        # Plan audio requirements for short movie scenes
        audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not self.force_regenerate:
            self.logger.info("Loading existing audio plan...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None:
            self.logger.info("Planning audio requirements for short movie scenes...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert scene scripts to Scene objects for audio planning
                scene_objects = []
                for idx, scene_script in enumerate(script_scenes):
                    scene_obj = Scene(
                        idx=idx,
                        is_last=(idx == len(script_scenes) - 1),
                        environment=EnvironmentInScene(
                            slugline="SHORT MOVIE SCENE",
                            description="Scene from short movie",
                        ),
                        characters=characters,
                        script=scene_script if isinstance(scene_script, str) else str(scene_script),
                    )
                    scene_objects.append(scene_obj)
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,
                    previous_audio_plan=None,
                    style=style,
                    audience=audience,
                    content_format=content_format,
                )
                
                self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                self.logger.info(f"Audio plan created with {len(audio_plan.scene_plans)} scene plans")
            except Exception as e:
                self.logger.warning(f"Failed to create audio plan: {e}. Continuing without detailed audio planning.")
                audio_plan = None
        
        self.audio_plan = audio_plan

        # ==== PHASE 2: Storyboard Generation ====
        scene_outputs = []
        scenes_dir = os.path.join(self.working_dir, "scenes")
        os.makedirs(scenes_dir, exist_ok=True)

        for i, scene_script in enumerate(script_scenes):
            scene_num = i + 1
            scene_dir = os.path.join(scenes_dir, f"scene_{scene_num:02d}")
            os.makedirs(scene_dir, exist_ok=True)
            
            scene_video_path = os.path.join(scene_dir, "scene_video.mp4")
            
            # RESUME CHECK: Scene Video (OR restitch_only)
            if (os.path.exists(scene_video_path) and not self.force_regenerate) or restitch_only:
                if restitch_only and not os.path.exists(scene_video_path):
                    self.logger.warning(f"  Restitch mode: Scene video NOT found at {scene_video_path}. Skipping scene.")
                    continue
                
                self.logger.info(f"  Resuming/Restitching from existing scene video: {scene_video_path}")
                scene_output = {
                    "scene_number": scene_num,
                    "script": scene_script,
                    "storyboard_frames": [os.path.join(scene_dir, f) for f in sorted(os.listdir(scene_dir)) if f.startswith("frame_") and f.endswith(".png") and "_raw" not in f],
                    "video_path": scene_video_path,
                }
                scene_outputs.append(scene_output)
                continue

            self.logger.info(f"Phase 2: Processing scene {scene_num}/{len(script_scenes)}...")
            
            scene_output = {
                "scene_number": scene_num,
                "script": scene_script,
                "storyboard_frames": [],
                "video_path": None,
            }

            # Generate storyboard for this scene
            if generate_storyboard_images and self.image_generator:
                self.logger.info(f"  Generating storyboard for scene {scene_num}...")
                
                try:
                    # Save storyboard design to disk for resumption
                    storyboard_design_path = os.path.join(scene_dir, "storyboard_design.json")
                    if os.path.exists(storyboard_design_path) and not self.force_regenerate:
                        with open(storyboard_design_path, "r", encoding="utf-8") as f:
                            shots_data = json.load(f)
                            # Re-wrap in ShotBriefDescription if necessary, or just use as dict
                            # Assuming storyboard_artist.design_storyboard returns List[ShotBriefDescription]
                            shots = shots_data 
                    else:
                        # Save debug prompt
                        debug_dir = os.path.join(scene_dir, "debug")
                        os.makedirs(debug_dir, exist_ok=True)
                        with open(os.path.join(debug_dir, "storyboard_design_prompt.txt"), "w", encoding="utf-8") as f:
                            f.write(f"Script: {scene_script[:1000]}\nCharacters: {[c.identifier_in_scene for c in characters]}")

                        shots = await self.storyboard_artist.design_storyboard(
                            script=scene_script,
                            characters=characters,
                        )
                        shots = (shots or [])[:10]
                        with open(storyboard_design_path, "w", encoding="utf-8") as f:
                            # Convert pydantic models to dict if needed
                            json.dump([s.model_dump() if hasattr(s, 'model_dump') else s for s in shots], f, indent=2)
                    
                    shot_video_paths = []
                    for j, shot in enumerate(shots):
                        frame_num = j + 1
                        frame_path = os.path.join(scene_dir, f"frame_{frame_num:02d}.png")
                        shot_video_path = os.path.join(scene_dir, f"shot_{frame_num:02d}.mp4")
                        
                        # 1. Generate/Load Frame
                        if not os.path.exists(frame_path) or self.force_regenerate:
                            raw_frame_path = os.path.join(scene_dir, f"frame_{frame_num:02d}_raw.png")
                            frame_prompt = getattr(shot, "visual_desc", None) if hasattr(shot, 'visual_desc') else shot.get("visual_desc", "")
                            if not frame_prompt:
                                frame_prompt = getattr(shot, "visual_description", None) if hasattr(shot, 'visual_description') else shot.get("visual_description", str(shot)[:500])
                            
                            visible_characters: List[CharacterInScene] = []
                            shot_reference_images = list(self.global_reference_images)
                            
                            for c in characters:
                                name = c.identifier_in_scene or ""
                                if not name: continue
                                pattern = rf"(?i)\b({re.escape(name)}|<{re.escape(name)}>)\b"
                                if re.search(pattern, frame_prompt):
                                    visible_characters.append(c)
                            
                            # DEBUG LOGS FOR SHOT
                            char_names = [c.identifier_in_scene for c in visible_characters]
                            self.logger.info(
                                f"\n🎬 [SCENE {scene_num} SHOT {frame_num}] DEBUG INFO:\n"
                                f"   👥 Characters ({len(visible_characters)}): {', '.join(char_names) if char_names else 'None'}\n"
                                f"   ⏱️ Duration: 8s (standard)\n"
                                f"   📝 Visual Plan: {frame_prompt}\n"
                            )

                            # CHARACTER CONSISTENCY FIX:
                            # We follow a dual-track generation process:
                            # 1. BACKGROUND: Clean environment
                            # 2. STORYBOARD: Exact S3 portraits composited on background
                            # 3. RAW: AI-rendered characters "gelled" into scene
                            
                            # Get establishment frame and previous shot reference
                            # Note: scene_script may be a string or dict - handle both
                            default_location = scene_script.get("location", "Default Location") if isinstance(scene_script, dict) else "Default Location"
                            location_name = getattr(shot, "location", default_location)
                            establishment_frame = self.continuity_memory.location_establishment_frames.get(location_name)
                            previous_shot_ref = self.continuity_memory.previous_shot_frame
                            
                            debug_dir = os.path.join(scene_dir, "debug")
                            os.makedirs(debug_dir, exist_ok=True)
                            
                            try:
                                # --- TRACK 1: BACKGROUND GENERATION (Clean Environment) ---
                                bg_visual_desc = frame_prompt
                                if visible_characters:
                                    for char in visible_characters:
                                        bg_visual_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_visual_desc)
                                
                                bg_prompt = f"{bg_visual_desc}. EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures. {style} style, {content_format.replace('_', ' ')}. No text."
                                
                                with open(os.path.join(debug_dir, f"frame_{frame_num:02d}_bg_prompt.txt"), "w", encoding="utf-8") as f:
                                    f.write(bg_prompt)

                                # Use establishment frame or previous shot as reference
                                bg_refs = []
                                if establishment_frame and os.path.exists(establishment_frame):
                                    bg_refs.append(establishment_frame)
                                elif previous_shot_ref and os.path.exists(previous_shot_ref):
                                    bg_refs.append(previous_shot_ref)
                                elif shot_reference_images:
                                    bg_refs.extend(self._resolve_ref_paths(shot_reference_images[:1]))

                                bg_image = await self.image_generator.generate_single_image(
                                    prompt=bg_prompt,
                                    reference_image_paths=bg_refs if bg_refs else None,
                                )
                                if bg_image:
                                    bg_image.save(frame_path)
                                
                                # --- TRACK 2: COMPOSITE CHARACTERS (S3 Portraits) ---
                                if character_portraits_registry and visible_characters:
                                    self._composite_s3_characters_on_frame(
                                        frame_path=frame_path,
                                        visible_characters=visible_characters,
                                        frame_desc=frame_prompt,
                                        character_portraits_registry=character_portraits_registry,
                                    )
                                
                                # --- TRACK 3: RAW GENERATION (Gelled Characters) ---
                                char_desc_parts = []
                                for char in visible_characters:
                                    if char.static_features:
                                        char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
                                char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
                                
                                # Add view and expression guidance
                                view_instruction = ""
                                expression_instruction = ""
                                if visible_characters:
                                    view = get_character_view_for_shot(frame_prompt)
                                    expression = get_character_expression_for_shot(frame_prompt)
                                    view_instruction = f" Camera angle: {view.value} view."
                                    expression_instruction = f" Character expressions: {expression.value}."
                                
                                raw_prompt = f"{frame_prompt}.{char_context}{view_instruction}{expression_instruction} {style} style, {content_format.replace('_', ' ')}. High quality animation frame, vibrant colors, expressive characters gelled into scene. Blend characters naturally into environment. No collages."
                                
                                # Include ALL character portraits (not just 2) for multi-character scenes
                                raw_refs = [frame_path]  # Start with composite frame
                                if character_portraits_registry and visible_characters:
                                    for char in visible_characters:
                                        char_id = char.identifier_in_scene
                                        if char_id in character_portraits_registry:
                                            # Use view/expression selector
                                            view = get_character_view_for_shot(frame_prompt)
                                            expression = get_character_expression_for_shot(frame_prompt)
                                            
                                            # Get portrait with view/expression
                                            path = self._get_portrait_path_with_view(
                                                character_portraits_registry,
                                                char_id,
                                                view,
                                                expression
                                            )
                                            
                                            if path and os.path.exists(path) and path not in raw_refs:
                                                raw_refs.append(path)
                                
                                with open(os.path.join(debug_dir, f"frame_{frame_num:02d}_raw_prompt.txt"), "w", encoding="utf-8") as f:
                                    f.write(raw_prompt)

                                raw_image = await self.image_generator.generate_single_image(
                                    prompt=raw_prompt,
                                    reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                                    strength=0.55,  # Blend with composite
                                )
                                if raw_image:
                                    raw_image.save(raw_frame_path)
                                
                                # Register establishment frame for location
                                if location_name not in self.continuity_memory.location_establishment_frames:
                                    self.continuity_memory.location_establishment_frames[location_name] = raw_frame_path if os.path.exists(raw_frame_path) else frame_path
                                
                                # Update continuity memory
                                visible_char_ids = [c.identifier_in_scene for c in visible_characters]
                                self.continuity_memory.update_for_shot(
                                    shot_idx=frame_num - 1,
                                    frame_path=raw_frame_path if os.path.exists(raw_frame_path) else frame_path,
                                    scene_id=f"scene_{scene_num}",
                                    location=location_name,
                                    visible_characters=visible_char_ids,
                                    visible_props=None,
                                    shot_description=frame_prompt,
                                )
                                
                                scene_output["storyboard_frames"].append(raw_frame_path if os.path.exists(raw_frame_path) else frame_path)
                            except Exception as e:
                                self.logger.warning(f"    Failed to generate frame {frame_num}: {e}")
                        else:
                            scene_output["storyboard_frames"].append(frame_path)

                        # 2. Generate Video for this Shot
                        if generate_videos and self.video_generator and os.path.exists(frame_path):
                            if not os.path.exists(shot_video_path) or self.force_regenerate:
                                raw_frame_path = os.path.join(scene_dir, f"frame_{frame_num:02d}_raw.png")
                                video_ref_frame = raw_frame_path if os.path.exists(raw_frame_path) else frame_path
                                
                                audio_desc = getattr(shot, "audio_desc", "") if hasattr(shot, 'audio_desc') else shot.get("audio_desc", "")
                                visual_desc = getattr(shot, "visual_desc", "") if hasattr(shot, 'visual_desc') else shot.get("visual_desc", "")
                                
                                video_prompt = f"{visual_desc}. {audio_desc}. {style} style, cinematic motion."
                                try:
                                    # Save debug prompt
                                    debug_dir = os.path.join(scene_dir, "debug")
                                    os.makedirs(debug_dir, exist_ok=True)
                                    with open(os.path.join(debug_dir, f"shot_{frame_num:02d}_prompt.txt"), "w", encoding="utf-8") as f:
                                        f.write(video_prompt)

                                    video_output = await self.video_generator.generate_single_video(
                                        prompt=video_prompt,
                                        reference_image_paths=[video_ref_frame],
                                        duration=8,
                                    )
                                    if video_output:
                                        video_output.save(shot_video_path)
                                        shot_video_paths.append(shot_video_path)
                                except Exception as e:
                                    self.logger.warning(f"    Failed to generate video for shot {frame_num}: {e}")
                            else:
                                shot_video_paths.append(shot_video_path)

                    # 3. Concatenate shot videos into scene video
                    if shot_video_paths:
                        try:
                            concat_videos(shot_video_paths, scene_video_path)
                            scene_output["video_path"] = scene_video_path
                        except Exception as e:
                            self.logger.warning(f"  Failed to assemble scene {scene_num} video: {e}")
                            if shot_video_paths: scene_output["video_path"] = shot_video_paths[0]
                
                except Exception as e:
                    self.logger.warning(f"  Storyboard generation failed for scene {scene_num}: {e}")
                    # Fallback Logic: generate a single frame from scene description
                    fallback_path = os.path.join(scene_dir, "frame_01.png")
                    if not os.path.exists(fallback_path) or self.force_regenerate:
                        try:
                            scene_desc = scene_script[:300] if isinstance(scene_script, str) else str(scene_script)[:300]
                            ref_paths = self._resolve_ref_paths(self.global_reference_images)
                            
                            # Clean prompt for fallback
                            fallback_prompt = f"{scene_desc}, {style} style, {content_format.replace('_', ' ')}. Focus on environment. No random background people or robots."
                            
                            image_output = await self.image_generator.generate_single_image(
                                prompt=fallback_prompt,
                                reference_image_paths=ref_paths,
                            )
                            if image_output:
                                image_output.save(fallback_path)
                                # Composite characters that appear in the scene (works for ALL characters)
                                if character_portraits_registry:
                                    fallback_visible = []
                                    # Convert scene_script to string if it's a dict (from write_script_based_on_story)
                                    scene_script_str = scene_script if isinstance(scene_script, str) else json.dumps(scene_script, ensure_ascii=False)
                                    for c in characters:
                                        name = c.identifier_in_scene or ""
                                        if not name: continue
                                        pattern = rf"(?i)\b({re.escape(name)}|<{re.escape(name)}>)\b"
                                        if re.search(pattern, scene_script_str or ""):
                                            fallback_visible.append(c)
                                    
                                    if fallback_visible:
                                        self._composite_s3_characters_on_frame(
                                            frame_path=fallback_path,
                                            visible_characters=fallback_visible,
                                            frame_desc=scene_desc,
                                            character_portraits_registry=character_portraits_registry,
                                        )
                                scene_output["storyboard_frames"].append(fallback_path)
                        except Exception as e2:
                            self.logger.warning(f"    Fallback frame generation failed: {e2}")

            scene_outputs.append(scene_output)

        # Cinematographer/picturization: StoryboardArtist per scene, frame gen from shot.visual_desc, video from motion prompt
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="short_video",
            rationale=(
                "Picturization is per-scene: StoryboardArtist.design_storyboard produces ShotBriefDescription "
                "with visual_desc per shot; frames are generated from visual_desc (plus character appearance "
                "hints and style). Character consistency is ensured through: (1) generating canonical portraits "
                "for ALL characters in character_portraits/ (2) using portraits as reference images (3) post-processing "
                "compositing of portraits onto frames. This works for BOTH S3 characters and newly extracted characters. "
                "Director's style and content_format shape the final look."
            ),
            inputs={
                "style": style,
                "content_format": content_format,
                "is_s3_characters": is_s3_characters,
                "character_count": len(characters),
                "portraits_generated": len(character_portraits_registry),
                "director_guidance": director_brief.to_context_block()[:200] if director_brief else None,
            },
            outputs={
                "character_portraits/*/front.png": "Canonical character portraits for consistency.",
                "character_portraits_registry.json": "Registry mapping character IDs to portrait paths.",
                "scenes/scene_XX/frame_*.png": "Storyboard frames with composited characters.",
                "scenes/scene_XX/scene_video.mp4": "Scene video from motion prompt + frame refs.",
                "final_video.mp4": "Concatenated scene videos.",
            },
        )

        # ==== PHASE 4: Concatenate Final Video ====
        final_video_path = None
        video_paths = [s["video_path"] for s in scene_outputs if s["video_path"]]
        
        if video_paths:
            self.logger.info(f"Phase 4: Concatenating {len(video_paths)} scene videos...")
            final_video_path = os.path.join(self.working_dir, "final_video.mp4")
            
            try:
                concat_videos(video_paths, final_video_path)
                
                # Generate and add audio if video doesn't have audio
                from moviepy import VideoFileClip
                from utils.pipeline.audio_helper import ensure_video_has_audio
                
                # Collect audio descriptions from script scenes
                audio_descriptions = []
                for scene_output in scene_outputs:
                    if scene_output.get("script"):
                        audio_descriptions.append(scene_output["script"][:200])  # Use script snippet
                
                await ensure_video_has_audio(
                    video_path=final_video_path,
                    audio_descriptions=audio_descriptions if audio_descriptions else None,
                    working_dir=self.working_dir,
                    force_regenerate=self.force_regenerate,
                )
                
                self.logger.info(f"Final video saved to: {final_video_path}")
            except Exception as e:
                self.logger.error(f"Failed to concatenate videos: {e}")
                final_video_path = None

        # ==== PHASE 5: Monetization ====
        self.logger.info("Phase 5: Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=f"Short Film: {premise[:50]}...",
            description=story[:500],
            audience=audience or "General",
            duration_seconds=target_duration_minutes * 60,
            genre=genre,
            is_shorts=False,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # ==== PHASE 6: Viral Shorts Extraction ====
        viral_shorts = []
        if final_video_path and target_duration_minutes >= 2:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = json.dumps(script_scenes, ensure_ascii=False)
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_video_path,
                script_content=script_full_text,
                total_duration_seconds=target_duration_minutes * 60,
                content_type="short_movie"
            )

        # Build final output
        payload = {
            "run_id": self.run_id,
            "premise": premise,
            "genre": genre,
            "target_duration_minutes": target_duration_minutes,
            "content_format": content_format,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "story": story,
            "characters": [c.model_dump() for c in characters],
            "script_scenes": script_scenes,
            "scene_outputs": scene_outputs,
            "final_video_path": final_video_path,
            "viral_shorts": viral_shorts,
            "monetization_plan": monetization_plan.model_dump(),
            # S3 Entity info
            "is_s3_characters": is_s3_characters,
            "brand_id": brand_id,
            "game_id": game_id,
            "character_portraits_registry": character_portraits_registry,
        }

        # ==== PHASE 7: Final Continuity Audit ====
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=story,
                storyboard=script_scenes,
                video_metadata=payload
            )
            payload["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])

        self.logger.info("Pipeline complete!")
        return payload

    def _get_portrait_path(
        self,
        character_portraits_registry: Dict[str, Any],
        identifier: str,
    ) -> Optional[str]:
        """Resolve front portrait path from registry; case-insensitive fallback."""
        entry = character_portraits_registry.get(identifier)
        if not entry and identifier:
            entry = next(
                (character_portraits_registry[k] for k in character_portraits_registry if (k or "").lower() == identifier.lower()),
                None,
            )
        if not entry:
            return None
        front = entry.get("front") if isinstance(entry, dict) else None
        if isinstance(front, dict):
            return front.get("path")
        return str(front) if front else None

    def _composite_s3_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        frame_desc: str,
        character_portraits_registry: Dict[str, Any],
    ) -> None:
        """
        Composite character portraits onto a generated frame for visual consistency.

        AI image generators cannot reliably reproduce specific character designs from
        reference images alone. This post-processing step overlays the canonical character
        portraits to ensure consistent appearance across ALL frames and scenes.
        
        Works for BOTH S3 characters and newly generated character portraits.
        Now uses view selection to pick front/side/back view based on shot description.
        """
        if not visible_characters or not os.path.exists(frame_path):
            return
        
        # Collect character portrait paths and infer positions
        char_data_to_composite: List[Dict[str, Any]] = []
        
        for char in visible_characters:
            # Use view selector to choose appropriate view based on shot description
            view = get_character_view_for_shot(frame_desc)
            expression = get_character_expression_for_shot(frame_desc)
            
            # Get portrait path with view/expression support
            path = self._get_portrait_path_with_view(
                character_portraits_registry, 
                char.identifier_in_scene or "",
                view,
                expression
            )
            
            if path and os.path.exists(path):
                # Infer position for THIS specific character from description
                pos = get_character_position_from_description(frame_desc, char.identifier_in_scene)
                scale = min(get_character_scale_from_shot_type(frame_desc), 0.5)
                
                char_data_to_composite.append({
                    "path": path,
                    "position": pos,
                    "scale": scale,
                    "name": char.identifier_in_scene,
                    "view": view.value,
                    "expression": expression.value,
                })
        
        if not char_data_to_composite:
            return
            
        try:
            if len(char_data_to_composite) == 1:
                data = char_data_to_composite[0]
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=data["path"],
                    output_path=frame_path,
                    position=data["position"],
                    scale_factor=data["scale"],
                    vertical_offset=0.05,
                    blend_mode="soft",
                )
                self.logger.info(
                    f"Composited {data['name']} ({data['view']}_{data['expression']}) "
                    f"onto {os.path.basename(frame_path)} at {data['position']}"
                )
            else:
                # Multiple characters - use inferred positions
                paths = [d["path"] for d in char_data_to_composite]
                positions = [d["position"] for d in char_data_to_composite]
                scales = [d["scale"] for d in char_data_to_composite]
                names = [d["name"] for d in char_data_to_composite]
                
                # Distribution logic: If all are "center", we distribute them.
                # BUT if one is the "main_host" (usually idx 0), we keep it central.
                if all(p == "center" for p in positions):
                    if len(positions) == 2:
                        # Character 0 (often main) at center-left, Character 1 at center-right
                        positions = ["center-left", "center-right"]
                    elif len(positions) == 3:
                        positions = ["left", "center", "right"]
                
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=paths,
                    output_path=frame_path,
                    positions=positions,
                    scale_factors=scales,
                    character_names=names,
                )
                self.logger.info(f"Composited {len(paths)} characters ({', '.join(names)}) onto {os.path.basename(frame_path)}")
        except Exception as e:
            self.logger.warning(f"Failed to composite S3 characters onto {frame_path}: {e}")
    
    def _get_portrait_path_with_view(
        self,
        registry: Dict[str, Any],
        char_id: str,
        view: CharacterView,
        expression: CharacterExpression,
    ) -> Optional[str]:
        """Get portrait path with view and expression support, falling back gracefully."""
        if not char_id or char_id not in registry:
            return None
        
        char_data = registry[char_id]
        
        # Try new format with view and expression
        view_data = char_data.get(view.value, {})
        if isinstance(view_data, dict):
            # Try expression-specific path
            expr_data = view_data.get(expression.value)
            if expr_data:
                path = expr_data.get("path") if isinstance(expr_data, dict) else str(expr_data)
                if path and os.path.exists(path):
                    return path
            
            # Try neutral expression for this view
            neutral_data = view_data.get("neutral", view_data)
            if isinstance(neutral_data, dict):
                path = neutral_data.get("path")
            else:
                path = str(neutral_data) if neutral_data else None
            if path and os.path.exists(path):
                return path
        
        # Fall back to front view (legacy or new format)
        front_data = char_data.get("front", {})
        if isinstance(front_data, dict):
            path = front_data.get("path")
            if path and os.path.exists(path):
                return path
            neutral_data = front_data.get("neutral")
            if neutral_data:
                path = neutral_data.get("path") if isinstance(neutral_data, dict) else str(neutral_data)
                if path and os.path.exists(path):
                    return path
        
        return None
    
    def _composite_props_on_frame(
        self,
        frame_path: str,
        visible_props: List[Any],
        prop_reference_images: List[Dict[str, str]],
        frame_desc: str,
    ) -> None:
        """Composite prop reference images onto a frame for object consistency."""
        if not visible_props or not prop_reference_images or not os.path.exists(frame_path):
            return
        
        # Build a lookup by prop identifier
        prop_refs_by_id = {}
        for ref in prop_reference_images:
            desc = ref.get("description", "")
            for prop in visible_props:
                if hasattr(prop, 'identifier') and prop.identifier.lower() in desc.lower():
                    prop_refs_by_id[prop.identifier] = ref.get("path")
                    break
        
        # Collect props to composite
        props_to_composite = []
        for prop in visible_props:
            if not hasattr(prop, 'identifier'):
                continue
            prop_path = prop_refs_by_id.get(prop.identifier)
            if prop_path and os.path.exists(prop_path):
                h_pos, v_pos = get_prop_position_from_description(frame_desc, prop.identifier)
                scale = get_prop_scale_from_context(frame_desc, prop.identifier)
                props_to_composite.append({
                    "path": prop_path,
                    "h_pos": h_pos,
                    "v_pos": v_pos,
                    "scale": scale,
                    "name": prop.identifier,
                })
        
        if not props_to_composite:
            return
        
        try:
            if len(props_to_composite) == 1:
                data = props_to_composite[0]
                composite_prop_on_image(
                    background_path=frame_path,
                    prop_path=data["path"],
                    output_path=frame_path,
                    position=data["h_pos"],
                    scale_factor=data["scale"],
                    vertical_position=data["v_pos"],
                    blend_mode="soft",
                )
                self.logger.info(f"Composited prop {data['name']} onto {os.path.basename(frame_path)}")
            else:
                paths = [d["path"] for d in props_to_composite]
                positions = [(d["h_pos"], d["v_pos"]) for d in props_to_composite]
                scales = [d["scale"] for d in props_to_composite]
                
                composite_multiple_props(
                    background_path=frame_path,
                    prop_paths=paths,
                    output_path=frame_path,
                    prop_positions=positions,
                    scale_factors=scales,
                )
                names = [d["name"] for d in props_to_composite]
                self.logger.info(f"Composited {len(paths)} props ({', '.join(names)}) onto {os.path.basename(frame_path)}")
        except Exception as e:
            self.logger.warning(f"Failed to composite props onto {frame_path}: {e}")

    def _resolve_ref_paths(self, scene_reference_images: List[Dict[str, Any]]) -> List[str]:
        """Resolve reference image entries to local file paths. Downloads http(s) URLs to
        working_dir/s3_characters/_url_refs/ so generators that only accept paths work."""
        out = []
        for r in scene_reference_images:
            path = r.get("path")
            if not path or not isinstance(path, str):
                continue
            is_url = path.startswith("http://") or path.startswith("https://")
            if not is_url:
                if os.path.exists(path):
                    out.append(path)
                continue
            ext = "png"
            if ".jpg" in path.split("?")[0] or ".jpeg" in path.split("?")[0]:
                ext = "jpg"
            h = hashlib.sha256(path.encode()).hexdigest()[:16]
            local = os.path.join(self.working_dir, "s3_characters", "_url_refs", f"{h}.{ext}")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            if os.path.exists(local) and os.path.getsize(local) > 0:
                out.append(local)
                continue
            try:
                _download_image(path, local)
                if os.path.exists(local) and os.path.getsize(local) > 0:
                    out.append(local)
            except Exception as e:
                self.logger.warning(f"Could not download reference image {path[:60]}...: {e}")
        return out

    def _extract_motion_prompt(self, scene_script: str, style: str) -> str:
        """Extract a motion/action description from the scene script for video generation."""
        # Parse scene script to find action descriptions
        if isinstance(scene_script, str):
            # Look for action lines (typically in parentheses or after character names)
            lines = scene_script.split("\n")
            actions = []
            for line in lines:
                line = line.strip()
                if line.startswith("(") and line.endswith(")"):
                    actions.append(line[1:-1])
                elif not line.isupper() and ":" not in line and len(line) > 20:
                    # Likely a description line
                    actions.append(line)
            
            if actions:
                motion_desc = " ".join(actions[:3])  # First 3 action descriptions
            else:
                motion_desc = scene_script[:200]
        else:
            motion_desc = str(scene_script)[:200]
        
        return f"{motion_desc}, {style} style, cinematic motion, smooth camera movement"
