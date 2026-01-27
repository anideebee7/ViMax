"""
Idea to Kids Movie Video Pipeline

Generates animated kids movie videos with age-appropriate content,
character consistency, scene-by-scene animation, and monetization recommendations.

Supports S3 character resolution for consistent character appearances
via post-processing compositing throughout the entire movie.
"""
import json
import logging
import os
import re
import shutil
from typing import Optional, Dict, Any, List, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing import KidsScreenwriter
from agents.directors.film import KidsMovieDirector
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.media.image import composite_character_on_image, composite_multiple_characters, get_character_position_from_description, get_character_scale_from_shot_type
from utils.media.video import concat_videos
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from interfaces.entities.character import CharacterInScene
from configs.constants.pipeline_profiles import KIDS_MOVIE_PROFILE


class KidsMoviePipeline:
    """Pipeline to generate kids animated movie content."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/kids_movie",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="kids_movie",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.kids_screenwriter = KidsScreenwriter(chat_model=self.chat_model)
        self.kids_movie_director = KidsMovieDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="kids_movie")
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="kids_movie", run_id=self.run_id, local_dir=self.working_dir)

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

        chat_model_args = config["chat_model"]["init_args"]
        chat_model_args = {k: _resolve_env(v) for k, v in chat_model_args.items()}
        chat_model = init_chat_model(**chat_model_args)

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)

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
        )

    async def _generate_scene_frame(
        self,
        scene_description: str,
        style: str,
        output_path: str,
        character_portraits: Optional[Dict[str, Any]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Generate an animated frame for a scene with character compositing."""
        if not self.image_generator:
            return None
        
        # Detect characters mentioned in scene description
        visible_chars = []
        char_refs = []
        if characters and character_portraits:
            for char in characters:
                char_name = char.identifier_in_scene
                if not char_name:
                    continue
                pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                if re.search(pattern, scene_description):
                    visible_chars.append(char)
                    if char_name in character_portraits:
                        front_info = character_portraits[char_name].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path):
                            char_refs.append(path)
        
        # CHARACTER CONSISTENCY FIX:
        # We follow a dual-track generation process:
        # 1. RAW Frame: AI generates the full scene with characters "gelled" in (lighting, etc.)
        # 2. STORYBOARD Frame: Exact S3 portraits composited on a clean background.
        
        # --- TRACK 1: RAW GENERATION (Gelled Characters) ---
        raw_output_path = output_path.replace(".png", "_raw.png")
        char_desc_parts = []
        for char in visible_chars:
            if char.static_features:
                char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
        char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
        
        raw_prompt = f"""Kids animated movie scene. {scene_description}.{char_context}
Style: {style}, colorful, kid-friendly, cute characters, safe for children.
High quality animation frame, vibrant colors, expressive characters gelled into scene.
Proper lighting and shadows. No text, no collages."""
        
        try:
            # For raw, use background refs + character portraits
            char_refs = []
            if visible_chars and character_portraits:
                for char in visible_chars[:2]:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits:
                        front_info = character_portraits[char_id].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path):
                            char_refs.append(path)
            
            raw_refs = (reference_images or [])[:1] + char_refs
            
            debug_dir = os.path.join(os.path.dirname(output_path), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_raw_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(raw_prompt)

            raw_image = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs if raw_refs else None,
            )
            raw_image.save(raw_output_path)
            
            # --- TRACK 2: STORYBOARD GENERATION (Composited S3 Characters) ---
            bg_visual_desc = scene_description
            if visible_chars:
                for char in visible_chars:
                    bg_visual_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_visual_desc)
            
            bg_prompt = f"""Kids animated movie background scenery. {bg_visual_desc}.
Style: {style}, colorful, kid-friendly.
EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures.
High quality animation background. No text."""
            
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_bg_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(bg_prompt)

            bg_image = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=(reference_images or [])[:2],
            )
            bg_image.save(output_path)
            
            if visible_chars and character_portraits:
                self._composite_characters_on_frame(
                    frame_path=output_path, 
                    visible_characters=visible_chars,
                    character_portraits=character_portraits,
                    scene_description=scene_description,
                )
            
            return output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate scene frame: {e}")
            return None

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        character_portraits: Dict[str, Any],
        scene_description: str,
    ) -> None:
        """Composite character portraits onto a scene frame."""
        if not visible_characters or not os.path.exists(frame_path):
            return
        
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            if char_id in character_portraits:
                front_info = character_portraits[char_id].get("front", {})
                path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                if path and os.path.exists(path):
                    portraits_to_composite.append({"path": path, "name": char_id})
        
        if not portraits_to_composite:
            return
        
        try:
            if len(portraits_to_composite) == 1:
                position = get_character_position_from_description(scene_description, portraits_to_composite[0]["name"])
                scale = get_character_scale_from_shot_type(scene_description)
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=portraits_to_composite[0]["path"],
                    output_path=frame_path,
                    position=position,
                    scale_factor=min(scale, 0.5),
                    blend_mode="soft",
                )
            else:
                paths = [p["path"] for p in portraits_to_composite[:3]]
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=paths,
                    output_path=frame_path,
                    scale_factors=[0.4] * len(paths),
                )
        except Exception as e:
            self.logger.warning(f"Failed to composite characters: {e}")

    async def _generate_scene_video(
        self,
        scene_description: str,
        style: str,
        output_path: str,
        first_frame_path: Optional[str] = None,
        character_portraits: Optional[Dict[str, Any]] = None,
        duration_seconds: int = 8,
    ) -> Optional[str]:
        """Generate an animated video for a scene."""
        if not self.video_generator:
            return None
        
        prompt = f"""Kids animated movie scene. {scene_description}
Style: {style}, colorful animation, kid-friendly, cute expressive characters.
Smooth animation, vibrant colors, safe and fun for children."""
        
        try:
            refs = []
            raw_frame_path = first_frame_path.replace(".png", "_raw.png") if first_frame_path else None
            # Use raw frame for video if available, otherwise fallback to composited
            video_ref_frame = raw_frame_path if raw_frame_path and os.path.exists(raw_frame_path) else first_frame_path
            
            if video_ref_frame and os.path.exists(video_ref_frame):
                refs.append(video_ref_frame)
            
            # Add character portraits as references
            if character_portraits:
                for char_id, portrait_info in list(character_portraits.items())[:2]:
                    front_info = portrait_info.get("front", {})
                    path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                    if path and os.path.exists(path) and path not in refs and len(refs) < 3:
                        refs.append(path)
            
            # Clamp duration to API limits
            clamped_duration = max(4, min(8, duration_seconds))
            
            # Save debug prompt
            debug_dir = os.path.join(os.path.dirname(output_path), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".mp4", "_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(prompt)

            video_output = await self.video_generator.generate_single_video(
                prompt=prompt,
                reference_image_paths=refs if refs else None,
                duration=clamped_duration,
            )
            video_output.save(output_path)
            return output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate scene video: {e}")
            return None

    async def __call__(
        self,
        story_idea: Optional[str] = None,
        age_group: str = "6-8",
        characters: Optional[str] = None,
        moral_lesson: Optional[str] = None,
        target_duration_minutes: int = 15,
        style: str = "colorful 3D animation",
        audience: Optional[str] = None,
        generate_character_art: bool = True,
        generate_scene_frames: bool = True,
        generate_videos: bool = True,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_ids: Optional[List[str]] = None,
        s3_characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate kids animated movie video.

        Args:
            story_idea: Story concept (optional if auto_ideate=True)
            age_group: Target age group (3-5, 6-8, 9-12)
            characters: Character descriptions
            moral_lesson: Moral/lesson to teach
            target_duration_minutes: Target duration
            style: Animation style
            audience: Additional audience description
            generate_character_art: Whether to generate character designs
            generate_scene_frames: Whether to generate scene storyboard frames
            generate_videos: Whether to generate scene videos and final movie
            trendy: Whether to incorporate trending kids content themes
            auto_ideate: If True, automatically generate story idea
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
            brand_id: S3 brand ID for brand context
            game_id: S3 game ID for game context
            character_ids: S3 character IDs to use in the movie
            s3_characters: Pre-built CharacterInScene objects
            character_portraits_registry: Pre-built character portrait registry

        Returns:
            Dictionary with script, characters, scene frames, videos, and monetization plan
        """
        ideation_result: Optional[IdeationResult] = None
        kids_context = ""
        output_json_path = os.path.join(self.working_dir, "kidsmovie_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Initialize character data
        local_character_portraits: Dict[str, Any] = character_portraits_registry or {}
        local_s3_characters: List[CharacterInScene] = s3_characters or []
        brand_ctx: Optional[BrandContext] = None
        game_ctx: Optional[GameContext] = None
        
        # Resolve S3 entities (brand, game, characters)
        if brand_id or game_id or character_ids or (auto_ideate and brand_hint):
            texts = []
            if brand_id:
                texts.append(f"@brand:{brand_id}")
            elif brand_hint:
                texts.append(brand_hint)
            if game_id:
                texts.append(f"@game:{game_id}")
            for char_id in (character_ids or []):
                texts.append(f"@character:{char_id}")
            
            if texts:
                resolution = resolve_s3_entities(
                    texts=texts,
                    brand_hint=brand_id or brand_hint,
                    game_hint=game_id,
                    working_dir=self.working_dir,
                )
                brand_ctx = resolution.get("brand_context")
                game_ctx = resolution.get("game_context")
                
                # Extract character portraits from S3
                s3_chars_dir = os.path.join(self.working_dir, "s3_characters")
                if os.path.exists(s3_chars_dir):
                    for char_folder in os.listdir(s3_chars_dir):
                        char_path = os.path.join(s3_chars_dir, char_folder)
                        if os.path.isdir(char_path):
                            front_path = os.path.join(char_path, "front.png")
                            if not os.path.exists(front_path):
                                for f in os.listdir(char_path):
                                    if f.endswith(('.png', '.jpg', '.jpeg')):
                                        front_path = os.path.join(char_path, f)
                                        break
                            if os.path.exists(front_path):
                                local_character_portraits[char_folder] = {
                                    "front": {"path": front_path, "description": f"Front portrait of {char_folder}"}
                                }
                                if not any(c.identifier_in_scene == char_folder for c in local_s3_characters):
                                    metadata_path = os.path.join(char_path, "metadata.json")
                                    static_features = ""
                                    if os.path.exists(metadata_path):
                                        try:
                                            with open(metadata_path, "r") as f:
                                                meta = json.load(f)
                                                static_features = meta.get("description", "")
                                        except:
                                            pass
                                    local_s3_characters.append(CharacterInScene(
                                        idx=len(local_s3_characters),
                                        identifier_in_scene=char_folder,
                                        static_features=static_features,
                                        dynamic_features="",
                                        is_visible=True,
                                    ))
        
        if local_character_portraits:
            self.logger.info(f"S3 characters available: {list(local_character_portraits.keys())}")

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="kids")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Ideation
        ideation_path = os.path.join(self.working_dir, "ideation.json")
        if auto_ideate and os.path.exists(ideation_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing ideation: {ideation_path}")
            with open(ideation_path, "r", encoding="utf-8") as f:
                ideation_data = json.load(f)
                ideation_result = IdeationResult(**ideation_data)
                story_idea = ideation_result.idea
                audience = audience or ideation_result.target_audience
        elif auto_ideate:
            self.logger.info(f"🧠 Auto-ideating kids movie in {ideation_mode} mode...")
            
            # Load brand/game context if brand mode
            if ideation_mode == "brand" and brand_hint:
                resolution = resolve_s3_entities(
                    texts=[brand_hint],
                    brand_hint=brand_hint,
                    working_dir=self.working_dir,
                )
                brand_ctx = resolution.get("brand_context")
                game_ctx = resolution.get("game_context")
                
                # If brand has characters, incorporate them
                if brand_ctx and brand_ctx.characters:
                    char_names = [c.name for c in brand_ctx.characters[:4]]
                    characters = characters or f"Characters: {', '.join(char_names)}"
                
                if brand_ctx or game_ctx:
                    ideation_result = await self.ideation_engine.ideate_for_brand(
                        content_type="kids",
                        brand_context=brand_ctx,
                        game_context=game_ctx,
                        trend_context=trend_context,
                    )
            
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(
                    content_type="kids",
                    mode=ideation_mode,
                    audience=f"children ages {age_group}",
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            # Use ideation result
            story_idea = ideation_result.idea
            audience = audience or ideation_result.target_audience
            
            # Save ideation result
            ideation_output = ideation_result.model_dump()
            if brand_ctx: ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx: ideation_output["game_context"] = game_ctx.model_dump()
            with open(ideation_path, "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)

        # Build context
        effective_audience = audience or f"children ages {age_group}"

        # RESUME CHECK: Script
        script_path = os.path.join(self.working_dir, "kids_script.json")
        if os.path.exists(script_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing script: {script_path}")
            with open(script_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
                from agents.kids_screenwriter import KidsScript
                script = KidsScript(**script_data)
        else:
            # Director: creative brief
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "kids_script_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Idea: {story_idea}\nContext: {kids_context}")

            director_brief = await self.kids_movie_director.direct(
                story_idea=story_idea,
                age_group=age_group,
                moral_lesson=moral_lesson,
                target_duration_minutes=target_duration_minutes,
                style=style,
                characters=characters,
                additional_context=trend_context_block if trend_context_block else None,
            )
            kids_context = f"{trend_context_block or ''}\n\n{director_brief.to_context_block()}".strip()

            # Generate kids script
            self.logger.info("Generating kids animated script...")
            script = await self.kids_screenwriter.write_kids_script(
                story_idea=story_idea,
                age_group=age_group,
                moral_lesson=moral_lesson,
                target_duration_minutes=target_duration_minutes,
                style=style,
                characters=characters,
                additional_context=kids_context,
            )
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script.model_dump(), f, ensure_ascii=False, indent=2)

        # Phase 1 reasoning: rationale behind the kids script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="kids_movie",
            phase_label="Phase 1: Story and script",
            content_type="script",
            rationale=(
                "The kids script is written for the target age group with clear moral lesson, safe conflict, "
                "and age-appropriate dialogue. KidsMovieDirector defines tone, pacing, and character roles. "
                "KidsScreenwriter uses story_idea, characters, moral_lesson, and style to create a structured "
                "script. Trends can suggest themes and character dynamics that resonate with current kids content."
            ),
            inputs={
                "story_idea": story_idea[:200] + "…" if story_idea and len(story_idea) > 200 else story_idea,
                "age_group": age_group,
                "moral_lesson": moral_lesson,
                "target_duration_minutes": target_duration_minutes,
                "style": style,
                "characters": (characters or "")[:150],
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={"kids_script.json": "Kids animated script (title, synopsis, moral_lesson, characters, scenes)."},
        )

        # Cinematographer/picturization reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="kids_movie",
            rationale=(
                "Picturization: each scene gets a storyboard frame and animated video clip. "
                "Character consistency is achieved via post-processing compositing using S3 character "
                "portraits or generated character art. Characters mentioned in scene descriptions are "
                "detected using regex word boundaries and composited onto frames. All scene videos are "
                "concatenated into the final kids movie. The director's visual_style (e.g. 'colorful 3D "
                "animation') drives the visual prompts for age-appropriate, kid-friendly content."
            ),
            inputs={
                "style": style,
                "generate_scene_frames": generate_scene_frames,
                "generate_videos": generate_videos,
                "s3_characters_used": list(local_character_portraits.keys()) if local_character_portraits else [],
            },
            outputs={
                "kids_script.json": "Scene-by-scene script.",
                "characters/": "Character art for visual consistency.",
                "scenes/*.png": "Storyboard frames per scene.",
                "scenes/*.mp4": "Animated video clips per scene.",
                "kids_movie_final.mp4": "Concatenated final kids movie.",
            },
        )

        # Generate character art if requested
        character_art = {}
        if generate_character_art and self.image_generator:
            self.logger.info("Generating character designs...")
            characters_dir = os.path.join(self.working_dir, "characters")
            os.makedirs(characters_dir, exist_ok=True)

            for char in script.characters:
                # Skip if we already have S3 portrait for this character
                if char.name in local_character_portraits:
                    character_art[char.name] = local_character_portraits[char.name]["front"]["path"]
                    continue
                
                try:
                    prompt = f"Kids cartoon character design. Name: {char.name}. {char.appearance}. {char.personality}. Style: {style}. Cute, kid-friendly, colorful."
                    char_path = os.path.join(characters_dir, f"{char.name.lower().replace(' ', '_')}.png")
                    
                    # Save debug prompt
                    debug_dir = os.path.join(characters_dir, "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, f"{char.name.lower().replace(' ', '_')}_prompt.txt"), "w", encoding="utf-8") as f:
                        f.write(prompt)

                    image_output = await self.image_generator.generate_single_image(prompt=prompt)
                    image_output.save(char_path)
                    character_art[char.name] = char_path
                    
                    # Add to portraits registry for compositing
                    local_character_portraits[char.name] = {
                        "front": {"path": char_path, "description": f"Character art for {char.name}"}
                    }
                except Exception as e:
                    self.logger.warning(f"Failed to generate art for {char.name}: {e}")
        
        # Build CharacterInScene list for compositing
        all_characters: List[CharacterInScene] = local_s3_characters.copy()
        for char in script.characters:
            if not any(c.identifier_in_scene == char.name for c in all_characters):
                all_characters.append(CharacterInScene(
                    idx=len(all_characters),
                    identifier_in_scene=char.name,
                    static_features=f"{char.appearance}. {char.personality}",
                    dynamic_features="",
                    is_visible=True,
                ))
        
        # Plan audio requirements for kids movie scenes
        audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not self.force_regenerate:
            self.logger.info("Loading existing audio plan...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None and hasattr(script, 'scenes') and script.scenes:
            self.logger.info("Planning audio requirements for kids movie scenes...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert kids movie scenes to Scene objects for audio planning
                scene_objects = []
                for idx, scene in enumerate(script.scenes):
                    scene_script = f"{scene.description}. {scene.dialogue if hasattr(scene, 'dialogue') else ''}"
                    scene_obj = Scene(
                        idx=idx,
                        is_last=(idx == len(script.scenes) - 1),
                        environment=EnvironmentInScene(
                            slugline=scene.setting if hasattr(scene, 'setting') else "KIDS MOVIE SCENE",
                            description=scene.setting if hasattr(scene, 'setting') else "",
                        ),
                        characters=[c for c in all_characters if c.identifier_in_scene in (scene.characters_present if hasattr(scene, 'characters_present') else [])],
                        script=scene_script,
                    )
                    scene_objects.append(scene_obj)
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,
                    previous_audio_plan=None,
                    style=style,
                    audience=effective_audience,
                    content_format="animated",  # Kids movies are animated
                )
                
                self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                self.logger.info(f"Audio plan created with {len(audio_plan.scene_plans)} scene plans")
            except Exception as e:
                self.logger.warning(f"Failed to create audio plan: {e}. Continuing without detailed audio planning.")
                audio_plan = None
        
        self.audio_plan = audio_plan
        
        # Generate scene frames and videos
        scene_frames: Dict[str, str] = {}
        scene_videos: Dict[str, str] = {}
        scenes_dir = os.path.join(self.working_dir, "scenes")
        os.makedirs(scenes_dir, exist_ok=True)
        
        # Calculate duration per scene
        num_scenes = len(script.scenes) if hasattr(script, 'scenes') and script.scenes else 5
        scene_duration_seconds = max(5, int((target_duration_minutes * 60) / num_scenes))
        
        if (generate_scene_frames or generate_videos) and hasattr(script, 'scenes') and script.scenes:
            self.logger.info(f"Generating frames/videos for {len(script.scenes)} scenes...")
            
            for i, scene in enumerate(script.scenes):
                scene_frame_path = os.path.join(scenes_dir, f"scene_{i+1:02d}_frame.png")
                scene_video_path = os.path.join(scenes_dir, f"scene_{i+1:02d}_video.mp4")
                
                # RESUME CHECK: Scene Video
                if os.path.exists(scene_video_path) and not self.force_regenerate:
                    self.logger.info(f"  Resuming from existing scene video: {scene_video_path}")
                    scene_videos[f"scene_{i+1}"] = scene_video_path
                    if os.path.exists(scene_frame_path):
                        scene_frames[f"scene_{i+1}"] = scene_frame_path
                    continue

                scene_desc = f"{scene.setting}. {scene.description}. Characters: {', '.join(scene.characters_present) if hasattr(scene, 'characters_present') else ''}. {scene.dialogue if hasattr(scene, 'dialogue') else ''}"
                
                # DEBUG LOGS FOR SHOT
                scene_chars = scene.characters_present if hasattr(scene, 'characters_present') else []
                self.logger.info(
                    f"\n🎬 [KIDS SCENE {i+1}] DEBUG INFO:\n"
                    f"   📍 Setting: {scene.setting if hasattr(scene, 'setting') else 'N/A'}\n"
                    f"   👥 Characters ({len(scene_chars)}): {', '.join(scene_chars) if scene_chars else 'None'}\n"
                    f"   ⏱️ Duration: {min(scene_duration_seconds, 8)}s\n"
                    f"   📝 Visual Plan: {scene.description if hasattr(scene, 'description') else 'N/A'}\n"
                    f"   💬 Dialogue: {scene.dialogue if hasattr(scene, 'dialogue') else 'None'}\n"
                )

                # Get reference images (character portraits for this scene)
                scene_refs = []
                for char_name in (scene.characters_present if hasattr(scene, 'characters_present') else []):
                    if char_name in local_character_portraits:
                        front_info = local_character_portraits[char_name].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path):
                            scene_refs.append(path)
                
                if generate_scene_frames and (not os.path.exists(scene_frame_path) or self.force_regenerate):
                    frame = await self._generate_scene_frame(
                        scene_description=scene_desc,
                        style=style,
                        output_path=scene_frame_path,
                        character_portraits=local_character_portraits,
                        characters=all_characters,
                        reference_images=scene_refs,
                    )
                    if frame:
                        scene_frames[f"scene_{i+1}"] = frame
                elif os.path.exists(scene_frame_path):
                    scene_frames[f"scene_{i+1}"] = scene_frame_path
                
                if generate_videos and (not os.path.exists(scene_video_path) or self.force_regenerate):
                    video = await self._generate_scene_video(
                        scene_description=scene_desc,
                        style=style,
                        output_path=scene_video_path,
                        first_frame_path=scene_frames.get(f"scene_{i+1}"),
                        character_portraits=local_character_portraits,
                        duration_seconds=min(scene_duration_seconds, 8),
                    )
                    if video:
                        scene_videos[f"scene_{i+1}"] = video
        
        # Concatenate all scene videos into final movie
        final_video_path: Optional[str] = None
        if generate_videos and scene_videos:
            self.logger.info("Concatenating scene videos into final kids movie...")
            final_video_path = os.path.join(self.working_dir, "kids_movie_final.mp4")
            
            video_paths = [scene_videos[f"scene_{i+1}"] for i in range(len(script.scenes)) if f"scene_{i+1}" in scene_videos]
            
            if len(video_paths) > 1:
                try:
                    concat_videos(video_paths, final_video_path)
                    
                    # Generate and add audio if video doesn't have audio
                    from moviepy import VideoFileClip
                    from utils.pipeline.audio_helper import ensure_video_has_audio
                    
                    # Collect audio descriptions from script scenes
                    audio_descriptions = []
                    if script and hasattr(script, 'scenes'):
                        for scene in script.scenes:
                            if hasattr(scene, 'description') and scene.description:
                                audio_descriptions.append(scene.description[:200])
                    
                    await ensure_video_has_audio(
                        video_path=final_video_path,
                        audio_descriptions=audio_descriptions if audio_descriptions else None,
                        working_dir=self.working_dir,
                        force_regenerate=self.force_regenerate,
                    )
                    
                    self.logger.info(f"Final kids movie saved: {final_video_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to concatenate videos: {e}")
                    final_video_path = None
            elif video_paths:
                shutil.copy(video_paths[0], final_video_path)
                # Add audio to single video if needed
                from utils.pipeline.audio_helper import ensure_video_has_audio
                await ensure_video_has_audio(
                    video_path=final_video_path,
                    audio_descriptions=None,
                    working_dir=self.working_dir,
                    force_regenerate=self.force_regenerate,
                )

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=script.title,
            description=f"Kids animated content for ages {age_group}. {script.synopsis}. Moral lesson: {script.moral_lesson}",
            audience=effective_audience,
            duration_seconds=int(script.total_duration_minutes * 60),
            genre="Kids Animation",
            is_shorts=target_duration_minutes <= 5,
            trend_context=trend_context_block if trend_context_block else None,
        )

        payload = {
            "run_id": self.run_id,
            "story_idea": story_idea,
            "age_group": age_group,
            "target_duration_minutes": target_duration_minutes,
            "style": style,
            "audience": effective_audience,
            "trendy": trendy,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "ideation_result": ideation_result.model_dump() if ideation_result else None,
            "script": script.model_dump(),
            "character_art": character_art,
            "scene_frames": scene_frames,
            "scene_videos": scene_videos,
            "final_video_path": final_video_path,
            "s3_characters_used": list(local_character_portraits.keys()) if local_character_portraits else [],
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=json.dumps(script.model_dump(), ensure_ascii=False),
                storyboard=script.scenes,
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

        return payload
