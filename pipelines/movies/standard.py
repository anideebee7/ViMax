"""
Idea to Movie Video Pipeline

Generates full-length movie videos with three-act structure,
scene-by-scene visuals, character consistency, and monetization recommendations.

Supports S3 character resolution for consistent character appearances
via post-processing compositing throughout the entire movie.
"""
import json
import logging
import os
import re
import shutil
import asyncio
from typing import Optional, Dict, Any, List, Literal

import yaml

from configs.constants.content_constants import (
    clamp_runtime,
    MOVIE_RUNTIME_MIN_MINUTES,
    MOVIE_RUNTIME_MAX_MINUTES,
    CONTENT_FORMAT_LIVE_ACTION,
    CONTENT_FORMAT_ANIMATED,
)
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing import Screenwriter
from agents.producers.analysis import CharacterExtractor
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.directors.film import MovieDirector
from agents.planners.strategy import IdeationEngine
from agents.producers.visuals import StoryboardArtist
from agents.producers.analysis.structure_supervisor import StructureSupervisor
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from pipelines.base.script import Script2VideoPipeline
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.media.image import (
    composite_character_on_image,
    composite_multiple_characters,
    composite_prop_on_image,
    composite_multiple_props,
    get_character_position_from_description,
    get_character_scale_from_shot_type,
    get_prop_position_from_description,
    get_prop_scale_from_context,
)
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression
from utils.pipeline.checkpoint import CheckpointManager
from utils.media.video import concat_videos, ffmpeg_concat_videos
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext


class MoviePipeline:
    """Pipeline to generate full-length movie scripts."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/movie",
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
            pipeline_name="movie",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        # Feature film mode for screenwriter (max_scenes supports up to 200-min films)
        film_mode = {
            "enabled": True,
            "format": "feature_film",
            "max_scenes": 200,
            "target_duration_minutes": 90,
        }
        self.screenwriter = Screenwriter(chat_model=self.chat_model, shorts_mode=film_mode, pipeline_kind="feature_film")
        self.movie_director = MovieDirector(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="feature_film")
        self.structure_supervisor = StructureSupervisor(chat_model=self.chat_model)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="feature_film")
        self.checkpoint = CheckpointManager(
            working_dir=self.working_dir,
            run_id=self.run_id,
            pipeline_type="movie"
        )
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="movie", run_id=self.run_id, local_dir=self.working_dir)

    async def _generate_scene_frame(
        self,
        scene_content: str,
        style: str,
        content_format: str,
        output_path: str,
        character_portraits: Optional[Dict[str, Any]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        scene_id: Optional[str] = None,
        location: Optional[str] = None,
        shot_idx: Optional[int] = None,
    ) -> Optional[str]:
        """Generate a storyboard frame for a movie scene with character compositing."""
        if not self.image_generator:
            return None
        
        format_hint = "cinematic live-action" if content_format == CONTENT_FORMAT_LIVE_ACTION else "animated, stylized"
        
        # Detect characters in scene
        visible_chars = []
        if characters and character_portraits:
            for char in characters:
                char_name = char.identifier_in_scene
                if not char_name:
                    continue
                pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                if re.search(pattern, scene_content):
                    visible_chars.append(char)
        
        # Get establishment frame and previous shot reference from continuity memory
        establishment_frame = None
        previous_shot_ref = None
        if location:
            establishment_frame = self.continuity_memory.location_establishment_frames.get(location)
        if self.continuity_memory.previous_shot_frame:
            previous_shot_ref = self.continuity_memory.previous_shot_frame
        
        # CHARACTER CONSISTENCY FIX:
        # We follow a dual-track generation process:
        # 1. RAW Frame: AI generates the full scene with characters "gelled" in (lighting, etc.)
        # 2. STORYBOARD Frame: Exact S3 portraits composited on a clean background.
        
        # --- TRACK 1: BACKGROUND GENERATION (Clean Environment) ---
        bg_visual_desc = scene_content[:500]
        if visible_chars:
            for char in visible_chars:
                bg_visual_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_visual_desc)
        
        bg_prompt = f"""Movie background scenery. {bg_visual_desc}.
