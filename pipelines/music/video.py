"""
Idea to Music Video Pipeline

A comprehensive pipeline that takes an idea and generates a complete music video,
including lyrics, audio composition, visual concept, and the final video file.
Supports S3 characters and brand integration for consistent visual storytelling.
"""

import asyncio
import json
import logging
import os
import re
import shutil
from typing import Optional, Dict, Any, List, Literal, Tuple

import aiohttp
import yaml
import importlib
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from langchain.chat_models import init_chat_model

from agents.creative.audio.lyricist import Lyricist, LyricsDraft
from agents.creative.audio.composer import SongComposer, SongCompositionPlan
from agents.directors.audio.music import MusicVideoDirector, MusicVideoConcept
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from agents.producers.analysis import CharacterExtractor, PropExtractor
from agents.producers.visuals import StoryboardArtist, PropReferenceGenerator
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import (
    write_phase1_reasoning, 
    write_song_reasoning, 
    write_director_reasoning, 
    write_cinematographer_picturization_reasoning
)
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.pipeline.run_memory import RunMemory
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
    get_portrait_path_from_legacy_registry,
)
from interfaces.entities.character import CharacterInScene
from interfaces.entities.character_sheet import CharacterView, CharacterExpression
from interfaces.content.shot_description import ShotBriefDescription
from interfaces.output.image_output import ImageOutput
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from configs.constants.content_constants import is_kids_audience


