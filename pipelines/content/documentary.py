"""
Idea to Documentary Video Pipeline

Generates documentary videos from topics with research,
narration, visual segments, and monetization recommendations.

Supports S3 entity resolution for brands, games, and presenter/host
characters with visual consistency via post-processing compositing.
"""
import json
import logging
import os
import re
import shutil
from typing import Optional, Dict, Any, List, Literal

import yaml

from configs.constants.content_constants import (
    CONTENT_FORMAT_LIVE_ACTION,
    CONTENT_FORMAT_ANIMATED,
    CONTENT_FORMAT_HYBRID,
)
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing import DocumentaryScreenwriter
from agents.directors.film import DocumentaryDirector
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from agents.producers.visuals import StoryboardArtist
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from interfaces.content.shot_description import ShotBriefDescription
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.generator_factory import create_generators
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.media.image import (
    composite_character_on_image,
    composite_multiple_characters,
    composite_prop_on_image,
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
from utils.media.video import concat_videos
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from interfaces.entities.character import CharacterInScene
from configs.constants.pipeline_profiles import DOCUMENTARY_PROFILE


class DocumentaryPipeline:
    """Pipeline to generate documentary videos from topics."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/documentary",
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
            pipeline_name="documentary",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.documentary_screenwriter = DocumentaryScreenwriter(chat_model=self.chat_model, pipeline_kind="documentary")
        self.documentary_director = DocumentaryDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="documentary")
        from utils.pipeline.continuity import ContinuityMemory
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="documentary")
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="documentary", run_id=self.run_id, local_dir=self.working_dir)

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

    async def _generate_segment_visual(
        self,
        segment_title: str,
        segment_narration: str,
        style: str,
        content_format: str,
        output_path: str,
        presenter_portrait: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        presenter: Optional[CharacterInScene] = None,
        character_portraits_registry: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate a visual frame for a documentary segment."""
        if not self.image_generator:
            return None
        
        format_hint = {
            CONTENT_FORMAT_ANIMATED: "animated, motion graphics, illustrated",
            CONTENT_FORMAT_HYBRID: "mixed media, archival footage style, documentary",
            CONTENT_FORMAT_LIVE_ACTION: "photorealistic, documentary footage, cinematic",
        }.get(content_format, "documentary style")
        
        # TRACK 1: BACKGROUND GENERATION (Clean Environment)
        bg_prompt = f"""Documentary visual background for segment "{segment_title}".
{segment_narration[:300]}
Style: {style}, {format_hint}. Professional documentary quality, informative, visually compelling.
EMPTY ENVIRONMENT ONLY. No characters, no people, no robots, no figures."""
        
        try:
            # Use character portraits as references (clamped to 2)
            refs = reference_images[:2] if reference_images else None
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_bg_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(bg_prompt)

            bg_output = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=refs,
            )
            bg_output.save(output_path)
            
            # TRACK 2: COMPOSITE PRESENTER (S3 Portrait)
            if presenter_portrait and os.path.exists(presenter_portrait):
                try:
                    composite_character_on_image(
                        background_path=output_path,
                        character_path=presenter_portrait,
                        output_path=output_path,
                        position="left",  # Presenter on left, content on right
                        scale_factor=0.35,
                        blend_mode="soft",
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to composite presenter: {e}")
            
            # TRACK 3: RAW GENERATION (Gelled Presenter)
            raw_output_path = output_path.replace(".png", "_raw.png")
            
            # Build character context if presenter has static_features
            char_context = ""
            view_instruction = ""
            expression_instruction = ""
            if presenter and presenter.static_features:
                char_context = f" Presenter: {presenter.static_features}."
                view = get_character_view_for_shot(segment_narration)
                expression = get_character_expression_for_shot(segment_narration)
                view_instruction = f" Camera angle: {view.value} view."
                expression_instruction = f" Presenter expression: {expression.value}."
            
            raw_prompt = f"""Documentary visual for segment "{segment_title}".
{segment_narration[:300]}.{char_context}{view_instruction}{expression_instruction}
Style: {style}, {format_hint}. Professional documentary quality, informative, visually compelling.
High quality animation frame, expressive presenter gelled into scene. Blend presenter naturally into environment. No text, no collages."""
            
            # Build raw references: composite frame + presenter portrait with view/expression
            raw_refs = [output_path]  # Start with composite frame
            if presenter_portrait and os.path.exists(presenter_portrait):
                # If we have character_portraits_registry, try to get view/expression-specific portrait
                presenter_portrait_path = presenter_portrait
                if presenter and character_portraits_registry:
                    char_id = presenter.identifier_in_scene
                    if char_id in character_portraits_registry:
                        view = get_character_view_for_shot(segment_narration)
                        expression = get_character_expression_for_shot(segment_narration)
                        
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
                        
                        # Fallback to provided presenter_portrait
                        if path and os.path.exists(path):
                            presenter_portrait_path = path
                
                raw_refs.append(presenter_portrait_path)
            
            with open(os.path.join(debug_dir, os.path.basename(output_path).replace(".png", "_raw_prompt.txt")), "w", encoding="utf-8") as f:
                f.write(raw_prompt)
            
            raw_output = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                strength=0.55,  # Blend with composite
            )
            raw_output.save(raw_output_path)
            
            return raw_output_path if os.path.exists(raw_output_path) else output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate visual for segment '{segment_title}': {e}")
            return None

    async def _generate_segment_video(
        self,
        segment_title: str,
        segment_narration: str,
        style: str,
        content_format: str,
        output_path: str,
        first_frame_path: Optional[str] = None,
        presenter_portrait: Optional[str] = None,
        duration_seconds: int = 30,
    ) -> Optional[str]:
        """Generate a video for a documentary segment."""
        if not self.video_generator:
            return None
        
        format_hint = {
            CONTENT_FORMAT_ANIMATED: "animated documentary, motion graphics, illustrated visuals",
            CONTENT_FORMAT_HYBRID: "mixed media documentary, archival and animated",
            CONTENT_FORMAT_LIVE_ACTION: "live-action documentary, cinematic footage",
        }.get(content_format, "documentary style")
        
        prompt = f"""Documentary video segment: "{segment_title}".
Narration: {segment_narration[:400]}
Style: {style}, {format_hint}. Professional documentary quality with smooth transitions.
Duration: approximately {duration_seconds} seconds of compelling visual content."""
        
        try:
            refs = []
            raw_frame_path = first_frame_path.replace(".png", "_raw.png") if first_frame_path else None
            # Use raw frame for video if available, otherwise fallback to composited
            video_ref_frame = raw_frame_path if raw_frame_path and os.path.exists(raw_frame_path) else first_frame_path
            
            if video_ref_frame and os.path.exists(video_ref_frame):
                refs.append(video_ref_frame)
            if presenter_portrait and os.path.exists(presenter_portrait) and len(refs) < 2:
                refs.append(presenter_portrait)
            
            # Clamp duration to API limits
            clamped_duration = max(4, min(8, duration_seconds))
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
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
            self.logger.warning(f"Failed to generate video for segment '{segment_title}': {e}")
            return None

    async def __call__(
        self,
        topic: Optional[str] = None,
        target_duration_minutes: int = 30,
        research_depth: str = "moderate",
        audience: Optional[str] = None,
        style: str = "informative and engaging",
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        content_format: Literal["live_action", "animated", "hybrid"] = CONTENT_FORMAT_LIVE_ACTION,
        generate_visuals: bool = True,
        generate_videos: bool = True,
        presenter_id: Optional[str] = None,
        presenter: Optional[CharacterInScene] = None,
        presenter_portrait_path: Optional[str] = None,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        restitch_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate documentary video from a topic.

        Args:
            topic: Documentary topic (optional if auto_ideate=True)
            target_duration_minutes: Target duration (10-60 minutes)
            research_depth: Research depth (light, moderate, deep)
            audience: Target audience (teens, adults, family, etc.)
            style: Documentary style
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate documentary topic
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
            content_format: 'live_action', 'animated', or 'hybrid' (mix of both)
            generate_visuals: Whether to generate segment visuals
            generate_videos: Whether to generate segment videos
            presenter_id: S3 character ID for documentary presenter/host
            presenter: Pre-built CharacterInScene for presenter
            presenter_portrait_path: Direct path to presenter portrait image
            brand_id: S3 brand ID for brand context
            game_id: S3 game ID for game context

        Returns:
            Dictionary with script, segments, visuals, videos, and monetization plan
        """
        ideation_result: Optional[IdeationResult] = None
        doc_context = ""
        output_json_path = os.path.join(self.working_dir, "documentary_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate and not restitch_only:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Resolve presenter/host from S3 if specified
        local_presenter_portrait: Optional[str] = presenter_portrait_path
        local_presenter: Optional[CharacterInScene] = presenter
        local_character_portraits_registry: Optional[Dict[str, Any]] = None
        reference_images: List[str] = []
        
        if presenter_id or brand_id or game_id:
            texts = []
            if presenter_id:
                texts.append(f"@character:{presenter_id}")
            if brand_id:
                texts.append(f"@brand:{brand_id}")
            if game_id:
                texts.append(f"@game:{game_id}")
            
            if texts:
                resolution = resolve_s3_entities(
                    texts=texts,
                    brand_hint=brand_id or brand_hint,
                    game_hint=game_id,
                    working_dir=self.working_dir,
                )
                
                # Collect reference images from resolution
                for ref in resolution.get("reference_images", []):
                    if ref.get("path") and os.path.exists(ref["path"]):
                        reference_images.append(ref["path"])
                
                # Extract presenter portrait from S3
                if presenter_id:
                    s3_chars_dir = os.path.join(self.working_dir, "s3_characters")
                    if os.path.exists(s3_chars_dir):
                        for char_folder in os.listdir(s3_chars_dir):
                            if char_folder.lower() == presenter_id.lower():
                                char_path = os.path.join(s3_chars_dir, char_folder)
                                if os.path.isdir(char_path):
                                    front_path = os.path.join(char_path, "front.png")
                                    if not os.path.exists(front_path):
                                        for f in os.listdir(char_path):
                                            if f.endswith(('.png', '.jpg', '.jpeg')):
                                                front_path = os.path.join(char_path, f)
                                                break
                                    if os.path.exists(front_path):
                                        local_presenter_portrait = front_path
                                        # Create presenter CharacterInScene
                                        metadata_path = os.path.join(char_path, "metadata.json")
                                        static_features = ""
                                        if os.path.exists(metadata_path):
                                            try:
                                                with open(metadata_path, "r") as f:
                                                    meta = json.load(f)
                                                    static_features = meta.get("description", "")
                                            except:
                                                pass
                                        local_presenter = CharacterInScene(
                                            idx=0,
                                            identifier_in_scene=char_folder,
                                            static_features=static_features,
                                            dynamic_features="Documentary presenter/host",
                                            is_visible=True,
                                        )
                                        
                                        # Build character portraits registry for view/expression selection
                                        if resolution.get("portrait_registry"):
                                            local_character_portraits_registry = resolution["portrait_registry"]
                                break
        
        if local_presenter_portrait:
            self.logger.info(f"Presenter portrait available: {local_presenter.identifier_in_scene if local_presenter else 'Custom'}")

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="documentary")
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
                topic = ideation_result.idea
                audience = audience or ideation_result.target_audience
        elif auto_ideate:
            self.logger.info(f"🧠 Auto-ideating documentary in {ideation_mode} mode...")
            # ... (Ideation logic) ...
            if ideation_mode == "brand" and brand_hint:
                resolution = resolve_s3_entities(texts=[brand_hint], brand_hint=brand_hint, working_dir=self.working_dir)
                brand_ctx = resolution.get("brand_context"); game_ctx = resolution.get("game_context")
                if brand_ctx or game_ctx:
                    ideation_result = await self.ideation_engine.ideate_for_brand(content_type="documentary", brand_context=brand_ctx, game_context=game_ctx, trend_context=trend_context)
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(content_type="documentary", mode=ideation_mode, audience=audience, trend_context=trend_context, brand_context=brand_ctx, game_context=game_ctx)
            topic = ideation_result.idea
            audience = audience or ideation_result.target_audience
            ideation_output = ideation_result.model_dump()
            if brand_ctx: ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx: ideation_output["game_context"] = game_ctx.model_dump()
            with open(ideation_path, "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)

        # Build context
        format_note = (
            "Content format: ANIMATED. Visuals should be stylized for 2D/3D animation."
            if content_format == CONTENT_FORMAT_ANIMATED
            else "Content format: live-action."
        )
        if content_format == CONTENT_FORMAT_HYBRID:
            format_note = "Content format: HYBRID (mix of live-action and animated elements)."

        # RESUME CHECK: Documentary Script
        script_path = os.path.join(self.working_dir, "documentary_script.json")
        if os.path.exists(script_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing documentary script: {script_path}")
            with open(script_path, "r", encoding="utf-8") as f:
                from agents.creative.writing import DocumentaryScript
                script = DocumentaryScript(**json.load(f))
        else:
            # Director & Screenwriter
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            director_brief = await self.documentary_director.direct(topic=topic, target_duration_minutes=target_duration_minutes, research_depth=research_depth, style=style, audience=audience, additional_context=f"{format_note}\n{trend_context_block or ''}".strip() or None)
            doc_context = f"{format_note}\n\n{trend_context_block or ''}\n\n{director_brief.to_context_block()}".strip()
            
            with open(os.path.join(debug_dir, "documentary_script_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"Topic: {topic}\nContext: {doc_context}")
            
            self.logger.info("Generating documentary script...")
            script = await self.documentary_screenwriter.write_documentary_script(topic=topic, target_duration_minutes=target_duration_minutes, research_depth=research_depth, audience=audience or "general", style=style, additional_context=doc_context)
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script.model_dump(), f, ensure_ascii=False, indent=2)

        # Phase 1 reasoning: rationale behind the documentary script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="documentary",
            phase_label="Phase 1: Story and script",
            content_type="documentary_script",
            rationale=(
                "The documentary script is structured into segments (opening hook, thesis, segments with narration, closing). "
                "DocumentaryDirector sets the research depth, tone, and narrative arc. DocumentaryScreenwriter uses "
                "the topic, target duration, and format (live-action, animated, hybrid) to shape the narration. "
                "Trends, when enabled, influence angle and framing so the doc feels current."
            ),
            inputs={
                "topic": topic,
                "target_duration_minutes": target_duration_minutes,
                "research_depth": research_depth,
                "audience": audience,
                "style": style,
                "content_format": content_format,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={
                "documentary_script.json": "Documentary script (title, thesis, segments with narration).",
                "narration.txt": "Flattened narration text for voiceover.",
            },
        )

        # Cinematographer and picturization reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="documentary",
            rationale=(
                "Picturization: each segment (opening, main segments, closing) gets a visual frame and "
                "video clip. The director's style and content_format (live-action, animated, hybrid) "
                "drive the visual prompts. Presenter/host portraits from S3 can be composited onto "
                "opening and key segments for consistent on-screen presence. All segment videos are "
                "concatenated into the final documentary. Visual style and narration drive B-roll, "
                "talking heads, animations, or archival footage choices."
            ),
            inputs={
                "content_format": content_format,
                "style": style,
                "generate_visuals": generate_visuals,
                "generate_videos": generate_videos,
                "presenter_used": local_presenter.identifier_in_scene if local_presenter else None,
            },
            outputs={
                "segments/*.png": "Visual frames per segment.",
                "segments/*.mp4": "Video clips per segment.",
                "documentary_final.mp4": "Concatenated final documentary video.",
                "narration.txt": "Narration text for voiceover.",
            },
        )

        # Save narration text
        narration_path = os.path.join(self.working_dir, "narration.txt")
        narration_text = f"# {script.title}\n\n{script.opening_hook}\n\n"
        for segment in script.segments:
            narration_text += f"## {segment.title}\n\n{segment.narration}\n\n"
        narration_text += f"\n{script.closing_statement}"
        with open(narration_path, "w", encoding="utf-8") as f:
            f.write(narration_text)

        # Plan audio requirements for documentary segments
        audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not self.force_regenerate:
            self.logger.info("Loading existing audio plan...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None:
            self.logger.info("Planning audio requirements for documentary segments...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert documentary segments to Scene objects for audio planning
                scene_objects = []
                # Opening hook
                scene_objects.append(Scene(
                    idx=0,
                    is_last=False,
                    environment=EnvironmentInScene(
                        slugline="DOCUMENTARY OPENING",
                        description="Opening segment",
                    ),
                    characters=[local_presenter] if local_presenter else [],
                    script=script.opening_hook or "",
                ))
                # Main segments
                for idx, segment in enumerate(script.segments):
                    scene_objects.append(Scene(
                        idx=idx + 1,
                        is_last=(idx == len(script.segments) - 1),
                        environment=EnvironmentInScene(
                            slugline=f"DOCUMENTARY SEGMENT: {segment.title}",
                            description=segment.title,
                        ),
                        characters=[local_presenter] if local_presenter else [],
                        script=segment.narration or "",
                    ))
                # Closing
                scene_objects.append(Scene(
                    idx=len(script.segments) + 1,
                    is_last=True,
                    environment=EnvironmentInScene(
                        slugline="DOCUMENTARY CLOSING",
                        description="Closing segment",
                    ),
                    characters=[local_presenter] if local_presenter else [],
                    script=script.closing_statement or "",
                ))
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,
                    previous_audio_plan=None,
                    style=style,
                    audience=audience,
                    content_format=content_format,
                )
                
                self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                self.logger.info(f"Audio plan created with {len(audio_plan.scene_plans)} segment plans")
            except Exception as e:
                self.logger.warning(f"Failed to create audio plan: {e}. Continuing without detailed audio planning.")
                audio_plan = None
        
        self.audio_plan = audio_plan

        # Prepare segment storage
        segment_visuals = {}
        segment_videos = {}
        
        # Calculate estimated segment duration for visuals
        total_segments = len(script.segments) + 2 # segments + opening + closing
        segment_duration_seconds = int((target_duration_minutes * 60) / total_segments) if total_segments > 0 else 30
        
        # RESUME CHECK: Final Documentary Video (OR restitch_only)
        final_video_path = os.path.join(self.working_dir, "documentary_final.mp4")
        segments_dir = os.path.join(self.working_dir, "segments")
        os.makedirs(segments_dir, exist_ok=True)
        
        if (os.path.exists(final_video_path) and not self.force_regenerate and not restitch_only):
            self.logger.info(f"  Resuming from existing final documentary: {final_video_path}")
        else:
            # Generate visuals and videos for each segment
            if generate_visuals or generate_videos:
                self.logger.info(f"Generating/Restitching visuals/videos for {len(script.segments) + 2} segments...")
                
                # Opening hook
                opening_visual_path = os.path.join(segments_dir, "00_opening_visual.png")
                opening_video_path = os.path.join(segments_dir, "00_opening_video.mp4")
                
                if (os.path.exists(opening_video_path) and not self.force_regenerate) or restitch_only:
                    if os.path.exists(opening_video_path):
                        segment_videos["opening"] = opening_video_path
                        if os.path.exists(opening_visual_path): segment_visuals["opening"] = opening_visual_path
                else:
                    if generate_visuals and (not os.path.exists(opening_visual_path) or self.force_regenerate):
                        visual = await self._generate_segment_visual(
                            segment_title="Opening", segment_narration=script.opening_hook,
                            style=style, content_format=content_format, output_path=opening_visual_path,
                            presenter_portrait=local_presenter_portrait, reference_images=reference_images,
                            presenter=local_presenter, character_portraits_registry=local_character_portraits_registry,
                        )
                        if visual: segment_visuals["opening"] = visual
                    if generate_videos and (not os.path.exists(opening_video_path) or self.force_regenerate):
                        video = await self._generate_segment_video(
                            segment_title="Opening", segment_narration=script.opening_hook,
                            style=style, content_format=content_format, output_path=opening_video_path,
                            first_frame_path=segment_visuals.get("opening"), presenter_portrait=local_presenter_portrait,
                            duration_seconds=min(segment_duration_seconds, 8),
                        )
                        if video: segment_videos["opening"] = video
                
                # Main segments
                for i, segment in enumerate(script.segments):
                    seg_visual_path = os.path.join(segments_dir, f"{i+1:02d}_{segment.title.replace(' ', '_')[:20]}_visual.png")
                    seg_video_path = os.path.join(segments_dir, f"{i+1:02d}_{segment.title.replace(' ', '_')[:20]}_video.mp4")
                    
                    if (os.path.exists(seg_video_path) and not self.force_regenerate) or restitch_only:
                        if os.path.exists(seg_video_path):
                            segment_videos[f"segment_{i+1}"] = seg_video_path
                            if os.path.exists(seg_visual_path): segment_visuals[f"segment_{i+1}"] = seg_visual_path
                        continue

                    if generate_visuals and (not os.path.exists(seg_visual_path) or self.force_regenerate):
                        visual = await self._generate_segment_visual(
                            segment_title=segment.title, segment_narration=segment.narration,
                            style=style, content_format=content_format, output_path=seg_visual_path,
                            presenter_portrait=local_presenter_portrait if i == 0 else None,
                            reference_images=reference_images,
                            presenter=local_presenter if i == 0 else None,
                            character_portraits_registry=local_character_portraits_registry,
                        )
                        if visual: segment_visuals[f"segment_{i+1}"] = visual
                    if generate_videos and (not os.path.exists(seg_video_path) or self.force_regenerate):
                        video = await self._generate_segment_video(
                            segment_title=segment.title, segment_narration=segment.narration,
                            style=style, content_format=content_format, output_path=seg_video_path,
                            first_frame_path=segment_visuals.get(f"segment_{i+1}"),
                            presenter_portrait=local_presenter_portrait if i == 0 else None,
                            duration_seconds=min(segment_duration_seconds, 8),
                        )
                        if video: segment_videos[f"segment_{i+1}"] = video
                
                # Closing
                closing_visual_path = os.path.join(segments_dir, f"{len(script.segments)+1:02d}_closing_visual.png")
                closing_video_path = os.path.join(segments_dir, f"{len(script.segments)+1:02d}_closing_video.mp4")
                
                if (os.path.exists(closing_video_path) and not self.force_regenerate) or restitch_only:
                    if os.path.exists(closing_video_path):
                        segment_videos["closing"] = closing_video_path
                        if os.path.exists(closing_visual_path): segment_visuals["closing"] = closing_visual_path
                else:
                    if generate_visuals and (not os.path.exists(closing_visual_path) or self.force_regenerate):
                        visual = await self._generate_segment_visual(
                            segment_title="Closing", segment_narration=script.closing_statement,
                            style=style, content_format=content_format, output_path=closing_visual_path,
                            presenter_portrait=local_presenter_portrait, reference_images=reference_images,
                            presenter=local_presenter, character_portraits_registry=local_character_portraits_registry,
                        )
                        if visual: segment_visuals["closing"] = visual
                    if generate_videos and (not os.path.exists(closing_video_path) or self.force_regenerate):
                        video = await self._generate_segment_video(
                            segment_title="Closing", segment_narration=script.closing_statement,
                            style=style, content_format=content_format, output_path=closing_video_path,
                            first_frame_path=segment_visuals.get("closing"), presenter_portrait=local_presenter_portrait,
                            duration_seconds=min(segment_duration_seconds, 8),
                        )
                        if video: segment_videos["closing"] = video
                
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
            
            # Concatenate all segment videos into final documentary (with music segments inserted)
            if generate_videos and segment_videos:
                self.logger.info("Concatenating segment videos into final documentary...")
                final_video_paths = []
                
                # Opening
                if "opening" in segment_videos:
                    final_video_paths.append(segment_videos["opening"])
                    # Check for music after opening
                    music_key = (0, 0)  # Opening is scene 0
                    if music_key in music_segments:
                        music_info = music_segments[music_key]
                        music_path = music_info["audio_path"]
                        if os.path.exists(music_path):
                            from moviepy import AudioFileClip, ColorClip
                            music_audio = AudioFileClip(music_path)
                            duration = music_audio.duration
                            music_video = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=duration).set_audio(music_audio)
                            temp_music_video = os.path.join(self.working_dir, "music_segment_opening.mp4")
                            music_video.write_videofile(temp_music_video, codec="libx264", audio_codec="aac", fps=24)
                            music_video.close()
                            music_audio.close()
                            final_video_paths.append(temp_music_video)
                
                # Main segments
                for i in range(len(script.segments)):
                    seg_key = f"segment_{i+1}"
                    if seg_key in segment_videos:
                        final_video_paths.append(segment_videos[seg_key])
                    
                    # Check for music after this segment
                    music_key = (i + 1, 0)  # Segment index + 1 (opening is 0)
                    if music_key in music_segments:
                        music_info = music_segments[music_key]
                        music_path = music_info["audio_path"]
                        if os.path.exists(music_path):
                            from moviepy import AudioFileClip, ColorClip
                            music_audio = AudioFileClip(music_path)
                            duration = music_audio.duration
                            music_video = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=duration).set_audio(music_audio)
                            temp_music_video = os.path.join(self.working_dir, f"music_segment_{seg_key}.mp4")
                            music_video.write_videofile(temp_music_video, codec="libx264", audio_codec="aac", fps=24)
                            music_video.close()
                            music_audio.close()
                            final_video_paths.append(temp_music_video)
                
                # Closing
                if "closing" in segment_videos:
                    final_video_paths.append(segment_videos["closing"])
                
                if len(final_video_paths) > 1:
                    try:
                        concat_videos(final_video_paths, final_video_path)
                        
                        # Generate and add audio if video doesn't have audio
                        from moviepy import VideoFileClip
                        from utils.pipeline.audio_helper import generate_audio_for_video, add_audio_to_video
                        
                        temp_clip = VideoFileClip(final_video_path)
                        has_audio = temp_clip.audio is not None
                        video_duration = temp_clip.duration
                        temp_clip.close()
                        
                        if not has_audio:
                            audio_path = os.path.join(self.working_dir, "final_audio.mp3")
                            # Collect narration text for audio generation
                            audio_descriptions = []
                            if script.opening_hook:
                                audio_descriptions.append(script.opening_hook)
                            for segment in script.segments:
                                if segment.narration:
                                    audio_descriptions.append(segment.narration)
                            if script.closing_statement:
                                audio_descriptions.append(script.closing_statement)
                            
                            generated_audio = await generate_audio_for_video(
                                video_duration=video_duration,
                                audio_descriptions=audio_descriptions if audio_descriptions else None,
                                output_path=audio_path,
                                force_regenerate=self.force_regenerate,
                            )
                            
                            if generated_audio and os.path.exists(generated_audio):
                                temp_clip = VideoFileClip(final_video_path)
                                if add_audio_to_video(temp_clip, generated_audio, final_video_path, codec="libx264", audio_codec="aac", preset="medium"):
                                    self.logger.info(f"Added audio to final documentary: {final_video_path}")
                                else:
                                    self.logger.warning("Failed to add audio to documentary")
                                temp_clip.close()
                        
                        self.logger.info(f"Final documentary saved: {final_video_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to concatenate videos: {e}")
                        final_video_path = None
                elif video_paths:
                    shutil.copy(video_paths[0], final_video_path)

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise(
            content_type="Documentary / Educational Long-form Video",
            content_summary=f"Title: {script.title}\nTopic: {script.topic}\nThesis: {script.thesis}\nDuration: {script.total_duration_minutes} minutes",
            audience=audience or "General",
            duration=f"{target_duration_minutes} minutes",
            genre="Documentary",
            additional_context=trend_context_block if trend_context_block else None,
        )

        # Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        if final_video_path and target_duration_minutes >= 2:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = json.dumps(script.model_dump(), ensure_ascii=False)
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_video_path,
                script_content=script_full_text,
                total_duration_seconds=target_duration_minutes * 60,
                content_type="documentary"
            )

        payload = {
            "run_id": self.run_id,
            "topic": topic,
            "target_duration_minutes": target_duration_minutes,
            "audience": audience,
            "trendy": trendy,
            "content_format": content_format,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "ideation_result": ideation_result.model_dump() if ideation_result else None,
            "script": script.model_dump(),
            "narration_path": narration_path,
            "segment_visuals": segment_visuals,
            "segment_videos": segment_videos,
            "final_video_path": final_video_path,
            "viral_shorts": viral_shorts,
            "presenter": local_presenter.identifier_in_scene if local_presenter else None,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=json.dumps(script.model_dump(), ensure_ascii=False),
                storyboard=list(segment_visuals.values()),
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