Style: {style}, {format_hint}, cinematic composition, professional film quality.
EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures.
High production value, dramatic lighting. No text."""
        
        try:
            debug_dir = os.path.join(os.path.dirname(output_path), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_bg_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(bg_prompt)

            # Use establishment frame or previous shot as reference for background consistency
            bg_refs = []
            if establishment_frame and os.path.exists(establishment_frame):
                bg_refs.append(establishment_frame)
            elif previous_shot_ref and os.path.exists(previous_shot_ref):
                bg_refs.append(previous_shot_ref)

            bg_image = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=bg_refs if bg_refs else None,
            )
            bg_image.save(output_path)
            
            # --- TRACK 2: COMPOSITE CHARACTERS (S3 Portraits) ---
            if visible_chars and character_portraits:
                self._composite_characters_on_frame(
                    frame_path=output_path, 
                    visible_characters=visible_chars,
                    character_portraits=character_portraits,
                    scene_content=scene_content,
                )
            
            # --- TRACK 3: RAW GENERATION (Gelled Characters) ---
            raw_output_path = output_path.replace(".png", "_raw.png")
            char_desc_parts = []
            for char in visible_chars:
                if char.static_features:
                    char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
            char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
            
            # Add view and expression guidance to prompt
            view_instruction = ""
            expression_instruction = ""
            if visible_chars:
                # Get view and expression from shot description
                view = get_character_view_for_shot(scene_content)
                expression = get_character_expression_for_shot(scene_content)
                view_instruction = f" Camera angle: {view.value} view."
                expression_instruction = f" Character expressions: {expression.value}."
            
            raw_prompt = f"""Movie scene frame. {scene_content[:500]}.{char_context}{view_instruction}{expression_instruction}
Style: {style}, {format_hint}, cinematic composition, professional film quality.
High quality animation frame, vibrant colors, expressive characters gelled into scene.
Proper lighting and shadows. Blend characters naturally into environment. No text, no collages."""
            
            # Include ALL character portraits (not just 2) for multi-character scenes
            raw_refs = [output_path]  # Start with composite frame
            if visible_chars and character_portraits:
                for char in visible_chars:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits:
                        # Use view/expression selector to get correct portrait
                        view = get_character_view_for_shot(scene_content)
                        expression = get_character_expression_for_shot(scene_content)
                        
                        # Try to get view-specific portrait
                        view_data = character_portraits[char_id].get(view.value, {})
                        if isinstance(view_data, dict):
                            # Try expression-specific path
                            expr_data = view_data.get(expression.value, {})
                            if isinstance(expr_data, dict):
                                path = expr_data.get("path")
                            else:
                                path = expr_data if isinstance(expr_data, str) else None
                            if not path:
                                path = view_data.get("path")
                        else:
                            path = str(view_data) if view_data else None
                        
                        # Fallback to front view if view-specific not found
                        if not path:
                            front_info = character_portraits[char_id].get("front", {})
                            path = front_info.get("path") if isinstance(front_info, dict) else str(front_info) if front_info else None
                        
                        if path and os.path.exists(path) and path not in raw_refs:
                            raw_refs.append(path)
            
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_raw_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(raw_prompt)

            raw_image = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                strength=0.55,  # Blend with composite
            )
            raw_image.save(raw_output_path)
            
            # Update continuity memory
            if shot_idx is not None:
                visible_char_ids = [c.identifier_in_scene for c in visible_chars]
                self.continuity_memory.update_for_shot(
                    shot_idx=shot_idx,
                    frame_path=raw_output_path if os.path.exists(raw_output_path) else output_path,
                    scene_id=scene_id,
                    location=location,
                    visible_characters=visible_char_ids,
                    visible_props=None,
                    shot_description=scene_content,
                )
            
            # Register establishment frame for location
            if location and location not in self.continuity_memory.location_establishment_frames:
                self.continuity_memory.location_establishment_frames[location] = raw_output_path if os.path.exists(raw_output_path) else output_path
            
            return raw_output_path if os.path.exists(raw_output_path) else output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate scene frame: {e}")
            return None

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        character_portraits: Dict[str, Any],
        scene_content: str,
    ) -> None:
        """Composite character portraits onto a scene frame with view/expression selection."""
        if not visible_characters or not os.path.exists(frame_path):
            return
        
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            if char_id in character_portraits:
                # Use view/expression selector to get correct portrait
                view = get_character_view_for_shot(scene_content)
                expression = get_character_expression_for_shot(scene_content)
                
                # Try to get view-specific portrait
                view_data = character_portraits[char_id].get(view.value, {})
                if isinstance(view_data, dict):
                    # Try expression-specific path
                    expr_data = view_data.get(expression.value, {})
                    if isinstance(expr_data, dict):
                        path = expr_data.get("path")
                    else:
                        path = expr_data if isinstance(expr_data, str) else None
                    if not path:
                        path = view_data.get("path")
                else:
                    path = str(view_data) if view_data else None
                
                # Fallback to front view if view-specific not found
                if not path:
                    front_info = character_portraits[char_id].get("front", {})
                    path = front_info.get("path") if isinstance(front_info, dict) else str(front_info) if front_info else None
                
                if path and os.path.exists(path):
                    portraits_to_composite.append({"path": path, "name": char_id})
        
        if not portraits_to_composite:
            return
        
        try:
            if len(portraits_to_composite) == 1:
                position = get_character_position_from_description(scene_content, portraits_to_composite[0]["name"])
                scale = get_character_scale_from_shot_type(scene_content)
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=portraits_to_composite[0]["path"],
                    output_path=frame_path,
                    position=position,
                    scale_factor=min(scale, 0.5),
                    blend_mode="soft",
                )
            else:
                # Include ALL characters, not just first 3
                paths = [p["path"] for p in portraits_to_composite]
                positions = [get_character_position_from_description(scene_content, p["name"]) for p in portraits_to_composite]
                scales = [min(get_character_scale_from_shot_type(scene_content), 0.4) for _ in portraits_to_composite]
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=paths,
                    output_path=frame_path,
                    positions=positions,
                    scale_factors=scales,
                )
        except Exception as e:
            self.logger.warning(f"Failed to composite characters: {e}")

    async def _generate_scene_video(
        self,
        scene_content: str,
        style: str,
        content_format: str,
        output_path: str,
        first_frame_path: Optional[str] = None,
        character_portraits: Optional[Dict[str, Any]] = None,
        duration_seconds: int = 8,
    ) -> Optional[str]:
        """Generate a video for a movie scene."""
        if not self.video_generator:
            return None
        
        format_hint = "cinematic live-action" if content_format == CONTENT_FORMAT_LIVE_ACTION else "animated, stylized"
        
        prompt = f"""Movie scene. {scene_content[:500]}
