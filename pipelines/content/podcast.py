"""
Podcast to Video Pipeline

Converts podcast scripts into complete video episodes using
S3-hosted character assets and ViMax video generation.
"""
import os
import re
import json
import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any, Literal
from dataclasses import dataclass
import yaml

from langchain.chat_models import init_chat_model
import importlib
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config

from agents.producers.analysis import (
    PodcastScriptParser, ParsedPodcast, PodcastScene, SceneType
)
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from utils.pipeline.s3_loader import (
    S3CharacterLoader, load_brand_characters_for_vimax, download_brand_characters
)
from interfaces.entities.character import CharacterInScene
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import PodcastEpisodeIdea
from interfaces.entities.brand_context import BrandContext, GameContext
from utils.core.rate_limiter import RateLimiter
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, TextClip, CompositeVideoClip
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
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
from configs.constants.pipeline_profiles import PODCAST_PROFILE


@dataclass
class PodcastConfig:
    """Configuration for podcast video generation"""
    brand_id: str = "intelli-verse-x"
    working_dir: str = ".working_dir/content/podcast"
    run_id: Optional[str] = None
    use_run_id: bool = True
    max_scene_duration: int = 120  # seconds
    video_style: str = "3D animated cartoon style, colorful, kid-friendly"
    audio_style: str = "warm, engaging, kid-friendly podcast voice"
    include_subtitles: bool = True
    include_background_music: bool = True