class MusicVideoPipeline:
    """Comprehensive pipeline for generating a music video from an idea."""

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        audio_generator_primary,
        audio_generator_fallback,
        working_dir: str = ".working_dir/music_video",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.audio_generator_primary = audio_generator_primary
        self.audio_generator_fallback = audio_generator_fallback
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="music_video",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.lyricist = Lyricist(chat_model=self.chat_model)
        self.song_composer = SongComposer(chat_model=self.chat_model)
        self.music_video_director = MusicVideoDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.prop_extractor = PropExtractor(chat_model=self.chat_model)
        self.prop_reference_generator = PropReferenceGenerator(image_generator=self.image_generator)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="music_video")
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="music_video", run_id=self.run_id, local_dir=self.working_dir)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)

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

        chat_model_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
        chat_model = init_chat_model(**chat_model_args)

        # Rate limiters
        img_rpm = config.get("image_generator", {}).get("max_requests_per_minute")
        vid_rpm = config.get("video_generator", {}).get("max_requests_per_minute")
        aud_rpm = config.get("audio_generator_primary", {}).get("max_requests_per_minute")

        image_rate_limiter = RateLimiter(max_requests_per_minute=img_rpm) if img_rpm else None
        video_rate_limiter = RateLimiter(max_requests_per_minute=vid_rpm) if vid_rpm else None
        audio_rate_limiter = RateLimiter(max_requests_per_minute=aud_rpm) if aud_rpm else None

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)
        
        # Audio generators still use direct class loading (not unified)
        def _init_gen(cfg_key, rate_limiter=None):
            if cfg_key not in config: return None
            mod, clz = config[cfg_key]["class_path"].rsplit(".", 1)
            cls_obj = getattr(importlib.import_module(mod), clz)
            args = {k: _resolve_env(v) for k, v in config[cfg_key]["init_args"].items()}
            if rate_limiter: args["rate_limiter"] = rate_limiter
            return cls_obj(**args)
        
        audio_generator_primary = _init_gen("audio_generator_primary", audio_rate_limiter)
        audio_generator_fallback = _init_gen("audio_generator_fallback")

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir or resolve from config
        resolved_working_dir = working_dir or (_resolve_path(config["working_dir"]) or config["working_dir"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            audio_generator_primary=audio_generator_primary,
            audio_generator_fallback=audio_generator_fallback,
            working_dir=resolved_working_dir,
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
        )

    async def _download_file(self, url: str, save_path: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024):
                        f.write(chunk)

    def _parse_timestamp(self, ts: str) -> float:
        """Parse timestamp like '0:15' or '1:30' into seconds."""
        parts = ts.split(':')
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(ts)

    def _build_creative_music_prompt(
        self,
        lyrics_draft,
        composition_plan,
        style: str,
        audience: Optional[str] = None,
    ) -> str:
        """Build a rich, creative prompt for music generation.
        
        Uses the composition plan's production details to create a prompt
        that will generate catchy, memorable music with proper beats and instruments.
        """
        # Start with the composer's production prompt if available
        if hasattr(composition_plan, 'production_prompt') and composition_plan.production_prompt:
            base_prompt = composition_plan.production_prompt
        else:
            # Build a rich prompt from available fields
            base_prompt = f"Create a {lyrics_draft.genre or style} song"
        
        # Build instrument list
        instruments = []
        if hasattr(composition_plan, 'primary_instruments') and composition_plan.primary_instruments:
            instruments = composition_plan.primary_instruments
        
        # Build beat/rhythm description
        beat_desc = ""
        if hasattr(composition_plan, 'beat_style') and composition_plan.beat_style:
            beat_desc = f"Beat style: {composition_plan.beat_style}. "
        
        # Build production style
        prod_style = ""
        if hasattr(composition_plan, 'production_style') and composition_plan.production_style:
            prod_style = f"Production: {composition_plan.production_style}. "
        
        # Build vocal style
        vocal_style = ""
        if hasattr(composition_plan, 'vocal_style') and composition_plan.vocal_style:
            vocal_style = f"Vocals: {composition_plan.vocal_style}. "
        
        # Build hook description
        hook_desc = ""
        if hasattr(composition_plan, 'hook_description') and composition_plan.hook_description:
            hook_desc = f"Hook: {composition_plan.hook_description}. "
        
        # Build section descriptions
        section_details = []
        for section in composition_plan.sections:
            section_str = f"{section.name} ({section.duration_seconds}s): {section.description}"
            if hasattr(section, 'instruments') and section.instruments:
                section_str += f" [Instruments: {', '.join(section.instruments)}]"
            if hasattr(section, 'beat_pattern') and section.beat_pattern:
                section_str += f" [Beat: {section.beat_pattern}]"
            if hasattr(section, 'energy_level') and section.energy_level:
                section_str += f" [Energy: {section.energy_level}]"
            section_details.append(section_str)
        
        # Construct the full creative prompt
        prompt_parts = [
            f"🎵 SONG: {lyrics_draft.title}",
            f"🎸 GENRE: {lyrics_draft.genre or style}",
            f"💫 MOOD: {lyrics_draft.mood or 'uplifting'}",
            f"🎯 AUDIENCE: {audience or 'general'}",
            "",
            "🎹 PRODUCTION DETAILS:",
        ]
        
        if instruments:
            prompt_parts.append(f"Instruments: {', '.join(instruments)}")
        if beat_desc:
            prompt_parts.append(beat_desc.strip())
        if prod_style:
            prompt_parts.append(prod_style.strip())
        if vocal_style:
            prompt_parts.append(vocal_style.strip())
        if hook_desc:
            prompt_parts.append(hook_desc.strip())
        
        if composition_plan.key:
            prompt_parts.append(f"Key: {composition_plan.key}")
        if composition_plan.tempo_bpm:
            prompt_parts.append(f"Tempo: {composition_plan.tempo_bpm} BPM")
        if composition_plan.energy_curve:
            prompt_parts.append(f"Energy Arc: {composition_plan.energy_curve}")
        
        prompt_parts.extend([
            "",
            "📋 SONG STRUCTURE:",
            *section_details,
            "",
            "📝 LYRICS:",
            lyrics_draft.lyrics,
            "",
            "🎯 MAKE IT CATCHY: Create an infectious, memorable song with a singalong chorus and hooks that stick in your head!",
        ])
        
        return "\n".join(prompt_parts)

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        frame_desc: str,
        character_portraits_registry: Dict[str, Any],
    ) -> None:
        """Composite character portraits onto a generated frame for consistency.
        
        Uses sophisticated positioning, view selection, and multi-character distribution logic.
        Now selects appropriate view (front/side/back) and expression based on shot context.
        """
        if not visible_characters or not os.path.exists(frame_path):
            return
        
        # Collect character portrait paths and infer positions
        char_data_to_composite: List[Dict[str, Any]] = []
        
        for char in visible_characters:
            char_id = char.identifier_in_scene
            
            # Use view selector to choose appropriate view based on shot description
            view = get_character_view_for_shot(frame_desc)
            expression = get_character_expression_for_shot(frame_desc)
            
            # Try to get the appropriate view path
            portrait_path = self._get_portrait_path_with_fallback(
                char_id, view, expression, character_portraits_registry
            )
            
            if portrait_path and os.path.exists(portrait_path):
                # Infer position for THIS specific character from description
                pos = get_character_position_from_description(frame_desc, char_id)
                scale = min(get_character_scale_from_shot_type(frame_desc), 0.5)
                
                char_data_to_composite.append({
                    "path": portrait_path,
                    "position": pos,
                    "scale": scale,
                    "name": char_id,
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
                    blend_mode="soft",
                )
                self.logger.info(
                    f"Composited {data['name']} ({data['view']}_{data['expression']}) "
                    f"onto {os.path.basename(frame_path)} at {data['position']}"
                )
            else:
                # Multiple characters - use inferred positions and distribution
                paths = [d["path"] for d in char_data_to_composite]
                positions = [d["position"] for d in char_data_to_composite]
                scales = [d["scale"] for d in char_data_to_composite]
                names = [d["name"] for d in char_data_to_composite]
                
                # Distribution logic: If multiple characters are center, spread them out
                if all(p == "center" for p in positions):
                    if len(positions) == 2:
                        positions = ["center-left", "center-right"]
                    elif len(positions) == 3:
                        positions = ["left", "center", "right"]
                
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=paths,
                    output_path=frame_path,
                    positions=positions,
                    scale_factors=scales,
                )
                self.logger.info(f"Composited {len(paths)} characters ({', '.join(names)}) onto {os.path.basename(frame_path)}")
        except Exception as e:
            self.logger.warning(f"Failed to composite characters onto {frame_path}: {e}")
    
    def _get_portrait_path_with_fallback(
        self,
        char_id: str,
        view: CharacterView,
        expression: CharacterExpression,
        registry: Dict[str, Any],
    ) -> Optional[str]:
        """Get portrait path with intelligent fallback.
        
        Tries to find the requested view+expression, falling back to:
        1. Requested view with neutral expression
        2. Front view with requested expression
        3. Front view with neutral expression
        """
        if char_id not in registry:
            return None
        
        char_data = registry[char_id]
        
        # Check for new format with expressions
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
            # Try expression-specific
            expr_data = front_data.get(expression.value)
            if expr_data:
                path = expr_data.get("path") if isinstance(expr_data, dict) else str(expr_data)
                if path and os.path.exists(path):
                    return path
            # Try neutral or direct path
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
        """Composite prop reference images onto a frame for object consistency.
        
        Args:
            frame_path: Path to the background frame
            visible_props: List of props that should appear in this shot
            prop_reference_images: List of {"path": ..., "description": ...} for each prop
            frame_desc: Visual description for position inference
        """
        if not visible_props or not prop_reference_images or not os.path.exists(frame_path):
            return
        
        # Build a lookup by prop identifier
        prop_refs_by_id = {}
        for ref in prop_reference_images:
            # Extract identifier from description
            desc = ref.get("description", "")
            for prop in visible_props:
                if prop.identifier.lower() in desc.lower():
                    prop_refs_by_id[prop.identifier] = ref.get("path")
                    break
        
        # Collect props to composite
        props_to_composite = []
        for prop in visible_props:
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

    async def __call__(
        self,
        idea: Optional[str] = None,
        user_requirement: Optional[str] = None,
        style: str = "pop",
        audience: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        # S3 Entity Integration
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_names: Optional[List[str]] = None,
        restitch_only: bool = False,
        content_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the music_video pipeline."""
        
        # 1. Resolve S3 entities
        print(f"🔗 Resolving S3 entities for consistency...")
        resolution = resolve_s3_entities(
            texts=[idea or "", user_requirement or ""],
            brand_hint=brand_id or brand_hint,
            game_hint=game_id,
            working_dir=self.working_dir,
        )
        characters: List[CharacterInScene] = resolution.get("characters") or []
        character_portraits_registry: Dict[str, Any] = resolution.get("portrait_registry") or {}
        is_s3_characters = len(characters) > 0
        
        # 2. Fetch Trends
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="music")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # 3. Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating song in {ideation_mode} mode...")
            brand_ctx = resolution.get("brand_context")
            game_ctx = resolution.get("game_context")
            
            if ideation_mode == "brand" and (brand_ctx or game_ctx):
                ideation_result = await self.ideation_engine.ideate_for_brand(
                    content_type="song",
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                    trend_context=trend_context,
                )
            
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(
                    content_type="song",
                    mode=ideation_mode,
                    audience=audience,
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            idea = ideation_result.idea
            user_requirement = ideation_result.to_prompt()
            audience = audience or ideation_result.target_audience
            # genre = genre or ideation_result.genre # Remove invalid attribute
            style = style or ideation_result.tone or "pop"
            
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_result.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated song idea: {ideation_result.title}")

        if not idea:
            raise ValueError("Either provide an 'idea' or set 'auto_ideate=True'")

        # 4. Generate Lyrics and Composition Plan
        effective_user_requirement = user_requirement or ""
        if trend_context_block:
            effective_user_requirement = f"{effective_user_requirement}\n\n{trend_context_block}"

        # DETECT KIDS AUDIENCE FOR ENHANCED DIRECTING
        is_kids = is_kids_audience(audience)
        if is_kids:
            effective_user_requirement = f"KIDS CONTENT: Magical, educational, safe, and highly visual.\n{effective_user_requirement}"
            style = f"colorful 3D kids animation, {style}"
            print(f"👦 Targeting kids audience - applying 'Toy-Box' vibrancy style.")

        # RESUME CHECK: Lyrics
        lyrics_path = os.path.join(self.working_dir, "lyrics.txt")
        if os.path.exists(lyrics_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing lyrics: {lyrics_path}")
            with open(lyrics_path, "r", encoding="utf-8") as f:
                lyrics_text = f.read()
            # We still need a lyrics_draft object for metadata
            lyrics_draft = LyricsDraft(title=idea[:30], lyrics=lyrics_text, genre=style, mood="dynamic")
        else:
            print(f"✍️ Generating lyrics...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "lyrics_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Idea: {idea}\nRequirement: {effective_user_requirement}\nAudience: {audience}")

            lyrics_draft = await self.lyricist.generate_lyrics(
                idea=idea,
                user_requirement=effective_user_requirement,
                style=style,
                audience=audience,
                trendy=trendy,
            )
            with open(lyrics_path, "w", encoding="utf-8") as f:
                f.write(lyrics_draft.lyrics)

        # RESUME CHECK: Composition Plan
        composition_path = os.path.join(self.working_dir, "composition_plan.json")
        if os.path.exists(composition_path) and not self.force_regenerate:
            with open(composition_path, "r", encoding="utf-8") as f:
                composition_plan = SongCompositionPlan(**json.load(f))
        else:
            print(f"✍️ Generating composition plan...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "composition_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Idea: {idea}\nLyrics: {lyrics_draft.lyrics[:1000]}")

            composition_plan = await self.song_composer.compose(
                idea=idea,
                lyrics=lyrics_draft.lyrics,
                style=style,
                audience=audience,
            )
            with open(composition_path, "w", encoding="utf-8") as f:
                json.dump(composition_plan.model_dump(), f, indent=2)

        # 4.5 Extract characters from lyrics if no S3 characters found
        # (Resume check for characters.json)
        characters_path = os.path.join(self.working_dir, "characters.json")
        if os.path.exists(characters_path) and not self.force_regenerate:
            with open(characters_path, "r", encoding="utf-8") as f:
                characters = [CharacterInScene(**c) for c in json.load(f)]
        elif not characters:
            print(f"🔍 Extracting characters from lyrics...")
            try:
                characters = await self.character_extractor.extract_characters(lyrics_draft.lyrics)
                with open(characters_path, "w", encoding="utf-8") as f:
                    json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.warning(f"Failed to extract characters from lyrics: {e}")
                characters = []
        
        # Generate character portraits for ALL characters (front, side, back views)
        if characters and self.image_generator and not character_portraits_registry:
            print(f"🎨 Generating character portraits for consistency...")
            char_portraits_dir = os.path.join(self.working_dir, "character_portraits")
            os.makedirs(char_portraits_dir, exist_ok=True)
            
            for char in characters:
                char_id = char.identifier_in_scene or f"character_{char.idx}"
                if char_id in character_portraits_registry:
                    continue
                    
                char_dir = os.path.join(char_portraits_dir, char_id.replace(" ", "_"))
                os.makedirs(char_dir, exist_ok=True)
                
                # Generate FRONT portrait first
                front_path = os.path.join(char_dir, "front.png")
                if not os.path.exists(front_path) or self.force_regenerate:
                    char_desc = f"{char.static_features or ''}"
                    if char.description:
                        char_desc = f"{char_desc}. {char.description}"
                    
                    portrait_prompt = f"""Character portrait of {char_id}. {char_desc}. 
{style} style music video aesthetic. Clean background, full body visible, facing camera.
This is the CANONICAL reference portrait - all future appearances must match this exactly."""
                    
                    try:
                        # Save debug prompt
                        debug_dir = os.path.join(char_dir, "debug")
                        os.makedirs(debug_dir, exist_ok=True)
                        with open(os.path.join(debug_dir, "portrait_prompt.txt"), "w", encoding="utf-8") as f:
                            f.write(portrait_prompt)

                        portrait_output = await self.image_generator.generate_single_image(
                            prompt=portrait_prompt,
                        )
                        if portrait_output:
                            portrait_output.save(front_path)
                            print(f"    Generated front portrait for {char_id}")
                    except Exception as e:
                        self.logger.warning(f"    Failed to generate front portrait for {char_id}: {e}")
                
                # Generate SIDE portrait using front as reference
                side_path = os.path.join(char_dir, "side.png")
                if os.path.exists(front_path) and (not os.path.exists(side_path) or self.force_regenerate):
                    side_prompt = f"""Generate a full-body, SIDE VIEW portrait of {char_id} based on the provided front-view portrait. 
CRITICAL: This must be the EXACT SAME CHARACTER as the reference image, just shown from a perfect 90-degree side angle (profile view).
- Same design, colors, features, and appearance as the front view
- Character facing left or right, NOT toward the camera
- Full body visible from head to feet
- {style} style music video aesthetic
- Pure white background, no shadows
- The character must be IDENTICAL to the reference, only the viewing angle changes."""
                    
                    try:
                        debug_dir = os.path.join(char_dir, "debug")
                        os.makedirs(debug_dir, exist_ok=True)
                        with open(os.path.join(debug_dir, "side_prompt.txt"), "w", encoding="utf-8") as f:
                            f.write(side_prompt)
                        
                        side_output = await self.image_generator.generate_single_image(
                            prompt=side_prompt,
                            reference_image_paths=[front_path],
                        )
                        if side_output:
                            side_output.save(side_path)
                            print(f"    Generated side portrait for {char_id}")
                    except Exception as e:
                        self.logger.warning(f"    Failed to generate side portrait for {char_id}: {e}")
                
                # Generate BACK portrait using front as reference
                back_path = os.path.join(char_dir, "back.png")
                if os.path.exists(front_path) and (not os.path.exists(back_path) or self.force_regenerate):
                    back_prompt = f"""Generate a full-body, BACK VIEW portrait of {char_id} based on the provided front-view portrait.
CRITICAL: This must be the EXACT SAME CHARACTER as the reference image, just shown from directly behind (180-degree view).
- Same design, colors, features, and appearance as the front view
- Character's back facing the camera
- NO face visible - only the back of the character
- Full body visible from head to feet
- {style} style music video aesthetic
- Pure white background, no shadows
- The character must be IDENTICAL to the reference, only the viewing angle changes."""
                    
                    try:
                        debug_dir = os.path.join(char_dir, "debug")
                        os.makedirs(debug_dir, exist_ok=True)
                        with open(os.path.join(debug_dir, "back_prompt.txt"), "w", encoding="utf-8") as f:
                            f.write(back_prompt)
                        
                        back_output = await self.image_generator.generate_single_image(
                            prompt=back_prompt,
                            reference_image_paths=[front_path],
                        )
                        if back_output:
                            back_output.save(back_path)
                            print(f"    Generated back portrait for {char_id}")
                    except Exception as e:
                        self.logger.warning(f"    Failed to generate back portrait for {char_id}: {e}")
                
                # Build registry with all three views
                if os.path.exists(front_path):
                    character_portraits_registry[char_id] = {
                        "front": {
                            "path": front_path,
                            "description": f"Front view portrait of {char_id}"
                        }
                    }
                    if os.path.exists(side_path):
                        character_portraits_registry[char_id]["side"] = {
                            "path": side_path,
                            "description": f"Side view portrait of {char_id}"
                        }
                    if os.path.exists(back_path):
                        character_portraits_registry[char_id]["back"] = {
                            "path": back_path,
                            "description": f"Back view portrait of {char_id}"
                        }
            
            # Save character portraits registry
            if character_portraits_registry:
                registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")
                with open(registry_path, "w", encoding="utf-8") as f:
                    json.dump(character_portraits_registry, f, ensure_ascii=False, indent=2)
        
        # Save characters.json
        if characters:
            characters_path = os.path.join(self.working_dir, "characters.json")
            with open(characters_path, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)

        # 4.6 Extract and Generate Prop References (Object Consistency)
        props_path = os.path.join(self.working_dir, "props.json")
        prop_reference_images = []
        if os.path.exists(props_path) and not self.force_regenerate:
            with open(props_path, "r", encoding="utf-8") as f:
                props_data = json.load(f)
                from interfaces.entities.prop import PropInScene
                props = [PropInScene(**p) for p in props_data]
        else:
            print(f"🔍 Extracting props from lyrics for object consistency...")
            props_result = await self.prop_extractor.extract_props_and_anchors(lyrics_draft.lyrics)
            props = props_result.props
            with open(props_path, "w", encoding="utf-8") as f:
                json.dump([p.model_dump() for p in props], f, ensure_ascii=False, indent=2)
        
        if props and self.image_generator:
            print(f"🎨 Generating prop references for object consistency...")
            prop_refs_dir = os.path.join(self.working_dir, "prop_references")
            os.makedirs(prop_refs_dir, exist_ok=True)
            for prop in props:
                ref_path = await self.prop_reference_generator.generate_prop_reference(prop, style, prop_refs_dir)
                if ref_path and os.path.exists(ref_path):
                    prop_reference_images.append({
                        "path": ref_path,
                        "description": f"Visual reference for prop: {prop.identifier}. {prop.description}"
                    })

        # 5. Generate Audio
        audio_path = os.path.join(self.working_dir, "audio.mp3")
        if os.path.exists(audio_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing audio: {audio_path}")
        else:
            print(f"🎵 Generating audio...")
            
            # Build a rich, creative music prompt from the composition plan
            music_prompt = self._build_creative_music_prompt(
                lyrics_draft=lyrics_draft,
                composition_plan=composition_plan,
                style=style,
                audience=audience,
            )
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "music_generation_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(music_prompt)
            
            try:
                # Build ElevenLabs composition plan if primary is ElevenLabs
                elevenlabs_plan = None
                if hasattr(self.audio_generator_primary, "compose_music"):
                    # Build sections with proper structure for ElevenLabs API
                    sections = []
                    for section in composition_plan.sections:
                        # Skip sections with 0 duration (like Outro with 0s)
                        if section.duration_seconds <= 0:
                            self.logger.debug(f"Skipping section '{section.name}' with 0 duration")
                            continue
                            
                        section_dict = {
                            "section_name": section.name,
                            "duration_ms": max(1000, int(section.duration_seconds * 1000)),  # Minimum 1 second
                            "lines": section.lines if section.lines else [],
                        }
                        # Add positive_local_styles only if description exists and is not too long
                        if section.description:
                            # Use description as style, but keep it concise (API may have limits)
                            section_dict["positive_local_styles"] = [section.description[:200]]  # Limit length
                        sections.append(section_dict)
                    
                    # Ensure we have at least one section
                    if not sections:
                        raise ValueError("No valid sections in composition plan (all sections have 0 duration)")
                    
                    elevenlabs_plan = {
                        "positive_global_styles": [style] if style else [],
                        "sections": sections
                    }
                    
                    self.logger.debug(f"Built ElevenLabs composition plan with {len(sections)} sections")

                # When using composition_plan, don't pass prompt or music_length_ms (API requirement)
                await self.audio_generator_primary.compose_music(
                    prompt=None,  # Don't pass prompt when using composition_plan
                    composition_plan=elevenlabs_plan,
                    music_length_ms=None,  # Don't pass music_length_ms when using composition_plan
                    output_path=audio_path,
                )
            except Exception as exc:
                self.logger.warning("Primary audio generation failed, using fallback: %s", exc)
                # Use the same rich prompt for fallback
                audio_url = await self.audio_generator_fallback.generate_music(
                    prompt=music_prompt,
                    lyrics=lyrics_draft.lyrics,
                    style=style,
                )
                await self._download_file(audio_url, audio_path)

        # 6. Generate Music Video Concept (Director)
        concept_path = os.path.join(self.working_dir, "musicvideo_concept.json")
        if os.path.exists(concept_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing concept: {concept_path}")
            with open(concept_path, "r", encoding="utf-8") as f:
                concept = MusicVideoConcept(**json.load(f))
        else:
            print(f"🎬 Directing music video (Director)...")
            is_kids = is_kids_audience(audience)
            kids_context = "KIDS ANIMATED MUSIC VIDEO: G-rated, colorful, safe." if is_kids else ""
            concept = await self.music_video_director.direct_music_video(
                song_title=lyrics_draft.title,
                lyrics=lyrics_draft.lyrics,
                genre=lyrics_draft.genre or style,
                mood=lyrics_draft.mood or "uplifting",
                song_structure=f"Duration: {composition_plan.total_duration_seconds}s",
                style="colorful 3D kids animation" if is_kids else style,
                audience=audience or "general",
                additional_context=f"{kids_context}\n\n{trend_context_block}".strip(),
            )
            with open(concept_path, "w", encoding="utf-8") as f:
                json.dump(concept.model_dump(), f, ensure_ascii=False, indent=2)

        # 6.5 Refine Cinematography (Video Grapher / Storyboard Artist)
        # The user wants a proper video grapher agent to plan based on lyrics.
        # We use the StoryboardArtist to refine the visual descriptions of the director's shots.
        refined_shots_path = os.path.join(self.working_dir, "refined_storyboard.json")
        if os.path.exists(refined_shots_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing refined storyboard: {refined_shots_path}")
            with open(refined_shots_path, "r", encoding="utf-8") as f:
                refined_shots = json.load(f)
        else:
            print(f"📐 Refining cinematography (Video Grapher)...")
            storyboard_context = f"Visual Style: {style}\nOriginal Concept: {concept.concept_summary}\n"
            if is_kids:
                storyboard_context += "KIDS PRODUCTION: Use playful framing, vibrant colors, and clear character focus.\n"
            
            # Use StoryboardArtist to detail the visual plans for each shot
            refined_storyboard = await self.storyboard_artist.design_storyboard(
                script=f"SONG TITLE: {lyrics_draft.title}\nLYRICS:\n{lyrics_draft.lyrics}\n\nDIRECTOR BRIEF:\n{concept.concept_summary}",
                characters=characters,
                user_requirement=storyboard_context,
            )
            
            # Align refined descriptions back to original timed shots
            refined_shots = []
            for i, shot in enumerate(concept.shots):
                # Match by index or just use the sequence
                refined_desc = refined_storyboard[i].visual_desc if i < len(refined_storyboard) else shot.visual_description
                refined_audio = refined_storyboard[i].audio_desc if i < len(refined_storyboard) else ""
                
                shot_data = shot.model_dump()
                shot_data["visual_description"] = refined_desc
                shot_data["audio_description"] = refined_audio
                refined_shots.append(shot_data)
            
            with open(refined_shots_path, "w", encoding="utf-8") as f:
                json.dump(refined_shots, f, ensure_ascii=False, indent=2)

        # 7. Generate Video Clips for Each Shot
        print(f"🎥 Generating/Restitching video clips for {len(refined_shots)} shots...")
        shots_dir = os.path.join(self.working_dir, "shots")
        os.makedirs(shots_dir, exist_ok=True)
        
        # Reset continuity memory for this run
        self.continuity_memory.reset()
        
        # Background Locking: Track the first frame of each location to maintain consistency
        location_establishment_frames = {}
        
        video_clips_paths = []
        for i, shot_data in enumerate(refined_shots):
            shot_num = shot_data.get("shot_number", i + 1)
            shot_id = f"shot_{shot_num:02d}"
            shot_dir = os.path.join(shots_dir, shot_id)
            os.makedirs(shot_dir, exist_ok=True)
            
            visual_description = shot_data["visual_description"]
            audio_description = shot_data.get("audio_description", "")
            location_name = shot_data.get("location", "Default Location")
            
            frame_path = os.path.join(shot_dir, "first_frame.png")
            raw_frame_path = os.path.join(shot_dir, "first_frame_raw.png")
            clip_path = os.path.join(shot_dir, "clip.mp4")
            
            if (os.path.exists(clip_path) and not self.force_regenerate) or restitch_only:
                if os.path.exists(clip_path):
                    video_clips_paths.append(clip_path)
                    # Even if skipping, register the first frame if it's the first for this location
                    if location_name not in location_establishment_frames and os.path.exists(raw_frame_path):
                        location_establishment_frames[location_name] = raw_frame_path
                    continue
                elif restitch_only:
                    self.logger.warning(f"  Restitch mode: Clip NOT found at {clip_path}. Skipping.")
                    continue

            start_sec = self._parse_timestamp(shot_data["timestamp_start"])
            end_sec = self._parse_timestamp(shot_data["timestamp_end"])
            duration = max(2, min(10, end_sec - start_sec))
            
            # Identify visible characters
            visible_chars = []
            for char in characters:
                char_name = char.identifier_in_scene
                if not char_name: continue
                pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                if re.search(pattern, visual_description):
                    visible_chars.append(char)

            # DEBUG LOGS FOR SHOT
            char_names = [c.identifier_in_scene for c in visible_chars]
            self.logger.info(
                f"\n🎬 [SHOT {shot_num}] DEBUG INFO:\n"
                f"   📍 Location: {location_name}\n"
                f"   👥 Characters ({len(visible_chars)}): {', '.join(char_names) if char_names else 'None'}\n"
                f"   ⏱️ Duration: {duration}s\n"
                f"   📝 Visual Plan: {visual_description}\n"
                f"   🎵 Audio Context: {audio_description}\n"
            )

            # Generate Frame
            if not os.path.exists(frame_path) or self.force_regenerate:
                # 1. Generate "CLEAN" Background first
                # We need a clean background to composite characters onto.
                bg_visual_desc = visual_description
                for char in characters:
                    bg_visual_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_visual_desc)
                
                bg_prompt = (
                    f"Music video background scenery. Location: {location_name}. {bg_visual_desc}. "
                    "EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures. "
                    "A beautiful, detailed background scene. High resolution. No text."
                )

                establishment_frame = location_establishment_frames.get(location_name)
                
                # Save debug prompt
                debug_dir = os.path.join(shot_dir, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "clean_bg_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(bg_prompt)

                bg_output = await self.image_generator.generate_single_image(
                    prompt=bg_prompt, 
                    reference_image_paths=[establishment_frame] if establishment_frame and os.path.exists(establishment_frame) else None
                )
                bg_output.save(frame_path) # Save as first_frame.png
                
                # 2. Composite EXACT S3 characters onto the clean background
                # This creates the "canvas" for the AI to blend.
                if visible_chars: 
                    self._composite_characters_on_frame(
                        frame_path=frame_path, 
                        visible_characters=visible_chars, 
                        frame_desc=visual_description, 
                        character_portraits_registry=character_portraits_registry
                    )
                
                # 2.5 Composite props for object consistency
                if props and prop_reference_images:
                    # Find props mentioned in this shot
                    visible_props = []
                    for prop in props:
                        if prop.identifier.lower() in visual_description.lower():
                            visible_props.append(prop)
                    
                    if visible_props:
                        self._composite_props_on_frame(
                            frame_path=frame_path,
                            visible_props=visible_props,
                            prop_reference_images=prop_reference_images,
                            frame_desc=visual_description,
                        )
                
                # 3. Generate "RAW" Frame (AI-rendered characters integrated into scene)
                # We use the composite first_frame.png as the reference to ensure consistency!
                char_desc_parts = []
                for char in visible_chars:
                    if char.static_features:
                        char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
                
                char_context = ""
                if char_desc_parts:
                    char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "."
                
                # Add view and expression guidance
                view_instruction = ""
                expression_instruction = ""
                if visible_chars:
                    view = get_character_view_for_shot(visual_description)
                    expression = get_character_expression_for_shot(visual_description)
                    view_instruction = f" Camera angle: {view.value} view."
                    expression_instruction = f" Character expressions: {expression.value}."
                
                raw_prompt = (
                    f"Music video scene. Location: {location_name}. {visual_description}.{char_context}{view_instruction}{expression_instruction} "
                    f"Professional animation quality, cinematic composition, proper lighting. "
                    f"Blend the characters naturally into the environment with shadows and reflections. "
                    f"Maintain the exact appearance of the characters from the reference image."
                )
                
                # Reference images: The composite frame is THE MOST IMPORTANT ONE.
                raw_refs = [frame_path] # The composite we just made
                
                # Get view/expression once for all characters
                view = get_character_view_for_shot(visual_description) if visible_chars else None
                expression = get_character_expression_for_shot(visual_description) if visible_chars else None
                
                for char in visible_chars:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits_registry and view and expression:
                        # Use view/expression selector
                        # Try to get view-specific portrait
                        view_data = character_portraits_registry[char_id].get(view.value, {})
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
                        
                        # Fallback to front view
                        if not path:
                            front_entry = character_portraits_registry[char_id].get("front", {})
                            if isinstance(front_entry, dict):
                                path = front_entry.get("path")
                            else:
                                path = str(front_entry) if front_entry else None
                        
                        if path and os.path.exists(path) and path not in raw_refs:
                            raw_refs.append(path)

                with open(os.path.join(debug_dir, "raw_scene_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(raw_prompt)

                # Generate the "gelled" AI frame using img2img on the composite
                image_output = await self.image_generator.generate_single_image(
                    prompt=raw_prompt, 
                    reference_image_paths=raw_refs,
                    strength=0.55 # Balanced strength to blend but keep identity
                )
                image_output.save(raw_frame_path)

                # 4. Register establishment frame for this location if it's the first
                if location_name not in location_establishment_frames:
                    location_establishment_frames[location_name] = raw_frame_path

            # Generate Video Clip
            if not os.path.exists(clip_path) or self.force_regenerate:
                # VIDEO GENERATION: Use the RAW frame (the one where characters are "gelled" in)
                vid_prompt = f"{visual_description}. {audio_description}. cinematic motion, smooth animation."
                
                for char in visible_chars:
                    if char.static_features:
                        vid_prompt += f" {char.identifier_in_scene}: {char.static_features}."
                
                video_output = await self.video_generator.generate_single_video(
                    prompt=vid_prompt, 
                    reference_image_paths=[raw_frame_path], # Use gelled frame for video!
                    duration=int(duration)
                )
                video_output.save(clip_path)
            
            # Update continuity memory for this shot
            visible_char_ids = [c.identifier_in_scene for c in visible_chars]
            visible_prop_ids = [p.identifier for p in props if p.identifier.lower() in visual_description.lower()] if props else []
            self.continuity_memory.update_for_shot(
                shot_idx=i,
                frame_path=raw_frame_path if os.path.exists(raw_frame_path) else frame_path,
                scene_id=f"scene_{location_name}",
                location=location_name,
                visible_characters=visible_char_ids,
                visible_props=visible_prop_ids,
                shot_description=visual_description,
            )
            
            video_clips_paths.append(clip_path)

        # 8. Assemble Final Video
        final_video_path = os.path.join(self.working_dir, "final_music_video.mp4")
        if os.path.exists(final_video_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing final music video: {final_video_path}")
        else:
            print(f"🎬 Assembling final video...")
            final_video_no_audio = os.path.join(self.working_dir, "final_video_no_audio.mp4")
            clips = [VideoFileClip(p) for p in video_clips_paths]
            final_clip = concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(final_video_no_audio, codec="libx264", audio=False)
            video_with_audio = final_clip.set_audio(AudioFileClip(audio_path))
            video_with_audio.write_videofile(final_video_path, codec="libx264", audio_codec="aac")
            for c in clips: c.close()
            final_clip.close()

        # 9. Reasoning
        write_phase1_reasoning(self.working_dir, "music_video", "Phase 1: Lyrics & Plan", "lyrics", "Lyrics and composition plan drive the song and visuals.", {"idea": idea}, {"lyrics.txt": "Lyrics text"})
        write_song_reasoning(self.working_dir, "music_video", "Lyrics and audio generation rationale.", {"style": style}, {"audio.mp3": "Song audio"})
        write_director_reasoning(self.working_dir, "music_video", "MusicVideoDirector", "Directing the visual narrative from lyrics.", {"lyrics": lyrics_draft.lyrics[:100]}, {"musicvideo_concept.json": "Concept"})
        write_cinematographer_picturization_reasoning(self.working_dir, "music_video", "Shot-by-shot video generation with character consistency.", {"shots": len(concept.shots)}, {"final_music_video.mp4": "Final video"})

        # 10. Monetization
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=lyrics_draft.title,
            description=f"Music video for '{lyrics_draft.title}'. Genre: {lyrics_draft.genre}. Concept: {concept.concept_summary}",
            audience=audience or "General",
            duration_seconds=int(final_clip.duration) if 'final_clip' in locals() else composition_plan.total_duration_seconds,
            genre=lyrics_draft.genre or style,
            is_shorts=False,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        total_duration = composition_plan.total_duration_seconds
        if final_video_path and total_duration >= 120:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = f"LYRICS:\n{lyrics_draft.lyrics}\n\nCONCEPT:\n{json.dumps(concept.model_dump(), ensure_ascii=False)}"
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_video_path,
                script_content=script_full_text,
                total_duration_seconds=total_duration,
                content_type="music_video"
            )

        output_metadata = {
            "run_id": self.run_id,
            "idea": idea,
            "song_title": lyrics_draft.title,
            "lyrics": lyrics_draft.lyrics,
            "audio_path": audio_path,
            "video_path": final_video_path,
            "viral_shorts": viral_shorts,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 11. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=lyrics_draft.lyrics,
                storyboard=refined_shots,
                video_metadata=output_metadata
            )
            output_metadata["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(os.path.join(self.working_dir, "output.json"), "w", encoding="utf-8") as f:
            json.dump(output_metadata, f, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4", "*.mp3"])

        return output_metadata
