import os
import logging
import shutil
from agents.creative.writing import Screenwriter
from agents.directors.technical import VideoDirector
from agents.producers.analysis import CharacterExtractor
from agents.producers.visuals import CharacterPortraitsGenerator
from agents.producers.business import MonetizationAdvisor
from agents.producers.audio import AudioPlanner
from agents.planners.strategy import IdeationEngine
from pipelines.base.script import Script2VideoPipeline
from interfaces.entities.character import CharacterInScene
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from interfaces.output.monetization import TrendContext
from configs.constants.pipeline_profiles import get_pipeline_profile, SHORTS_PROFILE
from configs.constants.content_constants import CONTENT_FORMAT_LIVE_ACTION, CONTENT_FORMAT_ANIMATED
from typing import List, Dict, Optional, Any, Literal
import asyncio
import json
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, concatenate_audioclips
import yaml
from langchain.chat_models import init_chat_model
from utils.core.rate_limiter import RateLimiter
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
import importlib
from utils.core.run_id import generate_run_id, write_run_metadata, extract_run_id_from_path, initialize_run_directory
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression


class VideoPipeline:
    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        working_dir: str = ".working_dir/video",
        character_portrait_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        global_reference_images: Optional[List[Dict[str, str]]] = None,
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        shorts_mode: Optional[Dict] = None,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
        pipeline_kind: str = "feature_film",
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="video",
            run_id=run_id,
            use_run_id=use_run_id,
        )
        
        self.character_portrait_overrides = character_portrait_overrides or {}
        self.global_reference_images = global_reference_images or []
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate
        self.shorts_mode = shorts_mode or {}
        self.pipeline_kind = pipeline_kind

        self.screenwriter = Screenwriter(chat_model=self.chat_model, shorts_mode=self.shorts_mode, pipeline_kind=self.pipeline_kind)
        self.video_director = VideoDirector(chat_model=self.chat_model, shorts_mode=self.shorts_mode, pipeline_kind=self.pipeline_kind)
        self.character_extractor = CharacterExtractor(
            chat_model=self.chat_model)
        self.character_portraits_generator = CharacterPortraitsGenerator(
            image_generator=self.image_generator)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind=self.pipeline_kind)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="video", run_id=self.run_id, local_dir=self.working_dir)

    @classmethod
    def init_from_config(
        cls,
        config_path: str,
        run_id: Optional[str] = None,
        working_dir: Optional[str] = None,
    ):
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

        # Create separate rate limiters for each service
        chat_model_rpm = config.get("chat_model", {}).get("max_requests_per_minute", None)
        chat_model_rpd = config.get("chat_model", {}).get("max_requests_per_day", None)
        image_generator_rpm = config.get("image_generator", {}).get("max_requests_per_minute", None)
        image_generator_rpd = config.get("image_generator", {}).get("max_requests_per_day", None)
        video_generator_rpm = config.get("video_generator", {}).get("max_requests_per_minute", None)
        video_generator_rpd = config.get("video_generator", {}).get("max_requests_per_day", None)

        chat_model_rate_limiter = RateLimiter(
            max_requests_per_minute=chat_model_rpm,
            max_requests_per_day=chat_model_rpd
        ) if (chat_model_rpm or chat_model_rpd) else None

        image_rate_limiter = RateLimiter(
            max_requests_per_minute=image_generator_rpm,
            max_requests_per_day=image_generator_rpd
        ) if (image_generator_rpm or image_generator_rpd) else None

        video_rate_limiter = RateLimiter(
            max_requests_per_minute=video_generator_rpm,
            max_requests_per_day=video_generator_rpd
        ) if (video_generator_rpm or video_generator_rpd) else None

        # Display rate limiting configuration
        if chat_model_rate_limiter:
            limits = []
            if chat_model_rpm:
                limits.append(f"{chat_model_rpm} req/min")
            if chat_model_rpd:
                limits.append(f"{chat_model_rpd} req/day")
            print(f"Chat model rate limiting: {', '.join(limits)}")

        if image_rate_limiter:
            limits = []
            if image_generator_rpm:
                limits.append(f"{image_generator_rpm} req/min")
            if image_generator_rpd:
                limits.append(f"{image_generator_rpd} req/day")
            print(f"Image generator rate limiting: {', '.join(limits)}")

        if video_rate_limiter:
            limits = []
            if video_generator_rpm:
                limits.append(f"{video_generator_rpm} req/min")
            if video_generator_rpd:
                limits.append(f"{video_generator_rpd} req/day")
            print(f"Video generator rate limiting: {', '.join(limits)}")

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)

        portrait_overrides = {}
        for override in config.get("character_portrait_overrides", []) or []:
            identifier = override.get("identifier")
            if not identifier:
                continue
            portrait_overrides[identifier] = {
                "front_path": _resolve_path(override.get("front_path")),
                "side_path": _resolve_path(override.get("side_path")),
                "back_path": _resolve_path(override.get("back_path")),
            }

        global_reference_images = []
        for item in config.get("global_reference_images", []) or []:
            path_value = _resolve_path(item.get("path"))
            description = item.get("description", "")
            if path_value and description:
                global_reference_images.append(
                    {
                        "path": path_value,
                        "description": description,
                    }
                )

        # Read shorts mode configuration
        shorts_mode = config.get("shorts_mode", {}) or {}
        if shorts_mode.get("enabled"):
            print(f"📱 Shorts mode enabled (max {shorts_mode.get('max_shots', 4)} shots, ~{shorts_mode.get('target_duration_seconds', 20)}s)")

        # Initialize trend analyzer if configured
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir or run_id, otherwise use config default
        resolved_working_dir = working_dir or config.get("working_dir", ".working_dir/video")
        
        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=resolved_working_dir,
            character_portrait_overrides=portrait_overrides,
            global_reference_images=global_reference_images,
            trend_analyzer=trend_analyzer,
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
            force_regenerate=bool(config.get("force_regenerate", False)),
            shorts_mode=shorts_mode,
        )

    async def extract_characters(
        self,
        story: str,
    ):
        save_path = os.path.join(self.working_dir, "characters.json")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
            characters = [CharacterInScene.model_validate(
                character) for character in characters]
            print(f"🚀 Loaded {len(characters)} characters from existing file.")
        else:
            characters = await self.character_extractor.extract_characters(story)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump([character.model_dump()
                          for character in characters], f, ensure_ascii=False, indent=4)
            print(
                f"✅ Extracted {len(characters)} characters from story and saved to {save_path}.")

        return characters

    async def generate_character_portraits(
        self,
        characters: List[CharacterInScene],
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]],
        style: str,
    ):
        character_portraits_registry_path = os.path.join(
            self.working_dir, "character_portraits_registry.json")
        if character_portraits_registry is None:
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, 'r', encoding='utf-8') as f:
                    character_portraits_registry = json.load(f)
            else:
                character_portraits_registry = {}

        override_identifiers = set(self.character_portrait_overrides.keys())
        tasks = [
            self.generate_portraits_for_single_character(character, style)
            for character in characters
            if (
                character.identifier_in_scene not in character_portraits_registry
                or character.identifier_in_scene in override_identifiers
            )
        ]
        if tasks:
            for future in asyncio.as_completed(tasks):
                character_portraits_registry.update(await future)
                with open(character_portraits_registry_path, 'w', encoding='utf-8') as f:
                    json.dump(character_portraits_registry,
                              f, ensure_ascii=False, indent=4)

            print(
                f"✅ Completed character portrait generation for {len(characters)} characters.")
        else:
            print(
                "🚀 All characters already have portraits, skipping portrait generation.")

        return character_portraits_registry

    async def develop_story(
        self,
        idea: str,
        user_requirement: str,
    ):
        save_path = os.path.join(self.working_dir, "story.txt")
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "story_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(f"Idea: {idea}\nRequirement: {user_requirement}")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                story = f.read()
            print(f"🚀 Loaded story from existing file.")
        else:
            print("🧠 Developing story...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "story_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Idea: {idea}\nRequirement: {user_requirement}")

            story = await self.screenwriter.develop_story(idea=idea, user_requirement=user_requirement)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(story)
            print(f"✅ Developed story and saved to {save_path}.")

        return story

    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: str,
    ):
        save_path = os.path.join(self.working_dir, "script.json")
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "script_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(f"Story: {story[:1000]}\nRequirement: {user_requirement}")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                script = json.load(f)
            print(f"🚀 Loaded script from existing file.")
        else:
            print("🧠 Writing script based on story...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "script_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Story: {story[:1000]}\nRequirement: {user_requirement}")

            script = await self.screenwriter.write_script_based_on_story(story=story, user_requirement=user_requirement)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=4)
            print(f"✅ Written script based on story and saved to {save_path}.")
        return script

    async def generate_portraits_for_single_character(
        self,
        character: CharacterInScene,
        style: str,
    ):
        character_dir = os.path.join(
            self.working_dir, "character_portraits", f"{character.idx}_{character.identifier_in_scene}")
        os.makedirs(character_dir, exist_ok=True)

        overrides = self.character_portrait_overrides.get(character.identifier_in_scene, {})
        override_front = overrides.get("front_path")
        override_side = overrides.get("side_path")
        override_back = overrides.get("back_path")
        override_front_used = False

        front_portrait_path = os.path.join(character_dir, "front.png")
        if override_front and os.path.exists(override_front):
            shutil.copy(override_front, front_portrait_path)
            override_front_used = True
        elif not os.path.exists(front_portrait_path):
            # Save debug prompt
            debug_dir = os.path.join(character_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            # We don't have the exact prompt here as it's inside CharacterPortraitsGenerator, 
            # but we can log that we're calling it.
            with open(os.path.join(debug_dir, "portrait_call.txt"), "w", encoding="utf-8") as f:
                f.write(f"Generating front portrait for {character.identifier_in_scene} with style {style}")

            front_portrait_output = await self.character_portraits_generator.generate_front_portrait(character, style)
            front_portrait_output.save(front_portrait_path)

        side_portrait_path = os.path.join(character_dir, "side.png")
        if override_side and os.path.exists(override_side):
            shutil.copy(override_side, side_portrait_path)
        elif override_front_used or not os.path.exists(side_portrait_path):
            side_portrait_output = await self.character_portraits_generator.generate_side_portrait(character, front_portrait_path)
            side_portrait_output.save(side_portrait_path)

        back_portrait_path = os.path.join(character_dir, "back.png")
        if override_back and os.path.exists(override_back):
            shutil.copy(override_back, back_portrait_path)
        elif override_front_used or not os.path.exists(back_portrait_path):
            back_portrait_output = await self.character_portraits_generator.generate_back_portrait(character, front_portrait_path)
            back_portrait_output.save(back_portrait_path)

        print(
            f"☑️ Completed character portrait generation for {character.identifier_in_scene}.")

        return {
            character.identifier_in_scene: {
                "front": {
                    "path": front_portrait_path,
                    "description": f"A front view portrait of {character.identifier_in_scene}.",
                },
                "side": {
                    "path": side_portrait_path,
                    "description": f"A side view portrait of {character.identifier_in_scene}.",
                },
                "back": {
                    "path": back_portrait_path,
                    "description": f"A back view portrait of {character.identifier_in_scene}.",
                },
            }
        }

    async def __call__(
        self,
        idea: Optional[str] = None,
        user_requirement: Optional[str] = None,
        style: str = "cinematic",
        audience: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        content_format: Literal["live_action", "animated"] = CONTENT_FORMAT_LIVE_ACTION,
        restitch_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the video pipeline. Supports shorts (via shorts_mode config), standard videos,
        and live-action or animated content.
        
        Args:
            idea: The idea/concept for the video (optional if auto_ideate=True)
            user_requirement: Additional requirements (optional if auto_ideate=True)
            style: Visual style for the video
            audience: Target audience (G, PG, teens, adults, family, etc.)
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate the idea
            ideation_mode: Mode for auto-ideation (creativity, trends, viral, brand, podcast)
            brand_hint: Brand name hint for brand-mode ideation
            content_format: 'live_action' or 'animated'
        
        Returns:
            Dictionary containing output metadata including video path and monetization plan
        """
        # Fetch trends if trendy flag is set or if we need them for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="video")
            trend_context_block = trend_context.to_context_block()
            # Save trend data
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        brand_ctx: Optional[BrandContext] = None
        game_ctx: Optional[GameContext] = None
        
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating in {ideation_mode} mode...")
            content_type = "shorts" if self.shorts_mode.get("enabled") else "video"
            
            # Check if brand/game context is available for brand mode
            if ideation_mode == "brand" and brand_hint:
                resolution = resolve_s3_entities(
                    texts=[brand_hint],
                    brand_hint=brand_hint,
                    working_dir=self.working_dir,
                )
                brand_ctx = resolution.get("brand_context")
                game_ctx = resolution.get("game_context")
                
                if brand_ctx or game_ctx:
                    ideation_result = await self.ideation_engine.ideate_for_brand(
                        content_type=content_type,
                        brand_context=brand_ctx,
                        game_context=game_ctx,
                        trend_context=trend_context,
                    )
            
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(
                    content_type=content_type,
                    mode=ideation_mode,
                    audience=audience,
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            # Use ideation result as idea and requirement
            idea = ideation_result.idea
            user_requirement = ideation_result.to_prompt()
            audience = audience or ideation_result.target_audience
            
            # Save ideation result
            ideation_output = ideation_result.model_dump()
            if brand_ctx:
                ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx:
                ideation_output["game_context"] = game_ctx.model_dump()
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated idea: {ideation_result.title}")
            print(f"   Hook: {ideation_result.hook or 'N/A'}")
            if brand_ctx:
                print(f"   Brand: {brand_ctx.name}")
            if game_ctx:
                print(f"   Game: {game_ctx.name}")

        # Validate that we have an idea
        if not idea:
            raise ValueError("Either provide an 'idea' or set 'auto_ideate=True'")

        # Append shorts mode requirement if enabled
        effective_user_requirement = user_requirement or ""
        if content_format == CONTENT_FORMAT_ANIMATED:
            effective_user_requirement = f"Content format: animated. Visuals and action stylized for 2D/3D animation.\n\n{effective_user_requirement}"
        # Add audience context
        if audience:
            effective_user_requirement = f"Target audience: {audience}\n\n{effective_user_requirement}"
        # Add trend context
        if trend_context_block:
            effective_user_requirement = f"{effective_user_requirement}\n\n{trend_context_block}"
        if self.shorts_mode.get("enabled"):
            shorts_suffix = self.shorts_mode.get("user_requirement_suffix", "")
            if shorts_suffix:
                effective_user_requirement = f"{user_requirement}\n\n{shorts_suffix}"
            target_seconds = self.shorts_mode.get("target_duration_seconds")
            max_shots = self.shorts_mode.get("max_shots")
            if target_seconds or max_shots:
                extra_lines = []
                if target_seconds:
                    extra_lines.append(f"Target total duration: ~{target_seconds} seconds.")
                if max_shots:
                    extra_lines.append(f"Maximum shots: {max_shots}.")
                if extra_lines:
                    effective_user_requirement = f"{effective_user_requirement}\n" + "\n".join(extra_lines)

        resolution = resolve_s3_entities(
            texts=[idea, effective_user_requirement],
            working_dir=self.working_dir,
        )
        if resolution.get("context_block"):
            effective_user_requirement = f"{effective_user_requirement}\n\n{resolution['context_block']}"
        if resolution.get("reference_images"):
            existing_paths = {item["path"] for item in self.global_reference_images}
            for item in resolution["reference_images"]:
                if item["path"] not in existing_paths:
                    self.global_reference_images.append(item)

        # Director: creative brief for screenwriter and cinematography (Script2Video)
        director_brief = await self.video_director.direct(idea_or_script=idea, user_requirement=effective_user_requirement)
        effective_user_requirement = f"{effective_user_requirement}\n\n{director_brief.to_context_block()}"

        # Director reasoning: VideoDirector creative brief
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="video",
            director_name="VideoDirector",
            rationale=(
                "VideoDirector sets the creative brief for story, script, and each scene's Script2Video run: "
                "tone, pacing, visual style, and shot emphasis. The brief is passed via effective_user_requirement "
                "to Screenwriter and to each Script2VideoPipeline. Shorts mode constrains shot count and duration. "
                "Content format (live-action/animated), audience, and trends shape the direction."
            ),
            inputs={
                "idea": (idea or "")[:150],
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "shorts_mode": self.shorts_mode.get("enabled", False),
            },
            outputs={"director_brief": "In effective_user_requirement for Screenwriter and each Script2Video."},
        )

        story = await self.develop_story(idea=idea, user_requirement=effective_user_requirement)

        characters = None
        character_portraits_registry = None
        if resolution.get("characters") and resolution.get("portrait_registry"):
            characters = resolution["characters"]
            character_portraits_registry = resolution["portrait_registry"]
        else:
            characters = await self.extract_characters(story=story)
            character_portraits_registry = await self.generate_character_portraits(
                characters=characters,
                character_portraits_registry=None,
                style=style,
            )

        scene_scripts = await self.write_script_based_on_story(story=story, user_requirement=effective_user_requirement)
        if self.shorts_mode.get("enabled") and len(scene_scripts) > 1:
            print(f"⚠️ Shorts mode expects a single scene; trimming from {len(scene_scripts)} to 1.")
            scene_scripts = scene_scripts[:1]

        # Phase 1 reasoning: rationale behind the story and script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="video",
            phase_label="Phase 1: Story and script",
            content_type="script",
            rationale=(
                "The story is developed from the idea and user_requirement; the script is then written "
                "scene-by-scene. VideoDirector sets the creative brief; Screenwriter develops the story "
                "and script. In shorts mode, pacing and shot count are constrained. Characters are "
                "extracted from the story (or from S3 when resolved); character portraits are generated "
                "or loaded for visual consistency. Content format (live-action/animated), audience, and "
                "trends shape the narrative. This script drives each scene's Script2Video run."
            ),
            inputs={
                "idea": (idea or "")[:200],
                "user_requirement": (user_requirement or "")[:200],
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "shorts_mode": self.shorts_mode.get("enabled", False),
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
                "scene_scripts_count": len(scene_scripts),
            },
            outputs={
                "story.txt": "Developed story from idea.",
                "characters.json": "Extracted or S3-resolved characters.",
                "script.json": "Scene-by-scene script (list of scene strings).",
            },
        )

        # Cinematographer/picturization: delegated to Script2Video per scene
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="video",
            rationale=(
                "Cinematography and picturization are delegated to Script2VideoPipeline for each scene. "
                "Each scene_working_dir (scene_0, scene_1, ...) contains that run's storyboard, "
                "decompose_visual_descriptions, camera_tree, shots (frames and videos), and final_video. "
                "Director brief and effective_user_requirement are passed into each Script2Video call. "
                "S3 character compositing is used when resolution provided characters and portrait_registry."
            ),
            inputs={
                "style": style,
                "content_format": content_format,
                "scene_scripts_count": len(scene_scripts),
                "director_guidance": director_brief.to_context_block()[:200] if director_brief else None,
            },
            outputs={
                "scene_N/": "Per-scene Script2Video run: storyboard, camera tree, shots/, final video.",
                "final_video.mp4": "Concatenated scene videos.",
            },
        )

        all_video_paths = []

        for idx, scene_script in enumerate(scene_scripts):
            scene_working_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_working_dir, exist_ok=True)
            
            # RESUME CHECK: Scene Video (OR restitch_only)
            scene_video_path = os.path.join(scene_working_dir, "final_video.mp4")
            if (os.path.exists(scene_video_path) and not self.force_regenerate) or restitch_only:
                if os.path.exists(scene_video_path):
                    self.logger.info(f"  Resuming/Restitching scene {idx} from: {scene_video_path}")
                    all_video_paths.append(scene_video_path)
                    continue
                elif restitch_only:
                    self.logger.warning(f"  Restitch mode: Scene video NOT found at {scene_video_path}. Skipping.")
                    continue

            script2video_pipeline = Script2VideoPipeline(
                chat_model=self.chat_model,
                image_generator=self.image_generator,
                video_generator=self.video_generator,
                working_dir=scene_working_dir,
                global_reference_images=self.global_reference_images,
                force_regenerate=self.force_regenerate,
                shorts_mode=self.shorts_mode,
                run_id=None,  # Don't create new run_id for scene-level pipeline
                use_run_id=False,  # Use working_dir directly without run_id subfolder
                pipeline_kind=self.pipeline_kind,
            )
            
            # Enable character compositing if portraits are available
            if character_portraits_registry:
                script2video_pipeline.use_character_compositing = True
                script2video_pipeline._extract_character_portrait_paths(character_portraits_registry)
            
            final_video_path = await script2video_pipeline(
                script=scene_script,
                user_requirement=effective_user_requirement,
                style=style,
                characters=characters,
                character_portraits_registry=character_portraits_registry,
            )
            all_video_paths.append(final_video_path)

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path) and not self.force_regenerate and not restitch_only:
            print(f"🚀 Skipped concatenating videos, already exists.")
        else:
            print(f"🎬 Starting concatenating videos...")
            
            # Check for music segments from scene-level audio plans
            music_segments = {}
            for idx in range(len(scene_scripts)):
                scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
                audio_plan_path = os.path.join(scene_dir, "audio_plan.json")
                if os.path.exists(audio_plan_path):
                    try:
                        from agents.producers.audio import AudioPlanner
                        from utils.pipeline.music_generator import generate_music_segments_from_plan
                        audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind=self.pipeline_kind)
                        scene_audio_plan = audio_planner.load_audio_plan(audio_plan_path)
                        if scene_audio_plan:
                            scene_music = await generate_music_segments_from_plan(
                                audio_plan=scene_audio_plan,
                                working_dir=scene_dir,
                                force_regenerate=self.force_regenerate,
                            )
                            # Map to global scene index
                            for (s_idx, shot_idx), music_info in scene_music.items():
                                music_segments[(idx, shot_idx)] = music_info
                    except Exception as e:
                        self.logger.warning(f"Failed to load/generate music from scene {idx}: {e}")
            
            # Build video clips list with music segments inserted
            final_video_clips = []
            for idx, v_path in enumerate(all_video_paths):
                if os.path.exists(v_path):
                    final_video_clips.append(VideoFileClip(v_path))
                
                # Check if there's a music segment after this scene
                music_key = (idx, 0)  # scene_idx, shot_idx
                if music_key in music_segments:
                    music_info = music_segments[music_key]
                    music_path = music_info["audio_path"]
                    
                    if os.path.exists(music_path):
                        from moviepy import AudioFileClip, ColorClip
                        music_audio = AudioFileClip(music_path)
                        duration = music_audio.duration
                        music_video = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=duration).set_audio(music_audio)
                        temp_music_video = os.path.join(self.working_dir, f"music_segment_scene_{idx}.mp4")
                        music_video.write_videofile(temp_music_video, codec="libx264", audio_codec="aac", fps=24)
                        music_video.close()
                        music_audio.close()
                        if os.path.exists(temp_music_video):
                            final_video_clips.append(VideoFileClip(temp_music_video))
                        self.logger.info(f"Inserted music segment after scene {idx}: {music_info['music_style']}")
            
            if not final_video_clips:
                # Fallback to original behavior if no clips
                final_video_clips = [VideoFileClip(v_path) for v_path in all_video_paths if os.path.exists(v_path)]
            
            if final_video_clips:
                final_video = concatenate_videoclips(final_video_clips)
                
                # Generate and add audio
                audio_path = os.path.join(self.working_dir, "final_audio.mp3")
                from utils.pipeline.audio_helper import generate_audio_for_video, add_audio_to_video
                
                # Collect audio descriptions from scene scripts if available
                audio_descriptions = []
                for idx, scene_script in enumerate(scene_scripts):
                    # Try to load shot descriptions from scene directory
                    scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
                    shots_dir = os.path.join(scene_dir, "shots")
                    if os.path.exists(shots_dir):
                        import json
                        from interfaces.content.shot_description import ShotDescription
                        for shot_idx in sorted([int(d) for d in os.listdir(shots_dir) if d.isdigit()]):
                            shot_desc_path = os.path.join(shots_dir, str(shot_idx), "shot_description.json")
                            if os.path.exists(shot_desc_path):
                                try:
                                    with open(shot_desc_path, 'r') as f:
                                        shot_desc = ShotDescription.model_validate(json.load(f))
                                        if shot_desc.audio_desc and shot_desc.audio_desc.strip():
                                            audio_descriptions.append(shot_desc.audio_desc)
                                except Exception:
                                    pass
                
                # Generate audio
                generated_audio = await generate_audio_for_video(
                    video_duration=final_video.duration,
                    audio_descriptions=audio_descriptions if audio_descriptions else None,
                    output_path=audio_path,
                    force_regenerate=self.force_regenerate,
                )
                
                # Add audio to video if generated
                if generated_audio and os.path.exists(generated_audio):
                    if add_audio_to_video(final_video, generated_audio, final_video_path):
                        self.logger.info(f"Final video with audio saved: {final_video_path}")
                    else:
                        # Fallback: save without audio
                        final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
                        self.logger.warning("Failed to add audio, saved video without audio")
                else:
                    # Save video without audio
                    final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
                    self.logger.info(f"Final video saved without audio: {final_video_path}")
                
                for c in final_video_clips: c.close()
                final_video.close()
                print(f"☑️ Concatenated videos, saved to {final_video_path}.")
            else:
                print("⚠️ No valid video clips found for concatenation.")

        # Calculate total duration
        total_duration_seconds = 0
        try:
            final_clip = VideoFileClip(final_video_path)
            total_duration_seconds = int(final_clip.duration)
            final_clip.close()
        except Exception:
            total_duration_seconds = 30  # Default estimate

        # Generate monetization plan
        is_shorts = self.shorts_mode.get("enabled", False)
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=f"Video from idea: {idea[:50]}...",
            description=story[:500] if story else idea,
            audience=audience or "General",
            duration_seconds=total_duration_seconds,
            genre="Entertainment",
            is_shorts=is_shorts,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        if final_video_path and total_duration_seconds >= 120:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = json.dumps(scene_scripts, ensure_ascii=False)
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_video_path,
                script_content=script_full_text,
                total_duration_seconds=total_duration_seconds,
                content_type="video"
            )

        # Save output metadata
        output_metadata = {
            "run_id": self.run_id,
            "idea": idea,
            "user_requirement": user_requirement,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "content_format": content_format,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "ideation_result": ideation_result.model_dump() if ideation_result else None,
            "video_path": final_video_path,
            "duration_seconds": total_duration_seconds,
            "is_shorts": is_shorts,
            "viral_shorts": viral_shorts,
            "monetization_plan": monetization_plan.model_dump(),
        }
        with open(os.path.join(self.working_dir, "output.json"), "w", encoding="utf-8") as f:
            json.dump(output_metadata, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"]) # Sync logic and frames, excluding bulky final videos if desired or include all
        
        return output_metadata