class Podcast2VideoPipeline:
    """Pipeline to convert podcast scripts to video"""
    
    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        config: PodcastConfig,
        trend_analyzer: Optional[TrendAnalyzer] = None,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.config = config
        self.trend_analyzer = trend_analyzer
        self.base_working_dir = config.working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=config.working_dir,
            pipeline_name="podcast2video",
            run_id=config.run_id,
            use_run_id=config.use_run_id,
        )
        
        # Initialize components
        self.script_parser = PodcastScriptParser()
        self.s3_loader = S3CharacterLoader()
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="podcast")
        
        # Loaded characters
        self.characters: Dict[str, CharacterInScene] = {}
        self.character_portraits: Dict[str, Dict] = {}
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        
        os.makedirs(self.working_dir, exist_ok=True)
        if config.use_run_id and self.run_id:
            write_run_metadata(self.working_dir, "podcast2video", self.run_id)
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def init_from_config(cls, config_path: str, podcast_config: Optional[PodcastConfig] = None):
        """Initialize pipeline from YAML config file"""
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
        
        # Initialize chat model
        chat_model_args = config["chat_model"]["init_args"]
        chat_model_args = {k: _resolve_env(v) for k, v in chat_model_args.items()}
        chat_model = init_chat_model(**chat_model_args)
        
        # Rate limiters
        image_generator_rpm = config.get("image_generator", {}).get("max_requests_per_minute")
        image_generator_rpd = config.get("image_generator", {}).get("max_requests_per_day")
        video_generator_rpm = config.get("video_generator", {}).get("max_requests_per_minute")
        video_generator_rpd = config.get("video_generator", {}).get("max_requests_per_day")
        
        image_rate_limiter = RateLimiter(
            max_requests_per_minute=image_generator_rpm,
            max_requests_per_day=image_generator_rpd
        ) if (image_generator_rpm or image_generator_rpd) else None
        
        video_rate_limiter = RateLimiter(
            max_requests_per_minute=video_generator_rpm,
            max_requests_per_day=video_generator_rpd
        ) if (video_generator_rpm or video_generator_rpd) else None
        
        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)
        
        # Default podcast config
        if podcast_config is None:
            podcast_config = PodcastConfig(
                working_dir=os.path.join(base_dir, ".working_dir/podcast")
            )
        
        # Initialize trend analyzer if configured
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])
        
        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            config=podcast_config,
            trend_analyzer=trend_analyzer,
        )
    
    async def load_characters_from_s3(
        self,
        additional_characters: Optional[List[str]] = None,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ):
        """Load all characters from S3 brand
        
        Generic loader that works with any brand. Characters are auto-discovered
        from S3 if brand.json doesn't list them.
        """
        effective_brand_id = brand_id or self.config.brand_id
        self.logger.info(f"Loading characters from brand: {effective_brand_id}")
        
        # Load from S3 - returns CharacterData objects
        if game_id:
            s3_characters = self.s3_loader.load_game_characters(game_id)
        else:
            s3_characters = self.s3_loader.load_brand_characters(effective_brand_id)
        
        for char_data in s3_characters:
            # CharacterData has identifier_in_scene attribute
            identifier = char_data.identifier_in_scene
            
            # Create CharacterInScene using the conversion method
            self.characters[identifier] = char_data.to_vimax_character(len(self.characters))
            
            # Store portrait URLs (supports multiple URL key formats)
            public_urls = char_data.public_urls
            if public_urls:
                # Build portrait registry with both URL formats for compatibility
                front_url = public_urls.get("front") or public_urls.get("portrait_front", "")
                side_url = public_urls.get("side") or public_urls.get("portrait_side", "")
                back_url = public_urls.get("back") or public_urls.get("portrait_back", "")
                
                self.character_portraits[identifier] = {
                    "front_url": front_url,
                    "side_url": side_url,
                    "back_url": back_url,
                    "front": {"path": front_url, "description": f"Front view of {char_data.name}"},
                    "side": {"path": side_url, "description": f"Side view of {char_data.name}"},
                    "back": {"path": back_url, "description": f"Back view of {char_data.name}"},
                }
            
            # Also store aliases for resolution
            for alias in char_data.aliases:
                self.s3_loader._alias_cache[alias] = identifier
        
        self.logger.info(f"Loaded {len(self.characters)} characters: {list(self.characters.keys())}")
        
        # Optionally download portraits locally (for backup/caching)
        portrait_dir = os.path.join(self.working_dir, "character_portraits")
        try:
            if game_id:
                self.local_portraits = download_brand_characters(
                    effective_brand_id,
                    portrait_dir,
                    list(self.characters.keys()),
                )
            else:
                self.local_portraits = download_brand_characters(
                    effective_brand_id,
                    portrait_dir,
                    list(self.characters.keys())
                )
            self.logger.info(f"Downloaded portraits to: {portrait_dir}")
        except Exception as e:
            self.logger.warning(f"Could not download portraits locally: {e}")
            self.local_portraits = {}
    
    def parse_script(self, script_path: str) -> ParsedPodcast:
        """Parse a podcast script file"""
        # Read file (supports PDF and text)
        if script_path.endswith('.pdf'):
            # Use PyPDF or similar
            import subprocess
            result = subprocess.run(
                ["pdftotext", "-layout", script_path, "-"],
                capture_output=True, text=True
            )
            script_text = result.stdout if result.returncode == 0 else ""
            if not script_text:
                # Fallback: read as provided
                with open(script_path, 'r', errors='ignore') as f:
                    script_text = f.read()
        else:
            with open(script_path, 'r') as f:
                script_text = f.read()
        
        parsed = self.script_parser.parse(script_text)
        
        # Save parsed structure
        parsed_path = os.path.join(self.working_dir, "parsed_podcast.json")
        with open(parsed_path, 'w') as f:
            json.dump({
                "title": parsed.title,
                "part": parsed.part,
                "total_scenes": len(parsed.scenes),
                "all_characters": parsed.all_characters,
                "estimated_duration_seconds": parsed.estimated_total_duration,
                "scenes": [
                    {
                        "scene_id": s.scene_id,
                        "title": s.title,
                        "type": s.scene_type.value,
                        "setting": s.setting,
                        "characters": s.characters_present,
                        "duration_estimate": s.duration_estimate_seconds,
                        "dialogue_count": len(s.dialogue)
                    }
                    for s in parsed.scenes
                ]
            }, f, indent=2)
        
        self.logger.info(f"Parsed podcast: {parsed.title}")
        self.logger.info(f"Total scenes: {len(parsed.scenes)}")
        self.logger.info(f"Estimated duration: {parsed.estimated_total_duration}s ({parsed.estimated_total_duration // 60}min)")

        # Phase 1 reasoning: rationale for the parsed podcast script driving the pipeline
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast2video",
            phase_label="Phase 1: Parsed podcast script",
            content_type="input_script",
            rationale=(
                "The podcast script is the narrative input. PodcastScriptParser turns it into a structured "
                "ParsedPodcast: scenes with type (INTRO, QA, SONG, SKIT, etc.), setting, characters_present, "
                "dialogue, and duration. This structure drives scene-level video generation: each scene's "
                "type and dialogue shape the visual prompt and character blocking. S3 characters are used "
                "when available for visual consistency. The rationale is to make explicit how the source "
                "script and parsing choices affect the resulting video."
            ),
            inputs={
                "script_path": script_path,
                "parsed_title": parsed.title,
                "total_scenes": len(parsed.scenes),
                "all_characters": parsed.all_characters[:10] if parsed.all_characters else [],
                "estimated_duration_seconds": parsed.estimated_total_duration,
            },
            outputs={"parsed_podcast.json": "Parsed structure (title, scenes with type, setting, characters, dialogue)."},
        )
        
        return parsed
    
    async def generate_scene_video(
        self,
        scene: PodcastScene,
        scene_dir: str
    ) -> Optional[str]:
        """Generate video for a single scene"""
        os.makedirs(scene_dir, exist_ok=True)
        
        output_path = os.path.join(scene_dir, "scene_video.mp4")
        if os.path.exists(output_path):
            self.logger.info(f"Scene {scene.scene_id} video already exists, skipping")
            return output_path
        
        # Get scene script
        scene_script = self.script_parser.get_scene_script(scene)
        
        # Build prompt for video generation
        prompt = self._build_scene_prompt(scene, scene_script)
        
        # Get reference images for characters in scene
        NON_VISUAL_CHARACTERS = {"KidVoice", "Wind", "AlarmClock", "Dino", "All"}
        
        reference_images = []
        visible_character_objs = []
        
        for char_id in scene.characters_present:
            if char_id in NON_VISUAL_CHARACTERS:
                continue
            
            resolved_id = self.s3_loader.resolve_character_alias(char_id)
            
            if resolved_id in self.characters:
                visible_character_objs.append(self.characters[resolved_id])
            
            # Find portrait path (supports multiple key formats for compatibility)
            portrait_path = None
            if resolved_id in self.local_portraits:
                local_entry = self.local_portraits[resolved_id]
                portrait_path = local_entry.get("front_path") or local_entry.get("front", {}).get("path")
            
            if not portrait_path and resolved_id in self.character_portraits:
                cp_entry = self.character_portraits[resolved_id]
                # Support both URL format and standard registry format
                portrait_path = cp_entry.get("front_url")
                if not portrait_path:
                    front_entry = cp_entry.get("front", {})
                    if isinstance(front_entry, dict):
                        portrait_path = front_entry.get("path")
            
            if portrait_path:
                reference_images.append(portrait_path)
        
        self.logger.info(f"Generating video for scene {scene.scene_id}: {scene.title}")
        
        try:
            # 1. Generate first frame for character consistency
            first_frame_path = os.path.join(scene_dir, "first_frame.png")
            raw_frame_path = first_frame_path.replace(".png", "_raw.png")
            
            if self.image_generator and not os.path.exists(first_frame_path):
                # CHARACTER CONSISTENCY FIX:
                # We follow a dual-track generation process:
                # 1. RAW Frame: AI generates the full scene with characters "gelled" in (lighting, etc.)
                # 2. STORYBOARD Frame: Exact S3 portraits composited on a clean background.
                
                debug_dir = os.path.join(scene_dir, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                
                # Get establishment frame and previous shot reference
                location_name = scene.setting or "Default Location"
                establishment_frame = self.continuity_memory.location_establishment_frames.get(location_name)
                previous_shot_ref = self.continuity_memory.previous_shot_frame
                
                # --- TRACK 1: BACKGROUND GENERATION (Clean Environment) ---
                bg_visual_desc = prompt[:500]
                if visible_character_objs:
                    for char in visible_character_objs:
                        bg_visual_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_visual_desc)
                
                bg_prompt = f"Podcast background scenery. {scene.setting}. {bg_visual_desc}. EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures. No text."
                
                with open(os.path.join(debug_dir, "first_frame_bg_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(bg_prompt)

                # Use establishment frame or previous shot as reference
                bg_refs = []
                if establishment_frame and os.path.exists(establishment_frame):
                    bg_refs.append(establishment_frame)
                elif previous_shot_ref and os.path.exists(previous_shot_ref):
                    bg_refs.append(previous_shot_ref)

                bg_image = await self.image_generator.generate_single_image(
                    prompt=bg_prompt,
                    reference_image_paths=bg_refs if bg_refs else None
                )
                if bg_image:
                    bg_image.save(first_frame_path)
                
                # --- TRACK 2: COMPOSITE CHARACTERS (S3 Portraits) ---
                if visible_character_objs:
                    self._composite_characters_on_frame(
                        frame_path=first_frame_path,
                        visible_characters=visible_character_objs,
                        frame_desc=prompt,
                        character_portraits_registry=self.character_portraits
                    )
                
                # --- TRACK 3: RAW GENERATION (Gelled Characters) ---
                char_desc_parts = []
                for char in visible_character_objs:
                    if char.static_features:
                        char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
                char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
                
                # Add view and expression guidance
                view_instruction = ""
                expression_instruction = ""
                if visible_character_objs:
                    view = get_character_view_for_shot(prompt)
                    expression = get_character_expression_for_shot(prompt)
                    view_instruction = f" Camera angle: {view.value} view."
                    expression_instruction = f" Character expressions: {expression.value}."
                
                raw_prompt = f"Podcast video frame. {scene.setting}. {prompt[:500]}.{char_context}{view_instruction}{expression_instruction} High quality animation frame, expressive characters gelled into scene. Blend characters naturally into environment. No text."
                
                # Include ALL character portraits (not just 2) for multi-character scenes
                raw_refs = [first_frame_path]  # Start with composite frame
                if visible_character_objs:
                    for char in visible_character_objs:
                        char_id = char.identifier_in_scene
                        if char_id in self.character_portraits:
                            # Use view/expression selector
                            view = get_character_view_for_shot(prompt)
                            expression = get_character_expression_for_shot(prompt)
                            
                            # Try to get view-specific portrait
                            view_data = self.character_portraits[char_id].get(view.value, {})
                            if isinstance(view_data, dict):
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
                                p_info = self.character_portraits[char_id].get("front", {})
                                path = p_info.get("path") if isinstance(p_info, dict) else str(p_info) if p_info else None
                            
                            if path and os.path.exists(path) and path not in raw_refs:
                                raw_refs.append(path)
                
                with open(os.path.join(debug_dir, "first_frame_raw_prompt.txt"), "w", encoding="utf-8") as f:
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
                    self.continuity_memory.location_establishment_frames[location_name] = raw_frame_path if os.path.exists(raw_frame_path) else first_frame_path
                
                # Update continuity memory
                visible_char_ids = [c.identifier_in_scene for c in visible_character_objs]
                self.continuity_memory.update_for_shot(
                    shot_idx=scene.scene_id or 0,
                    frame_path=raw_frame_path if os.path.exists(raw_frame_path) else first_frame_path,
                    scene_id=f"scene_{scene.scene_id}",
                    location=location_name,
                    visible_characters=visible_char_ids,
                    visible_props=None,
                    shot_description=prompt,
                )
            
            # 3. Generate video using the RAW first frame as reference
            ref_images = []
            video_ref_frame = raw_frame_path if os.path.exists(raw_frame_path) else first_frame_path
            if os.path.exists(video_ref_frame):
                ref_images.append(video_ref_frame)
            
            # Add character portraits as additional references (up to 2 total character refs)
            if prioritized_char_refs:
                for img in prioritized_char_refs:
                    if len(ref_images) >= 2: # Veo limit
                        break
                    if img not in ref_images:
                        ref_images.append(img)
            
            video_output = await self.video_generator.generate_single_video(
                prompt=prompt,
                reference_image_paths=ref_images if ref_images else None,
            )
            
            # Save debug prompt
            debug_dir = os.path.join(scene_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "scene_video_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)
            
            # Save video
            if video_output:
                if video_output.fmt == "url" and video_output.data:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(video_output.data) as resp:
                            if resp.status == 200:
                                with open(output_path, 'wb') as f:
                                    f.write(await resp.read())
                                return output_path
                elif video_output.fmt == "bytes" and video_output.data:
                    with open(output_path, 'wb') as f:
                        f.write(video_output.data)
                    return output_path
                elif hasattr(video_output, 'video_path') and video_output.video_path:
                    shutil.copy(video_output.video_path, output_path)
                    return output_path
                
        except Exception as e:
            self.logger.error(f"Failed to generate scene {scene.scene_id}: {e}")
        
        return None

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        frame_desc: str,
        character_portraits_registry: Optional[Dict[str, Any]] = None
    ) -> None:
        """Composite character portraits onto a frame for consistency.
        
        Args:
            frame_path: Path to the frame image
            visible_characters: List of characters that should appear
            frame_desc: Frame description for positioning hints
            character_portraits_registry: Optional registry with portrait paths (standard format)
        """
        if not visible_characters or not os.path.exists(frame_path):
            return
            
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            portrait_path = None
            
            # Use view/expression selector to get correct portrait
            view = get_character_view_for_shot(frame_desc)
            expression = get_character_expression_for_shot(frame_desc)
            
            # 1. Try local portraits first (with both key formats)
            if char_id in self.local_portraits:
                local_entry = self.local_portraits[char_id]
                # Try view-specific path first
                view_path = local_entry.get(f"{view.value}_path") or local_entry.get(view.value, {}).get("path")
                if not view_path:
                    portrait_path = local_entry.get("front_path") or local_entry.get("front", {}).get("path")
                else:
                    portrait_path = view_path
            
            # 2. Try character_portraits registry (standard format: {char_id: {"front": {"path": ...}}})
            if not portrait_path and character_portraits_registry and char_id in character_portraits_registry:
                registry_entry = character_portraits_registry[char_id]
                # Try view-specific entry
                view_entry = registry_entry.get(view.value, {})
                if isinstance(view_entry, dict):
                    # Try expression-specific path
                    expr_entry = view_entry.get(expression.value, {})
                    if isinstance(expr_entry, dict):
                        portrait_path = expr_entry.get("path")
                    else:
                        portrait_path = expr_entry if isinstance(expr_entry, str) else None
                    if not portrait_path:
                        portrait_path = view_entry.get("path")
                elif isinstance(view_entry, str):
                    portrait_path = view_entry
                
                # Fallback to front view
                if not portrait_path:
                    front_entry = registry_entry.get("front", {})
                    if isinstance(front_entry, dict):
                        portrait_path = front_entry.get("path")
                    elif isinstance(front_entry, str):
                        portrait_path = front_entry
            
            # 3. Try self.character_portraits registry (URL-based from S3 loader)
            if not portrait_path and char_id in self.character_portraits:
                cp_entry = self.character_portraits[char_id]
                # Try view-specific entry
                view_entry = cp_entry.get(view.value, {})
                if isinstance(view_entry, dict):
                    # Try expression-specific path
                    expr_entry = view_entry.get(expression.value, {})
                    if isinstance(expr_entry, dict):
                        portrait_path = expr_entry.get("path")
                    else:
                        portrait_path = expr_entry if isinstance(expr_entry, str) else None
                    if not portrait_path:
                        portrait_path = view_entry.get("path")
                elif isinstance(view_entry, str):
                    portrait_path = view_entry
                
                # Fallback to front view
                if not portrait_path:
                    front_entry = cp_entry.get("front", {})
                    if isinstance(front_entry, dict):
                        portrait_path = front_entry.get("path")
                    elif isinstance(front_entry, str):
                        portrait_path = front_entry
            
            if portrait_path and os.path.exists(portrait_path):
                portraits_to_composite.append(portrait_path)
        
        if not portraits_to_composite:
            return
            
        try:
            if len(portraits_to_composite) == 1:
                position = get_character_position_from_description(frame_desc, visible_characters[0].identifier_in_scene if visible_characters else None)
                scale = get_character_scale_from_shot_type(frame_desc)
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=portraits_to_composite[0],
                    output_path=frame_path,
                    position=position,
                    scale_factor=min(scale, 0.5),
                    blend_mode="soft",
                )
                self.logger.info(f"Composited 1 character onto: {frame_path}")
            else:
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=portraits_to_composite,
                    output_path=frame_path,
                )
                self.logger.info(f"Composited {len(portraits_to_composite)} characters onto: {frame_path}")
        except Exception as e:
            self.logger.warning(f"Failed to composite characters onto {frame_path}: {e}")
    
    def _build_scene_prompt(self, scene: PodcastScene, script: str) -> str:
        """Build a video generation prompt for a scene with podcast-specific direction"""
        # Base style
        style = self.config.video_style
        
        # Scene type specific prompts
        type_prompts = {
            SceneType.INTRO: "Energetic opening sequence with character introductions",
            SceneType.QA: "Educational Q&A segment with visual explanations",
            SceneType.SONG: "Musical performance with animated characters singing",
            SceneType.SKIT: "Comedic skit with character interactions",
            SceneType.GAME: "Fun game show segment with competition elements",
            SceneType.STORY: "Gentle storytelling with soft visuals and narration",
            SceneType.TECH_BREAK: "Invention showcase with gadgets and demonstrations",
            SceneType.SILENT_WONDER: "Quiet, contemplative scene with subtle animations",
            SceneType.RECAP: "Summary segment with key points highlighted",
            SceneType.OUTRO: "Warm farewell with all characters together",
        }
        
        type_desc = type_prompts.get(scene.scene_type, "Character interaction scene")
        
        # Character descriptions with positions
        char_descs = []
        for i, char_id in enumerate(scene.characters_present[:4]):  # Limit to 4 main characters
            if char_id in self.characters:
                char = self.characters[char_id]
                position = "center frame" if i == 0 else f"{'left' if i % 2 else 'right'} of frame"
                char_descs.append(f"{char_id} ({position}): {char.static_features[:100]}")
        
        # Get visual direction from profile
        visual_direction = PODCAST_PROFILE.visual_profile
        
        # Build prompt with PODCAST-SPECIFIC constraints
        prompt = f"""Create a {style} video scene for a children's educational podcast.

CRITICAL PODCAST RULES:
- Background must be a CONSISTENT STUDIO SET - same backdrop throughout
- Characters are SEATED or STANDING in fixed positions - minimal movement
- Characters talk, gesture, and react but do NOT walk around or change locations
- Focus on EXPRESSIONS and DIALOGUE-DRIVEN engagement
- Camera: Studio multi-cam setup with smooth transitions between speakers

Scene Type: {type_desc}
Setting: {scene.setting} (PODCAST STUDIO - consistent background)

Visual Style:
- Camera: {visual_direction.camera_style}
- Lighting: {visual_direction.lighting_style}
- Atmosphere: {visual_direction.atmosphere}
- Cut Rhythm: {visual_direction.cut_rhythm}

Characters Present (in fixed studio positions):
{chr(10).join(char_descs)}

Scene Script (key moments):
{script[:500]}...

Style: {style}. Vibrant, engaging, kid-friendly animation. Characters should be expressive 
with gestures and facial expressions. Warm, inviting studio atmosphere.
The background MUST REMAIN CONSISTENT - same studio set throughout."""

        return prompt
    
    async def generate_podcast_video(
        self,
        parsed_podcast: ParsedPodcast,
        max_scenes: Optional[int] = None
    ) -> str:
        """Generate complete podcast video from parsed script"""
        scenes_to_process = parsed_podcast.scenes
        if max_scenes:
            scenes_to_process = scenes_to_process[:max_scenes]
        
        self.logger.info(f"Generating video for {len(scenes_to_process)} scenes")
        
        # Generate each scene
        scene_videos = []
        for scene in scenes_to_process:
            scene_dir = os.path.join(self.working_dir, f"scene_{scene.scene_id:02d}")
            video_path = await self.generate_scene_video(scene, scene_dir)
            if video_path:
                scene_videos.append((scene, video_path))
        
        if not scene_videos:
            raise RuntimeError("No scene videos were generated")
        
        # Assemble final video
        final_video_path = await self._assemble_final_video(
            parsed_podcast.title,
            scene_videos
        )
        
        return final_video_path
    
    async def _assemble_final_video(
        self,
        title: str,
        scene_videos: List[Tuple[PodcastScene, str]]
    ) -> str:
        """Assemble scene videos into final podcast video"""
        self.logger.info(f"Assembling {len(scene_videos)} scenes into final video")
        
        clips = []
        for scene, video_path in scene_videos:
            try:
                clip = VideoFileClip(video_path)
                clips.append(clip)
            except Exception as e:
                self.logger.warning(f"Could not load scene {scene.scene_id}: {e}")
        
        if not clips:
            raise RuntimeError("No valid video clips to assemble")
        
        # Concatenate
        final_clip = concatenate_videoclips(clips, method="compose")
        
        # Generate and add audio if videos don't have audio
        output_path = os.path.join(self.working_dir, f"{title.replace(' ', '_')}_final.mp4")
        
        # Check if any clip has audio
        has_audio = any(clip.audio is not None for clip in clips)
        
        if not has_audio:
            # Generate audio for podcast
            audio_path = os.path.join(self.working_dir, "final_audio.mp3")
            from utils.pipeline.audio_helper import generate_audio_for_video, add_audio_to_video
            
            # Collect audio descriptions from scenes
            audio_descriptions = []
            for scene, _ in scene_videos:
                if hasattr(scene, 'narration') and scene.narration:
                    audio_descriptions.append(scene.narration)
                elif hasattr(scene, 'dialogue') and scene.dialogue:
                    audio_descriptions.append(scene.dialogue)
            
            generated_audio = await generate_audio_for_video(
                video_duration=final_clip.duration,
                audio_descriptions=audio_descriptions if audio_descriptions else None,
                output_path=audio_path,
                force_regenerate=getattr(self.config, 'force_regenerate', False),
            )
            
            if generated_audio and os.path.exists(generated_audio):
                if add_audio_to_video(final_clip, generated_audio, output_path, codec="libx264", audio_codec="aac", preset="medium"):
                    self.logger.info(f"Final video with audio saved: {output_path}")
                else:
                    # Fallback: save without audio
                    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
                    self.logger.warning("Failed to add audio, saved video without audio")
            else:
                # Save video without audio
                final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
                self.logger.info(f"Final video saved without audio: {output_path}")
        else:
            # Videos already have audio, just save
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
            self.logger.info(f"Final video saved: {output_path}")
        
        # Cleanup
        for clip in clips:
            clip.close()
        final_clip.close()
        
        return output_path
    
    async def run(
        self,
        script_path: Optional[str] = None,
        max_scenes: Optional[int] = None,
        audience: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "podcast",
        topic_area: Optional[str] = None,
        restitch_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete podcast to video pipeline.
        
        Args:
            script_path: Path to podcast script (optional if auto_ideate=True)
            max_scenes: Maximum number of scenes to process
            audience: Target audience
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate podcast episode idea
            ideation_mode: Mode for auto-ideation
            topic_area: Topic area for podcast ideation
        
        Returns:
            Dictionary containing output metadata
        """
        self.logger.info(f"Starting Podcast2Video pipeline")
        
        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="podcast")
            trend_context_block = trend_context.to_context_block()
            # Save trend data
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Ideation
        ideation_path = os.path.join(self.working_dir, "ideation.json")
        if auto_ideate and os.path.exists(ideation_path) and not self.config.force_regenerate if hasattr(self.config, 'force_regenerate') else False:
            self.logger.info(f"  Resuming from existing ideation: {ideation_path}")
            with open(ideation_path, "r", encoding="utf-8") as f:
                ideation_data = json.load(f)
                podcast_idea = PodcastEpisodeIdea(**ideation_data)
                topic_area = ideation_data.get("topic_area", topic_area)
                if not script_path and os.path.exists(os.path.join(self.working_dir, "generated_script.txt")):
                    script_path = os.path.join(self.working_dir, "generated_script.txt")
        elif auto_ideate:
            self.logger.info(f"🧠 Auto-ideating podcast episode in {ideation_mode} mode...")
            # ... (Ideation logic) ...
            if self.config.brand_id:
                resolution = resolve_s3_entities(texts=[topic_area or ""], brand_hint=self.config.brand_id, working_dir=self.working_dir)
                brand_ctx = resolution.get("brand_context"); game_ctx = resolution.get("game_context")
            podcast_idea = await self.ideation_engine.ideate_podcast_episode(topic_area=topic_area, trend_context=trend_context)
            ideation_output = podcast_idea.model_dump()
            if brand_ctx: ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx: ideation_output["game_context"] = game_ctx.model_dump()
            with open(ideation_path, "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)
            if not script_path:
                script_path = await self._generate_script_from_idea(podcast_idea)

        # RESUME CHECK: Parsed Podcast
        parsed_path = os.path.join(self.working_dir, "parsed_podcast.json")
        if os.path.exists(parsed_path) and not self.config.force_regenerate if hasattr(self.config, 'force_regenerate') else False:
            self.logger.info(f"  Resuming from existing parsed podcast: {parsed_path}")
            with open(parsed_path, "r", encoding="utf-8") as f:
                from agents.podcast_script_parser import ParsedPodcast
                parsed = ParsedPodcast(**json.load(f))
        else:
            # Step 1: Resolve brand/game from script
            # ... (Existing step 1-3 logic) ...
            script_text = ""
            try:
                with open(script_path, 'r', errors='ignore') as f: script_text = f.read()
            except Exception: script_text = ""
            resolution = resolve_s3_entities(texts=[script_text], brand_hint=self.config.brand_id, working_dir=self.working_dir)
            brand_id = resolution.get("brand_id") or self.config.brand_id
            game_id = resolution.get("game_id")
            await self.load_characters_from_s3(brand_id=brand_id, game_id=game_id)
            
            # Save debug info
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "script_parsing_input.txt"), "w", encoding="utf-8") as f:
                f.write(f"Script path: {script_path}\nBrand: {brand_id}\nGame: {game_id}")

            parsed = self.parse_script(script_path)
        
        # Plan audio requirements for podcast scenes
        audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not (self.config.force_regenerate if hasattr(self.config, 'force_regenerate') else False):
            self.logger.info("Loading existing audio plan...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None:
            self.logger.info("Planning audio requirements for podcast scenes...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert podcast scenes to Scene objects for audio planning
                scene_objects = []
                for idx, scene in enumerate(parsed.scenes):
                    scene_script = self.script_parser.get_scene_script(scene)
                    scene_obj = Scene(
                        idx=idx,
                        is_last=(idx == len(parsed.scenes) - 1),
                        environment=EnvironmentInScene(
                            slugline=f"PODCAST SCENE {scene.scene_id}",
                            description=scene.scene_type.value if hasattr(scene.scene_type, 'value') else str(scene.scene_type),
                        ),
                        characters=list(self.characters.values()) if self.characters else [],
                        script=scene_script,
                    )
                    scene_objects.append(scene_obj)
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,
                    previous_audio_plan=None,
                    style=self.config.video_style,
                    audience=None,
                    content_format="animated",  # Podcasts are typically animated
                )
                
                self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                self.logger.info(f"Audio plan created with {len(audio_plan.scene_plans)} scene plans")
            except Exception as e:
                self.logger.warning(f"Failed to create audio plan: {e}. Continuing without detailed audio planning.")
                audio_plan = None
        
        self.audio_plan = audio_plan
        
        # Director reasoning: from config (video_style, audio_style); no Director agent
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast2video",
            director_name="Podcast2Video (config)",
            rationale=(
                "No dedicated Director agent; creative direction comes from PodcastConfig: video_style "
                "(e.g. '3D animated cartoon style, colorful, kid-friendly') and audio_style (e.g. 'warm, "
                "engaging, kid-friendly podcast voice'). PODCAST_PROFILE.visual_profile supplies "
                "camera_style, lighting_style, atmosphere, cut_rhythm. These steer _build_scene_prompt "
                "and thus each scene's video generation."
            ),
            inputs={
                "video_style": self.config.video_style,
                "audio_style": self.config.audio_style,
            },
            outputs={"config": "Feeds into _build_scene_prompt and generate_scene_video."},
        )
        
        # RESUME CHECK: Final Video (OR restitch_only)
        final_video_fname = f"{parsed.title.replace(' ', '_')}_final.mp4"
        final_video_path = os.path.join(self.working_dir, final_video_fname)
        if (os.path.exists(final_video_path) and not self.config.force_regenerate if hasattr(self.config, 'force_regenerate') else False) and not restitch_only:
            self.logger.info(f"  Resuming from existing final video: {final_video_path}")
            final_path = final_video_path
        else:
            # Step 4: Generate video
            if restitch_only:
                self.logger.info("Restitch only mode: Skipping video generation phase.")
                # We need to manually assemble from existing scenes
                scene_videos = []
                for scene in parsed.scenes:
                    scene_dir = os.path.join(self.working_dir, f"scene_{scene.scene_id:02d}")
                    v_path = os.path.join(scene_dir, "scene_video.mp4")
                    if os.path.exists(v_path):
                        scene_videos.append((scene, v_path))
                final_path = await self._assemble_final_video(parsed.title, scene_videos)
            else:
                final_path = await self.generate_podcast_video(parsed, max_scenes)
        
        # Cinematographer/picturization: _build_scene_prompt, scene type, video_style, character blocking
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast2video",
            rationale=(
                "Each scene's video is driven by _build_scene_prompt: scene type (INTRO, QA, SONG, SKIT, "
                "GAME, STORY, etc.) maps to type_prompts; config.video_style and PODCAST_PROFILE "
                "visual_profile (camera_style, lighting_style, atmosphere, cut_rhythm) define the look. "
                "Character blocking (center/left/right) and S3 character portraits as reference_images "
                "shape the frame. Studio-set consistency and dialogue-driven engagement are enforced. "
                "Scene scripts and setting feed the prompt; videos are concatenated into the final episode."
            ),
            inputs={
                "video_style": self.config.video_style,
                "total_scenes": len(parsed.scenes),
                "scene_types": list(dict.fromkeys(s.scene_type.value for s in parsed.scenes))[:8],
            },
            outputs={
                "scene_XX/scene_video.mp4": "Per-scene video from _build_scene_prompt.",
                f"{parsed.title.replace(' ', '_')}_final.mp4": "Concatenated final video.",
            },
        )
        
        # Calculate duration
        total_duration_seconds = parsed.estimated_total_duration or 300
        try:
            final_clip = VideoFileClip(final_path)
            total_duration_seconds = int(final_clip.duration)
            final_clip.close()
        except Exception:
            pass
        
        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_podcast(
            title=parsed.title,
            description=f"Podcast episode with {len(parsed.scenes)} scenes featuring characters: {', '.join(parsed.all_characters[:5])}",
            audience=audience or "General",
            duration_minutes=total_duration_seconds // 60,
            category="Kids Entertainment" if "kid" in self.config.video_style.lower() else "Entertainment",
            trend_context=trend_context_block if trend_context_block else None,
        )
        
        # Save output metadata
        output_metadata = {
            "run_id": self.run_id,
            "script_path": script_path,
            "title": parsed.title,
            "audience": audience,
            "trendy": trendy,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "podcast_idea": podcast_idea.model_dump() if podcast_idea else None,
            "video_path": final_path,
            "duration_seconds": total_duration_seconds,
            "total_scenes": len(parsed.scenes),
            "characters": parsed.all_characters,
            "monetization_plan": monetization_plan.model_dump(),
        }
        with open(os.path.join(self.working_dir, "output.json"), "w", encoding="utf-8") as f:
            json.dump(output_metadata, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Pipeline complete! Final video: {final_path}")
        return output_metadata
    
    async def _generate_script_from_idea(self, idea: PodcastEpisodeIdea) -> str:
        """Generate a simple podcast script from an episode idea."""
        script_path = os.path.join(self.working_dir, "generated_script.txt")
        
        # Build a simple script structure
        script_lines = [
            f"PODCAST EPISODE: {idea.episode_title}",
            f"TOPIC: {idea.topic}",
            "",
            "---",
            "",
            "SCENE 1: INTRO",
            "Setting: Podcast studio",
            "",
            "HOST: Welcome to another episode! Today we're diving into something really exciting.",
            f"HOST: Our topic today is: {idea.topic}",
            "",
        ]
        
        # Add key points as scenes
        for i, point in enumerate(idea.key_points, start=2):
            script_lines.extend([
                f"---",
                "",
                f"SCENE {i}: DISCUSSION - {point[:50]}...",
                f"Setting: Podcast studio",
                "",
                f"HOST: Let's talk about {point}",
                "",
            ])
        
        # Add guest suggestion if available
        if idea.guest_suggestion:
            script_lines.extend([
                "---",
                "",
                f"SCENE {len(idea.key_points) + 2}: GUEST SEGMENT",
                "Setting: Podcast studio with guest",
                "",
                f"HOST: We have a special guest today - {idea.guest_suggestion}",
                "",
            ])
        
        # Add outro
        script_lines.extend([
            "---",
            "",
            "SCENE FINAL: OUTRO",
            "Setting: Podcast studio",
            "",
            "HOST: That's all for today's episode! Thanks for tuning in.",
        ])
        
        if idea.call_to_action:
            script_lines.append(f"HOST: {idea.call_to_action}")
        
        script_lines.append("HOST: See you next time!")
        
        # Write script
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("\n".join(script_lines))
        
        self.logger.info(f"Generated podcast script: {script_path}")
        return script_path