Style: {style}, {format_hint}, cinematic composition, high production quality.
Smooth camera movement, dramatic lighting, professional film quality."""
        
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

    @classmethod
    def init_from_config(
        cls,
        config_path: str,
        run_id: Optional[str] = None,
        working_dir: Optional[str] = None,
    ):
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

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir or resolve from config
        resolved_working_dir = working_dir or (_resolve_path(config["working_dir"]) or config["working_dir"])

        return cls(
            chat_model=chat_model,
            working_dir=resolved_working_dir,
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
        )

    async def __call__(
        self,
        premise: Optional[str] = None,
        genre: str = "drama",
        target_runtime_minutes: int = 90,
        audience: Optional[str] = None,
        style: str = "cinematic",
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        content_format: Literal["live_action", "animated"] = CONTENT_FORMAT_LIVE_ACTION,
        generate_scene_frames: bool = True,
        generate_videos: bool = True,
        max_scenes_to_generate: int = 20,
        restitch_only: bool = False,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_ids: Optional[List[str]] = None,
        s3_characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a full-length movie video from a premise.

        Args:
            premise: Film premise/logline (optional if auto_ideate=True)
            genre: Film genre (drama, action, comedy, sci-fi, horror, romance, etc.)
            target_runtime_minutes: Target runtime (60-200 minutes)
            audience: Target audience (G, PG, PG-13, R, teens, adults, family, etc.)
            style: Visual/narrative style
            trendy: Whether to incorporate trending themes
            auto_ideate: If True, automatically generate film premise
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
            content_format: 'live_action' or 'animated'
            generate_scene_frames: Whether to generate storyboard frames
            generate_videos: Whether to generate scene videos
            max_scenes_to_generate: Maximum number of scenes to generate visuals for (to limit cost)
            brand_id: S3 brand ID for brand context
            game_id: S3 game ID for game context
            character_ids: S3 character IDs to use in the movie
            s3_characters: Pre-built CharacterInScene objects
            character_portraits_registry: Pre-built character portrait registry

        Returns:
            Dictionary with story, acts, characters, scene frames, videos, and monetization plan
        """
        target_runtime_minutes = clamp_runtime(
            target_runtime_minutes, MOVIE_RUNTIME_MIN_MINUTES, MOVIE_RUNTIME_MAX_MINUTES
        )
        output_json_path = os.path.join(self.working_dir, "movie_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate and not restitch_only:
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
            if brand_id: texts.append(f"@brand:{brand_id}")
            elif brand_hint: texts.append(brand_hint)
            if game_id: texts.append(f"@game:{game_id}")
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
                                            with open(metadata_path, "r") as mf:
                                                meta = json.load(mf)
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
            trend_context = await self.trend_analyzer.fetch_trends(category="film")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating movie in {ideation_mode} mode...")
            
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
                    audience=audience or "General audiences",
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            premise = ideation_result.idea
            audience = audience or ideation_result.target_audience
            genre = genre or ideation_result.tone or "drama"
            
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_result.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated movie premise: {ideation_result.title}")

        if not premise:
            raise ValueError("Either provide a 'premise' or set 'auto_ideate=True'")

        # Scene guidance for long runtimes (up to 200 min)
        scenes_hint = (
            f"Use approximately 1 to 1.5 scenes per minute (e.g. {max(60, int(target_runtime_minutes * 0.6))}–{min(200, int(target_runtime_minutes * 1.2))} scenes for this runtime) for proper pacing and coverage."
            if target_runtime_minutes > 90
            else ""
        )
        format_note = (
            "Content format: ANIMATED. Write for animation: stylized, expressive action; no live-action-only constraints; imaginative visuals and character expressions."
            if content_format == CONTENT_FORMAT_ANIMATED
            else "Content format: live-action."
        )

        # Build user requirement for feature film
        user_requirement = f"""
Genre: {genre}
Style: {style}
Target audience: {audience or 'General audiences'}
Target runtime: {target_runtime_minutes} minutes
{format_note}
Format: Feature film with classic three-act structure:
- Act 1 (Setup): ~25% - Introduce world, characters, inciting incident
- Act 2 (Confrontation): ~50% - Rising action, midpoint, complications
- Act 3 (Resolution): ~25% - Climax, falling action, resolution
Include character arcs, subplots, and thematic depth.
{scenes_hint}
"""
        if trend_context_block:
            user_requirement = f"{user_requirement}\n\n{trend_context_block}"

        # Director: creative brief for screenwriter
        director_brief = await self.movie_director.direct(
            premise=premise,
            genre=genre,
            target_runtime_minutes=target_runtime_minutes,
            style=style,
            audience=audience,
            additional_context=f"{format_note}\n{trend_context_block or ''}".strip() or None,
        )
        user_requirement = f"{user_requirement}\n\n{director_brief.to_context_block()}"

        # Director reasoning: MovieDirector creative brief
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="movie",
            director_name="MovieDirector",
            rationale=(
                "MovieDirector sets the creative brief for the feature: tone, pacing, three-act structure, "
                "and visual style. The brief aligns premise, genre, target_runtime, format (live-action/animated), "
                "and audience so the Screenwriter delivers a coherent, properly paced screenplay. Trends can "
                "influence thematic choices when enabled."
            ),
            inputs={
                "premise": premise[:150],
                "genre": genre,
                "target_runtime_minutes": target_runtime_minutes,
                "style": style,
                "audience": audience,
                "content_format": content_format,
            },
            outputs={"director_brief": "Feeds into user_requirement for Screenwriter."},
        )

        # Develop story
        self.logger.info("Developing story...")
        story_path = os.path.join(self.working_dir, "story.txt")
        
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "story_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(f"Idea: {premise}\nRequirement: {user_requirement}")

        story = await self.screenwriter.develop_story(idea=premise, user_requirement=user_requirement)
        with open(story_path, "w", encoding="utf-8") as f:
            f.write(story)

        # MEGA SCALE: Develop movie outline (chapters)
        self.logger.info(f"Developing movie outline for {target_runtime_minutes} minutes...")
        outline = await self.screenwriter.develop_movie_outline(story=story, target_runtime_minutes=target_runtime_minutes)
        
        # PACING VERIFICATION: Review outline structure
        self.logger.info("Verifying movie structure and pacing...")
        pacing_analysis = await self.structure_supervisor.analyze_pacing(
            outline=outline,
            target_runtime_minutes=target_runtime_minutes,
            genre=genre
        )
        if not pacing_analysis.is_pacing_correct:
            self.logger.warning(f"Pacing issues detected (Score: {pacing_analysis.pacing_score}). Attempting shift...")
            # In a real scenario, we might force a rewrite here. 
            # For now, we log the bottlenecks and required shifts.
            self.logger.warning(f"Bottlenecks: {pacing_analysis.bottlenecks}")
            self.logger.warning(f"Required Shifts: {pacing_analysis.required_shifts}")

        outline_path = os.path.join(self.working_dir, "outline.json")
        with open(outline_path, "w", encoding="utf-8") as f:
            json.dump(outline, f, indent=2)

        # Extract characters
        self.logger.info("Extracting characters...")
        characters = await self.character_extractor.extract_characters(story)
        characters_path = os.path.join(self.working_dir, "characters.json")
        with open(characters_path, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)

        # MEGA SCALE: Write script chapter-by-chapter
        self.logger.info("Writing script chapter-by-chapter...")
        all_scenes = []
        for chapter in outline:
            self.logger.info(f"Writing script for Chapter {chapter['chapter_number']}: {chapter['title']}...")
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"chapter_{chapter['chapter_number']}_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Chapter: {chapter}\nContext: {story[:1000]}\nRequirement: {user_requirement}")

            chapter_scenes = await self.screenwriter.write_script_for_chapter(
                story_context=story,
                chapter_info=chapter,
                user_requirement=user_requirement,
            )
            all_scenes.extend(chapter_scenes)
        
        script = all_scenes
        script_path = os.path.join(self.working_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # Plan audio requirements for all scenes
        audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not self.force_regenerate:
            self.logger.info("Loading existing audio plan...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None:
            self.logger.info("Planning audio requirements for movie scenes...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert script scenes to Scene objects for audio planning
                scene_objects = []
                for idx, scene_data in enumerate(script[:max_scenes_to_generate]):
                    scene_content = scene_data if isinstance(scene_data, str) else scene_data.get("content", str(scene_data))
                    scene_obj = Scene(
                        idx=idx,
                        is_last=(idx == len(script) - 1),
                        environment=EnvironmentInScene(
                            slugline=scene_data.get("location", "UNKNOWN") if isinstance(scene_data, dict) else "UNKNOWN",
                            description=scene_data.get("description", "") if isinstance(scene_data, dict) else "",
                        ),
                        characters=all_characters,
                        script=scene_content,
                    )
                    scene_objects.append(scene_obj)
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,  # MoviePipeline doesn't have shot-level info yet
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

        # Phase 1 reasoning: rationale behind the story and script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="movie",
            phase_label="Phase 1: Story and script",
            content_type="script",
            rationale=(
                "The feature script follows a three-act structure (Setup ~25%, Confrontation ~50%, Resolution ~25%). "
                "MovieDirector provides the creative brief; Screenwriter develops the story from the premise "
                "and then writes scene-by-scene script. CharacterExtractor pulls characters from the story "
                "for consistency. Genre, runtime, format (live-action/animated), and trends shape tone, "
                "pacing, and thematic choices."
            ),
            inputs={
                "premise": premise[:200] + "…" if len(premise) > 200 else premise,
                "genre": genre,
                "target_runtime_minutes": target_runtime_minutes,
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={
                "story.txt": "Developed story from premise.",
                "characters.json": "Extracted characters from story.",
                "script.json": "Scene-by-scene screenplay.",
            },
        )

        # Build character list combining extracted and S3 characters
        all_characters: List[CharacterInScene] = local_s3_characters.copy()
        for char in characters:
            if not any(c.identifier_in_scene == char.identifier_in_scene for c in all_characters):
                all_characters.append(char)
                # Generate character portrait if we have image generator and no portrait yet
                if self.image_generator and char.identifier_in_scene not in local_character_portraits:
                    char_portrait_dir = os.path.join(self.working_dir, "character_portraits")
                    os.makedirs(char_portrait_dir, exist_ok=True)
                    char_portrait_path = os.path.join(char_portrait_dir, f"{char.identifier_in_scene.replace(' ', '_')}.png")
                    
                    if not os.path.exists(char_portrait_path) or self.force_regenerate:
                        try:
                            format_hint = "photorealistic" if content_format == CONTENT_FORMAT_LIVE_ACTION else "stylized animated"
                            prompt = f"Character portrait. {char.static_features}. {format_hint}, {style}, professional quality."
                            
                            # Save debug prompt
                            debug_dir = os.path.join(char_portrait_dir, "debug")
                            os.makedirs(debug_dir, exist_ok=True)
                            with open(os.path.join(debug_dir, f"{char.identifier_in_scene.replace(' ', '_')}_prompt.txt"), "w", encoding="utf-8") as f:
                                f.write(prompt)

                            image_output = await self.image_generator.generate_single_image(prompt=prompt)
                            image_output.save(char_portrait_path)
                            local_character_portraits[char.identifier_in_scene] = {
                                "front": {"path": char_portrait_path, "description": f"Portrait of {char.identifier_in_scene}"}
                            }
                        except Exception as e:
                            self.logger.warning(f"Failed to generate portrait for {char.identifier_in_scene}: {e}")
        
        # RESUME CHECK: Try to sync from S3 if local folder is missing/incomplete
        if not os.path.exists(self.working_dir):
            self.logger.info(f"Attempting to sync run state from S3 for run_id: {self.run_id}")
            if self.memory.sync_from_s3():
                self.logger.info("✅ Synced run state from S3")
                self.continuity_memory.load()
            else:
                self.logger.info("No existing run found in S3, starting fresh")

        # RESUME CHECK: Load checkpoint and check if run can be resumed
        checkpoint = self.checkpoint.load()
        can_resume = self.checkpoint.can_resume()
        
        if can_resume and not self.force_regenerate:
            resume_info = self.checkpoint.get_resume_info()
            self.logger.info(f"🔄 Resuming incomplete run (status: {resume_info['status']})")
            self.logger.info(f"   Completed scenes: {resume_info['completed_scenes']}")
            if resume_info.get('errors'):
                self.logger.warning(f"   Previous errors: {resume_info['errors']}")
        elif not checkpoint:
            self.checkpoint.initialize(metadata={
                "premise": premise,
                "genre": genre,
                "target_runtime_minutes": target_runtime_minutes,
            })

        # Generate scene frames and videos
        scene_frames: Dict[str, str] = {}
        scene_videos: Dict[str, str] = {}
        scenes_dir = os.path.join(self.working_dir, "scenes")
        os.makedirs(scenes_dir, exist_ok=True)
        
        if generate_scene_frames or generate_videos:
            scenes_to_process = script[:max_scenes_to_generate] if isinstance(script, list) else []
            self.logger.info(f"Generating frames/videos for {len(scenes_to_process)} scenes in parallel (max: {max_scenes_to_generate})...")
            
            # Use a semaphore to limit concurrent AI generations (avoid rate limits/OOM)
            semaphore = asyncio.Semaphore(5)
            
            async def process_scene(i, scene_data):
                async with semaphore:
                    scene_num = i + 1
                    scene_content = scene_data if isinstance(scene_data, str) else json.dumps(scene_data, ensure_ascii=False)
                    scene_frame_path = os.path.join(scenes_dir, f"scene_{scene_num:03d}_frame.png")
                    scene_video_path = os.path.join(scenes_dir, f"scene_{scene_num:03d}_video.mp4")
                    
                    # RESUME CHECK: Skip if scene already completed
                    if self.checkpoint.is_scene_completed(scene_num) and not self.force_regenerate:
                        if os.path.exists(scene_video_path):
                            self.logger.info(f"  Resuming: Scene {scene_num} already completed")
                            scene_videos[f"scene_{scene_num}"] = scene_video_path
                            if os.path.exists(scene_frame_path):
                                scene_frames[f"scene_{scene_num}"] = scene_frame_path
                            return
                    
                    # RESUME CHECK: Scene Video (OR restitch_only)
                    if (os.path.exists(scene_video_path) and not self.force_regenerate) or restitch_only:
                        if restitch_only and not os.path.exists(scene_video_path):
                            self.logger.warning(f"  Restitch mode: Scene video NOT found at {scene_video_path}. Skipping.")
                            return
                        
                        self.logger.info(f"  Resuming/Restitching from existing scene video: {scene_video_path}")
                        scene_videos[f"scene_{scene_num}"] = scene_video_path
                        if os.path.exists(scene_frame_path):
                            scene_frames[f"scene_{scene_num}"] = scene_frame_path
                        # Mark as completed in checkpoint
                        self.checkpoint.complete_scene(scene_num, output_files=[scene_video_path])
                        return
                    
                    # Start scene in checkpoint
                    self.checkpoint.start_scene(scene_num)

                    try:
                        frame_path = None
                        scene_num = i + 1
                        
                        # RESUME CHECK: Skip frame generation if already exists and checkpointed
                        if generate_scene_frames:
                            if os.path.exists(scene_frame_path) and not self.force_regenerate:
                                frame_path = scene_frame_path
                                # Check if we have raw frame too
                                raw_frame_path = scene_frame_path.replace(".png", "_raw.png")
                                if os.path.exists(raw_frame_path):
                                    frame_path = raw_frame_path
                            elif not self.checkpoint.is_shot_completed(scene_num, 0):  # Scene frame is shot 0
                                # Extract location from scene if available
                                location = None
                                if isinstance(scene_data, dict):
                                    location = scene_data.get("location")
                                scene_id = f"scene_{scene_num}"
                                
                                # Track shot (frame generation)
                                self.checkpoint.start_shot(scene_num, 0)
                                
                                frame_path = await self._generate_scene_frame(
                                    scene_content=scene_content,
                                    style=style,
                                    content_format=content_format,
                                    output_path=scene_frame_path,
                                    character_portraits=local_character_portraits,
                                    characters=all_characters,
                                    scene_id=scene_id,
                                    location=location or "Default Location",
                                    shot_idx=i,
                                )
                                
                                # Mark shot as completed
                                raw_frame_path = scene_frame_path.replace(".png", "_raw.png")
                                self.checkpoint.complete_shot(
                                    scene_num, 0,
                                    image_path=scene_frame_path,
                                    raw_image_path=raw_frame_path if os.path.exists(raw_frame_path) else None,
                                )

                        if frame_path:
                            scene_frames[f"scene_{scene_num}"] = frame_path
                        
                        # RESUME CHECK: Skip video generation if already exists and checkpointed
                        if generate_videos:
                            if os.path.exists(scene_video_path) and not self.force_regenerate:
                                scene_videos[f"scene_{scene_num}"] = scene_video_path
                            elif not self.checkpoint.is_shot_completed(scene_num, 1):  # Scene video is shot 1
                                # Track shot (video generation)
                                self.checkpoint.start_shot(scene_num, 1)
                                
                                video_path = await self._generate_scene_video(
                                    scene_content=scene_content,
                                    style=style,
                                    content_format=content_format,
                                    output_path=scene_video_path,
                                    first_frame_path=frame_path,
                                    character_portraits=local_character_portraits,
                                )
                                
                                if video_path:
                                    scene_videos[f"scene_{scene_num}"] = video_path
                                    # Mark shot as completed
                                    self.checkpoint.complete_shot(
                                        scene_num, 1,
                                        video_path=video_path,
                                    )
                        
                        # Mark scene as completed if both frame and video are done
                        if (not generate_scene_frames or frame_path) and (not generate_videos or scene_videos.get(f"scene_{scene_num}")):
                            output_files = []
                            if frame_path:
                                output_files.append(frame_path)
                            if scene_videos.get(f"scene_{scene_num}"):
                                output_files.append(scene_videos[f"scene_{scene_num}"])
                            self.checkpoint.complete_scene(scene_num, output_files=output_files)
                            
                    except Exception as e:
                        self.logger.error(f"Failed to process scene {scene_num}: {e}")
                        self.checkpoint.fail_scene(scene_num, str(e))

            # Launch all scene tasks
            tasks = [process_scene(i, sd) for i, sd in enumerate(scenes_to_process)]
            await asyncio.gather(*tasks)
        
        # Check for music segments that need to be inserted
        music_segments = {}
        if hasattr(self, 'audio_plan') and self.audio_plan:
            try:
                from utils.pipeline.music_generator import generate_music_segments_from_plan
                music_segments = await generate_music_segments_from_plan(
                    audio_plan=self.audio_plan,
                    working_dir=self.working_dir,
                    force_regenerate=self.force_regenerate,
                )
                if music_segments:
                    self.logger.info(f"Generated {len(music_segments)} music segments from audio plan")
            except Exception as e:
                self.logger.warning(f"Failed to generate music segments: {e}")
        
        # Concatenate all scene videos into final movie (with music segments inserted)
        final_video_path: Optional[str] = None
        if generate_videos and scene_videos:
            self.logger.info("Concatenating scene videos into segments and final movie...")
            final_video_path = os.path.join(self.working_dir, "movie_final.mp4")
            
            # Build video path list with music segments inserted
            final_video_paths = []
            for i in range(len(scenes_to_process)):
                scene_key = f"scene_{i+1}"
                if scene_key in scene_videos:
                    final_video_paths.append(scene_videos[scene_key])
                
                # Check if there's a music segment after this scene
                # Music segments are keyed by (scene_idx, shot_idx)
                # scene_idx is 0-based (i), but we use scene_num (i+1) for matching
                music_key = (i, 0)  # Use scene index as scene_idx
                if music_key in music_segments:
                    music_info = music_segments[music_key]
                    music_path = music_info["audio_path"]
                    
                    if os.path.exists(music_path):
                        from moviepy import AudioFileClip, ColorClip
                        
                        music_audio = AudioFileClip(music_path)
                        duration = music_audio.duration
                        
                        music_video = ColorClip(
                            size=(1920, 1080),
                            color=(0, 0, 0),
                            duration=duration
                        ).set_audio(music_audio)
                        
                        temp_music_video = os.path.join(self.working_dir, f"music_segment_scene_{i+1}.mp4")
                        music_video.write_videofile(temp_music_video, codec="libx264", audio_codec="aac", fps=24)
                        music_video.close()
                        music_audio.close()
                        
                        final_video_paths.append(temp_music_video)
                        self.logger.info(f"Inserted music segment after scene {i+1}: {music_info['music_style']}")
            
            if not final_video_paths:
                # Fallback: use original scene videos if no music segments
                final_video_paths = [scene_videos[f"scene_{i+1}"] for i in range(len(scenes_to_process)) if f"scene_{i+1}" in scene_videos]
            
            if len(final_video_paths) > 1:
                try:
                    # For very long movies, we group into 10-scene segments first
                    # This is safer for MoviePy fallback and general organization
                    segment_paths = []
                    segment_dir = os.path.join(self.working_dir, "segments")
                    os.makedirs(segment_dir, exist_ok=True)
                    
                    chunk_size = 10
                    for i in range(0, len(final_video_paths), chunk_size):
                        chunk = final_video_paths[i:i + chunk_size]
                        seg_path = os.path.join(segment_dir, f"segment_{i//chunk_size:03d}.mp4")
                        if not os.path.exists(seg_path) or self.force_regenerate:
                            # Use ffmpeg for segments if many, MoviePy otherwise
                            if len(chunk) > 5:
                                ffmpeg_concat_videos(chunk, seg_path)
                            else:
                                concat_videos(chunk, seg_path)
                        segment_paths.append(seg_path)
                    
                    # Final stitch of segments using ffmpeg (OOM safe)
                    ffmpeg_concat_videos(segment_paths, final_video_path)
                    
                    # Generate and add audio if video doesn't have audio
                    from moviepy import VideoFileClip
                    from utils.pipeline.audio_helper import ensure_video_has_audio
                    
                    # Collect audio descriptions from scenes
                    audio_descriptions = []
                    for i, scene_data in enumerate(scenes_to_process):
                        if scene_data and isinstance(scene_data, dict) and "content" in scene_data:
                            audio_descriptions.append(scene_data["content"][:200])
                    
                    await ensure_video_has_audio(
                        video_path=final_video_path,
                        audio_descriptions=audio_descriptions if audio_descriptions else None,
                        working_dir=self.working_dir,
                        force_regenerate=self.force_regenerate,
                    )
                    
                    self.logger.info(f"Final mega-movie saved: {final_video_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to concatenate videos: {e}")
                    # Last ditch attempt: direct ffmpeg of all videos
                    try:
                        ffmpeg_concat_videos(final_video_paths, final_video_path)
                        
                        # Generate and add audio if video doesn't have audio
                        from moviepy import VideoFileClip
                        from utils.pipeline.audio_helper import ensure_video_has_audio
                        
                        audio_descriptions = []
                        for i, scene_data in enumerate(scenes_to_process):
                            if scene_data and isinstance(scene_data, dict) and "content" in scene_data:
                                audio_descriptions.append(scene_data["content"][:200])
                        
                        await ensure_video_has_audio(
                            video_path=final_video_path,
                            audio_descriptions=audio_descriptions if audio_descriptions else None,
                            working_dir=self.working_dir,
                            force_regenerate=self.force_regenerate,
                        )
                    except Exception as e2:
                        self.logger.error(f"Direct ffmpeg concatenation also failed: {e2}")
                        final_video_path = None

        # Cinematographer/picturization reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="movie",
            rationale=(
                "Picturization: each scene gets a storyboard frame and video clip. Character consistency "
                "is achieved via post-processing compositing using S3 character portraits or generated "
                "character portraits. Characters mentioned in scene content are detected using regex word "
                "boundaries and composited onto frames. Scene videos are concatenated into the final movie. "
                "The director's visual_style and three-act structure drive scene composition. Genre, format "
                "(live-action/animated), and act_breakdown shape shot design and camera choices."
            ),
            inputs={
                "style": style,
                "content_format": content_format,
                "generate_scene_frames": generate_scene_frames,
                "generate_videos": generate_videos,
                "max_scenes_to_generate": max_scenes_to_generate,
                "s3_characters_used": list(local_character_portraits.keys()) if local_character_portraits else [],
            },
            outputs={
                "story.txt": "Story.",
                "script.json": "Scene-by-scene screenplay.",
                "characters.json": "Character list.",
                "character_portraits/": "Generated character portraits.",
                "scenes/*.png": "Storyboard frames per scene.",
                "scenes/*.mp4": "Video clips per scene.",
                "movie_final.mp4": "Concatenated final movie video.",
            },
        )

        # Calculate act breakdown
        total_scenes = len(script) if isinstance(script, list) else 1
        act_1_end = int(total_scenes * 0.25)
        act_2_end = int(total_scenes * 0.75)

        act_breakdown = {
            "act_1": {
                "name": "Setup",
                "scenes": list(range(1, act_1_end + 1)),
                "duration_percent": 25,
            },
            "act_2": {
                "name": "Confrontation",
                "scenes": list(range(act_1_end + 1, act_2_end + 1)),
                "duration_percent": 50,
            },
            "act_3": {
                "name": "Resolution",
                "scenes": list(range(act_2_end + 1, total_scenes + 1)),
                "duration_percent": 25,
            },
        }

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise(
            content_type="Feature Film / Movie",
            content_summary=f"Genre: {genre}\nPremise: {premise}\nRuntime: {target_runtime_minutes} minutes\n\nStory synopsis:\n{story[:1000]}...",
            audience=audience or "General audiences",
            duration=f"{target_runtime_minutes} minutes",
            genre=genre,
            additional_context=trend_context_block if trend_context_block else None,
        )

        # 11. Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        if final_video_path and target_runtime_minutes >= 2:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = json.dumps(script, ensure_ascii=False)
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_video_path,
                script_content=script_full_text,
                total_duration_seconds=target_runtime_minutes * 60,
                content_type="movie"
            )

        payload = {
            "run_id": self.run_id,
            "premise": premise,
            "genre": genre,
            "target_runtime_minutes": target_runtime_minutes,
            "content_format": content_format,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "story": story,
            "characters": [c.model_dump() for c in characters],
            "script": script,
            "act_breakdown": act_breakdown,
            "scene_frames": scene_frames,
            "scene_videos": scene_videos,
            "final_video_path": final_video_path,
            "viral_shorts": viral_shorts,
            "s3_characters_used": list(local_character_portraits.keys()) if local_character_portraits else [],
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        continuity_report = await self.continuity_supervisor.review_continuity(
            script=json.dumps(script, ensure_ascii=False),
            storyboard=all_scenes,
            video_metadata=payload
        )
        payload["continuity_report"] = continuity_report.model_dump()

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Mark run as completed
        self.checkpoint.mark_completed()

        # Sync all assets and metadata to S3 memory (including checkpoint and continuity state)
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])

        return payload
