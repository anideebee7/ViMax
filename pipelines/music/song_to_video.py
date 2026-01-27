"""
Song to Music Video Pipeline

Generates music video concepts and visuals from song data
with shot lists and monetization recommendations.
"""
import json
import logging
import os
import shutil
from typing import Optional, Dict, Any, List
import re

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.directors.audio import MusicVideoDirector
from agents.producers.business import MonetizationAdvisor
from agents.producers.analysis import CharacterExtractor
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators
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
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene
from configs.constants.pipeline_profiles import MUSIC_VIDEO_PROFILE
from configs.constants.content_constants import is_kids_audience


class Song2MusicVideoPipeline:
    """Pipeline to generate music video concepts from songs."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/music/song_to_music_video",
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
            pipeline_name="song2musicvideo",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.music_video_director = MusicVideoDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.logger = logging.getLogger(__name__)

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
        from utils.pipeline.generator_factory import create_generators_from_config
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

    async def __call__(
        self,
        song_title: str,
        lyrics: str,
        genre: str,
        mood: str,
        song_structure: Optional[str] = None,
        style: str = "cinematic",
        audience: Optional[str] = None,
        generate_storyboard_images: bool = True,
        trendy: bool = False,
        kids_mode: bool = False,
        # S3 Entity Integration
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate music video concept from song data. Supports kids animated music videos
        via kids_mode=True or when audience indicates children.

        Args:
            song_title: Title of the song
            lyrics: Song lyrics
            genre: Music genre
            mood: Song mood
            song_structure: Song structure (verse-chorus-verse, etc.)
            style: Visual style preference
            audience: Target audience (when kids/family, can drive kids-style visuals if kids_mode not set)
            generate_storyboard_images: Whether to generate storyboard frames
            trendy: Whether to incorporate trending visual styles
            kids_mode: If True, produce G-rated kids animated music video (colorful, age-appropriate, no mature content)
            brand_id: S3 brand ID for character loading
            game_id: S3 game ID for character loading
            character_names: Specific character names to include from S3

        Returns:
            Dictionary with concept, shot list, and monetization plan
        """
        # Resolve S3 entities for character consistency if provided
        characters: List[CharacterInScene] = []
        character_portraits_registry: Dict[str, Any] = {}
        is_s3_characters = False
        
        if brand_id or game_id or character_names:
            print(f"🔗 Resolving S3 entities for character consistency...")
            resolution = resolve_s3_entities(
                texts=[song_title, lyrics],
                brand_hint=brand_id,
                game_hint=game_id,
                working_dir=self.working_dir,
            )
            characters = resolution.get("characters") or []
            character_portraits_registry = resolution.get("portrait_registry") or {}
            is_s3_characters = len(characters) > 0
            if is_s3_characters:
                print(f"   Loaded {len(characters)} characters for music video.")
        
        # If no S3 characters, extract characters from lyrics
        if not characters:
            print(f"🔍 Extracting characters from lyrics...")
            try:
                characters = await self.character_extractor.extract_characters(lyrics)
                print(f"   Extracted {len(characters)} characters from lyrics.")
            except Exception as e:
                self.logger.warning(f"Failed to extract characters from lyrics: {e}")
                characters = []
        
        # Generate character portraits for ALL characters (S3 or extracted)
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
                            print(f"    Generated portrait for {char_id}")
                    except Exception as e:
                        self.logger.warning(f"    Failed to generate portrait for {char_id}: {e}")
                
                if os.path.exists(front_path):
                    character_portraits_registry[char_id] = {
                        "front": {
                            "path": front_path,
                            "description": f"Front view portrait of {char_id}"
                        }
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

        is_kids = kids_mode or is_kids_audience(audience)
        kids_context = ""
        if is_kids:
            kids_context = (
                "KIDS ANIMATED MUSIC VIDEO: Visual style must be G-rated, colorful, age-appropriate. "
                "No scary or mature content. Cute characters, friendly imagery, suitable for children. "
                "Animation: 2D or 3D kids cartoon. Bright, warm, safe. "
            )
        output_json_path = os.path.join(self.working_dir, "musicvideo_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fetch trends if trendy flag is set
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if trendy and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="music")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Concept
        concept_path = os.path.join(self.working_dir, "musicvideo_concept.json")
        if os.path.exists(concept_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing concept: {concept_path}")
            with open(concept_path, "r", encoding="utf-8") as f:
                from agents import MusicVideoConcept
                concept = MusicVideoConcept(**json.load(f))
        else:
            # Generate music video concept
            self.logger.info("Generating music video concept...")
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "concept_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Title: {song_title}\nLyrics: {lyrics[:1000]}\nGenre: {genre}\nMood: {mood}")

            extra = [s for s in (kids_context, trend_context_block) if s]
            concept = await self.music_video_director.direct_music_video(
                song_title=song_title,
                lyrics=lyrics,
                genre=genre,
                mood=mood,
                song_structure=song_structure,
                style="colorful 3D kids animation" if is_kids else style,
                audience=audience or ("children and families" if is_kids else "general"),
                additional_context="\n\n".join(extra) if extra else None,
            )
            with open(concept_path, "w", encoding="utf-8") as f:
                json.dump(concept.model_dump(), f, ensure_ascii=False, indent=2)

        # Director reasoning: MusicVideoDirector concept (creative lead for music video)
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song2musicvideo",
            director_name="MusicVideoDirector",
            rationale=(
                "MusicVideoDirector.direct_music_video produces the concept: concept_summary, aesthetic, "
                "and a shot list with visual_description per shot. The director translates lyrics, genre, "
                "mood, and song_structure into a visual plan. Style, audience, and kids_mode shape the "
                "aesthetic and shot choices. Trends can influence the look when enabled."
            ),
            inputs={
                "song_title": song_title,
                "genre": genre,
                "mood": mood,
                "style": style,
                "audience": audience,
                "kids_mode": is_kids,
            },
            outputs={"musicvideo_concept.json": "Concept (concept_summary, aesthetic, shots)."},
        )

        # Phase 1 reasoning: rationale behind the music video concept (creative "script" for visuals)
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song2musicvideo",
            phase_label="Phase 1: Music video concept",
            content_type="concept",
            rationale=(
                "The music video concept is the creative script for the visuals: concept_summary, aesthetic, "
                "and a shot list with visual_description per shot. MusicVideoDirector derives it from "
                "song_title, lyrics, genre, mood, and song_structure. Style, audience, and kids_mode "
                "(or kids audience) shape the aesthetic and shot choices. Trends can influence the look. "
                "The lyrics are the narrative input; the concept translates them into a visual plan."
            ),
            inputs={
                "song_title": song_title,
                "lyrics_preview": (lyrics or "")[:200] + "…",
                "genre": genre,
                "mood": mood,
                "song_structure": song_structure,
                "style": style,
                "audience": audience,
                "kids_mode": is_kids,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={
                "musicvideo_concept.json": "Concept (concept_summary, aesthetic, shots with visual_description).",
            },
        )

        # Generate storyboard images if requested
        storyboard_images = {}
        if generate_storyboard_images and self.image_generator:
            self.logger.info("Generating storyboard images...")
            storyboard_dir = os.path.join(self.working_dir, "storyboard")
            os.makedirs(storyboard_dir, exist_ok=True)

            # Reset continuity memory for this run
            self.continuity_memory.reset()
            
            # Track establishment frames per location
            location_establishment_frames = {}
            
            # Generate key frames (limit to avoid too many API calls)
            key_shots = concept.shots[:10] if len(concept.shots) > 10 else concept.shots
            for shot in key_shots:
                try:
                    vis_style = "Colorful kids cartoon, G-rated, cute, friendly." if is_kids else f"{style}. Cinematic, professional."
                    location_name = getattr(shot, "location", "Default Location")
                    
                    # Detect visible characters using word boundary regex (works for ALL characters)
                    visible_characters = []
                    for char in characters:
                        char_name = char.identifier_in_scene
                        if not char_name:
                            continue
                        # Use word boundary regex for precise matching (avoids partial matches)
                        pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                        if re.search(pattern, shot.visual_description):
                            visible_characters.append(char)
                    
                    # Get establishment frame and previous shot reference
                    establishment_frame = location_establishment_frames.get(location_name)
                    previous_shot_ref = self.continuity_memory.previous_shot_frame
                    
                    # --- TRACK 1: BACKGROUND GENERATION (Clean Environment) ---
                    bg_desc = shot.visual_description
                    for char in visible_characters:
                        bg_desc = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_desc)
                    
                    bg_prompt = f"Music video background scenery. Location: {location_name}. {bg_desc}. EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures. A beautiful, detailed background scene. High resolution. No text."
                    
                    bg_refs = []
                    if establishment_frame and os.path.exists(establishment_frame):
                        bg_refs.append(establishment_frame)
                    elif previous_shot_ref and os.path.exists(previous_shot_ref):
                        bg_refs.append(previous_shot_ref)
                    
                    bg_image_path = os.path.join(storyboard_dir, f"shot_{shot.shot_number:02d}_bg.png")
                    bg_output = await self.image_generator.generate_single_image(
                        prompt=bg_prompt,
                        reference_image_paths=bg_refs if bg_refs else None
                    )
                    bg_output.save(bg_image_path)
                    
                    # --- TRACK 2: COMPOSITE CHARACTERS (S3 Portraits) ---
                    image_path = os.path.join(storyboard_dir, f"shot_{shot.shot_number:02d}.png")
                    shutil.copy(bg_image_path, image_path)  # Start with background
                    
                    if visible_characters and character_portraits_registry:
                        self._composite_characters_on_frame(
                            frame_path=image_path,
                            visible_characters=visible_characters,
                            frame_desc=shot.visual_description,
                            character_portraits_registry=character_portraits_registry
                        )
                    
                    # --- TRACK 3: RAW GENERATION (Gelled Characters) ---
                    raw_image_path = os.path.join(storyboard_dir, f"shot_{shot.shot_number:02d}_raw.png")
                    
                    # Build character context with static_features
                    char_desc_parts = []
                    for char in visible_characters:
                        if char.static_features:
                            char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
                    char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
                    
                    # Add view and expression guidance
                    view_instruction = ""
                    expression_instruction = ""
                    if visible_characters:
                        view = get_character_view_for_shot(shot.visual_description)
                        expression = get_character_expression_for_shot(shot.visual_description)
                        view_instruction = f" Camera angle: {view.value} view."
                        expression_instruction = f" Character expressions: {expression.value}."
                    
                    raw_prompt = f"Music video scene. Location: {location_name}. {shot.visual_description}.{char_context}{view_instruction}{expression_instruction} {vis_style}. Professional animation quality, cinematic composition, proper lighting. Blend the characters naturally into the environment with shadows and reflections. Maintain the exact appearance of the characters from the reference image. No collages, no picture-in-picture, no separate reference image inserts."
                    
                    # Include ALL character portraits (not just 2) for multi-character scenes
                    raw_refs = [image_path]  # Start with composite frame
                    if visible_characters and character_portraits_registry:
                        # Prioritize characters based on role (main_host first)
                        prioritized_chars = sorted(
                            visible_characters, 
                            key=lambda x: 0 if getattr(x, "role", None) == "main_host" else 1
                        )
                        for char in prioritized_chars:
                            char_id = char.identifier_in_scene
                            if char_id in character_portraits_registry:
                                # Use view/expression selector
                                view = get_character_view_for_shot(shot.visual_description)
                                expression = get_character_expression_for_shot(shot.visual_description)
                                
                                # Try to get view-specific portrait
                                view_data = character_portraits_registry[char_id].get(view.value, {})
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
                                    p_info = character_portraits_registry[char_id].get("front", {})
                                    path = p_info.get("path") if isinstance(p_info, dict) else str(p_info) if p_info else None
                                
                                if path and os.path.exists(path) and path not in raw_refs:
                                    raw_refs.append(path)
                    
                    # Save debug prompt
                    debug_dir = os.path.join(storyboard_dir, "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, f"shot_{shot.shot_number:02d}_raw_prompt.txt"), "w", encoding="utf-8") as f:
                        f.write(raw_prompt)

                    raw_output = await self.image_generator.generate_single_image(
                        prompt=raw_prompt,
                        reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                        strength=0.55,  # Blend with composite
                    )
                    raw_output.save(raw_image_path)
                    
                    # Register establishment frame for location
                    if location_name not in location_establishment_frames:
                        location_establishment_frames[location_name] = raw_image_path
                    
                    # Update continuity memory
                    visible_char_ids = [c.identifier_in_scene for c in visible_characters]
                    self.continuity_memory.update_for_shot(
                        shot_idx=shot.shot_number - 1,
                        frame_path=raw_image_path if os.path.exists(raw_image_path) else image_path,
                        scene_id=f"scene_{location_name}",
                        location=location_name,
                        visible_characters=visible_char_ids,
                        visible_props=None,
                        shot_description=shot.visual_description,
                    )
                    
                    storyboard_images[f"shot_{shot.shot_number}"] = raw_image_path if os.path.exists(raw_image_path) else image_path
                except Exception as e:
                    self.logger.warning(f"Failed to generate storyboard for shot {shot.shot_number}: {e}")

        # Cinematographer/picturization: concept shot list and visual_description drive storyboard frames
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song2musicvideo",
            rationale=(
                "Picturization is driven by the concept's shot list: each shot has visual_description used "
                "as the image prompt for storyboard frames. Kids mode uses 'Colorful kids cartoon, G-rated'; "
                "otherwise style and 'Cinematic, professional' shape the look. The concept aesthetic and "
                "lyrics narrative define what to show when; storyboard_dir/shot_XX.png are the key frames. "
                "No in-pipeline video in this version; the storyboard supports downstream video or editorial."
            ),
            inputs={
                "concept_summary": (concept.concept_summary or "")[:150],
                "aesthetic": (getattr(concept, "aesthetic", None) or "")[:150],
                "shots_count": len(concept.shots),
                "style": style,
                "kids_mode": is_kids,
            },
            outputs={"storyboard/shot_*.png": "Storyboard frames from concept shot visual_description."},
        )

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=f"Music Video: {song_title}",
            description=f"Music video for '{song_title}' ({genre}). Mood: {mood}. Concept: {concept.concept_summary}",
            audience=audience or "General",
            duration_seconds=240,  # Assume ~4 minute song
            genre=genre,
            is_shorts=False,
            trend_context=trend_context_block if trend_context_block else None,
        )

        payload = {
            "run_id": self.run_id,
            "song_title": song_title,
            "genre": genre,
            "mood": mood,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "kids_mode": is_kids,
            "concept": concept.model_dump(),
            "storyboard_images": storyboard_images,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=lyrics,
                storyboard=concept.shots,
                video_metadata=payload
            )
            payload["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return payload

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        frame_desc: str,
        character_portraits_registry: Dict[str, Any],
    ) -> None:
        """Composite character portraits onto a generated frame with view/expression selection."""
        if not visible_characters or not os.path.exists(frame_path):
            return
        
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            if char_id in character_portraits_registry:
                # Use view/expression selector
                view = get_character_view_for_shot(frame_desc)
                expression = get_character_expression_for_shot(frame_desc)
                
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
                    portrait_info = character_portraits_registry[char_id].get("front", {})
                    path = portrait_info.get("path") if isinstance(portrait_info, dict) else str(portrait_info) if portrait_info else None
                
                if path and os.path.exists(path):
                    portraits_to_composite.append({"path": path, "name": char_id})
        
        if not portraits_to_composite:
            return
            
        try:
            if len(portraits_to_composite) == 1:
                position = get_character_position_from_description(frame_desc, portraits_to_composite[0]["name"])
                scale = get_character_scale_from_shot_type(frame_desc)
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=portraits_to_composite[0]["path"],
                    output_path=frame_path,
                    position=position,
                    scale_factor=min(scale, 0.5),
                    blend_mode="soft",
                )
            else:
                # Include ALL characters, not just first few
                paths = [p["path"] for p in portraits_to_composite]
                positions = [get_character_position_from_description(frame_desc, p["name"]) for p in portraits_to_composite]
                scales = [min(get_character_scale_from_shot_type(frame_desc), 0.5) for _ in portraits_to_composite]
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=paths,
                    output_path=frame_path,
                    positions=positions,
                    scale_factors=scales,
                )
        except Exception as e:
            self.logger.warning(f"Failed to composite characters onto {frame_path}: {e}")
