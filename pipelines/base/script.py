import json
import logging
import os
import re
import shutil
import asyncio
import time
from typing import Optional, Dict, List, Tuple, Literal, Any
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, concatenate_audioclips
from PIL import Image
from agents.creative.writing import Screenwriter
from agents.producers.analysis import CharacterExtractor, PropExtractor
from agents.producers.visuals import StoryboardArtist, PropReferenceGenerator
from agents.producers.visuals import CameraImageGenerator
from agents.directors.technical import Cinematographer
from agents.producers.visuals import ReferenceImageSelector
from agents.producers.visuals import BestImageSelector
from agents.producers.analysis import EventExtractor
from agents.producers.analysis import SceneExtractor
from agents.producers.analysis import NovelCompressor
from agents.producers.business import MonetizationAdvisor
from agents.directors.technical import VideoDirector
from agents.producers.visuals import CharacterPortraitsGenerator
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from agents.producers.audio import AudioPlanner
from utils.pipeline.series_bible import SeriesBible
import yaml
from interfaces.content.camera import Camera
from interfaces.content.frame import Frame
from interfaces.content.scene import Scene
from interfaces.content.shot_description import ShotDescription, ShotBriefDescription
from interfaces.content.director_brief import DirectorBrief
from interfaces.entities.character import CharacterInScene, CharacterInEvent, CharacterInNovel
from interfaces.entities.prop import PropInScene
from interfaces.entities.brand_context import BrandContext, GameContext, BrandVisuals, BrandCharacterSummary
from interfaces.entities.environment import EnvironmentInScene
from interfaces.entities.event import Event
from interfaces.entities.ideation import IdeationResult, PodcastEpisodeIdea, SeriesIdeation
from interfaces.output.image_output import ImageOutput
from interfaces.output.video_output import VideoOutput
from interfaces.output.monetization import MonetizationPlan, PlatformRecommendation, TrendContext
from langchain.chat_models import init_chat_model
from utils.core.timer import Timer
from utils.core.rate_limiter import RateLimiter
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
import importlib
from utils.core.run_id import generate_run_id, write_run_metadata, extract_run_id_from_path, initialize_run_directory
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.series_bible import SeriesBible
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
from configs.constants.content_constants import CONTENT_FORMAT_ANIMATED

class Script2VideoPipeline:

    # events
    character_portrait_events = {}
    shot_desc_events = {}
    frame_events = {}


    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        working_dir: str = ".working_dir/script2video",
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
        self.shorts_mode = shorts_mode or {}
        self.trend_analyzer = trend_analyzer
        self.pipeline_kind = pipeline_kind

        # Set up working directory FIRST (needed for ContinuityMemory)
        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="script2video",
            run_id=run_id,
            use_run_id=use_run_id,
        )
        
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.prop_extractor = PropExtractor(chat_model=self.chat_model)
        self.character_portraits_generator = CharacterPortraitsGenerator(image_generator=self.image_generator)
        self.prop_reference_generator = PropReferenceGenerator(image_generator=self.image_generator)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, shorts_mode=self.shorts_mode, pipeline_kind=self.pipeline_kind)
        self.camera_image_generator = CameraImageGenerator(chat_model=self.chat_model, image_generator=self.image_generator, video_generator=self.video_generator, pipeline_kind=self.pipeline_kind)
        self.video_director = VideoDirector(chat_model=self.chat_model, shorts_mode=self.shorts_mode, pipeline_kind=self.pipeline_kind)
        self.reference_image_selector = ReferenceImageSelector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        # Initialize voice memory for character voice consistency
        from utils.pipeline.voice_memory import VoiceMemory
        self.voice_memory = VoiceMemory(working_dir=self.working_dir)
        self.audio_planner = AudioPlanner(
            chat_model=self.chat_model,
            pipeline_kind=self.pipeline_kind,
            working_dir=self.working_dir,
            voice_memory=self.voice_memory,
        )
        self.global_reference_images = global_reference_images or []
        self.force_regenerate = force_regenerate
        self.logger = logging.getLogger(__name__)
        
        # Character portrait paths for compositing (populated during call)
        # Works for both S3 characters and newly generated characters
        self.character_portraits: Dict[str, str] = {}
        self.use_character_compositing: bool = False



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

        shorts_mode = config.get("shorts_mode", {}) or {}

        # Initialize trend analyzer if configured
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir or run_id, otherwise use config default
        resolved_working_dir = working_dir or config.get("working_dir", ".working_dir/script2video")

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=resolved_working_dir,
            global_reference_images=global_reference_images,
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
            shorts_mode=shorts_mode,
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
        )

    async def __call__(
        self,
        script: str,
        user_requirement: str,
        style: str,
        characters: List[CharacterInScene] = None,
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
        audience: Optional[str] = None,
        trendy: bool = False,
        content_format: Optional[Literal["live_action", "animated"]] = None,
        restitch_only: bool = False,
    ) -> Dict[str, Any]:
        self.logger.info("Starting Script2VideoPipeline execution...")
        # Fetch trends if trendy flag is set
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if trendy and self.trend_analyzer:
            self.logger.info("Fetching real-time trends for trendy content...")
            trend_context = await self.trend_analyzer.fetch_trends(category="video")
            trend_context_block = trend_context.to_context_block()
            # Save trend data
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Enhance user requirement with content_format, audience, and trend context
        effective_user_requirement = user_requirement
        if content_format == CONTENT_FORMAT_ANIMATED:
            effective_user_requirement = f"Content format: animated. Visuals stylized for 2D/3D animation.\n\n{effective_user_requirement}"
        if audience:
            effective_user_requirement = f"Target audience: {audience}\n\n{effective_user_requirement}"
        if trend_context_block:
            effective_user_requirement = f"{effective_user_requirement}\n\n{trend_context_block}"

        resolution = resolve_s3_entities(
            texts=[script, effective_user_requirement],
            working_dir=self.working_dir,
        )
        if resolution.get("context_block"):
            effective_user_requirement = f"{effective_user_requirement}\n\n{resolution['context_block']}"
        if resolution.get("reference_images"):
            existing_paths = {item["path"] for item in self.global_reference_images}
            for item in resolution["reference_images"]:
                if item["path"] not in existing_paths:
                    self.global_reference_images.append(item)

        if characters is None or character_portraits_registry is None:
            resolved_characters = resolution.get("characters") or []
            resolved_registry = resolution.get("portrait_registry") or {}
            if resolved_characters and resolved_registry:
                characters = resolved_characters
                character_portraits_registry = resolved_registry
                
                # Enable character compositing for visual consistency
                self.use_character_compositing = True
                self._extract_character_portrait_paths(character_portraits_registry)

        if characters is None:
            characters = await self.extract_characters(script=script)

        # Extract props and anchors for consistency
        props_and_anchors = await self.prop_extractor.extract_props_and_anchors(script=script)
        props = props_and_anchors.props
        visual_anchors = props_and_anchors.visual_anchors

        # Record in Bible if possible (Search parent directories)
        bible_path = os.path.join(os.path.dirname(self.working_dir), "series_bible.json")
        if os.path.exists(bible_path):
            bible = SeriesBible.load(os.path.dirname(self.working_dir))
            for prop in props:
                bible.register_prop(prop)
            for anchor in visual_anchors:
                # Try to extract slugline from script or use generic
                bible.add_visual_anchor("GENERAL", anchor)
            bible.save(os.path.dirname(self.working_dir))

        # Generate prop visual references if needed
        prop_refs_dir = os.path.join(self.working_dir, "prop_references")
        os.makedirs(prop_refs_dir, exist_ok=True)
        prop_reference_images = {}
        self.logger.info(f"Generating prop references for {len(props)} props...")
        for prop in props:
            ref_path = await self.prop_reference_generator.generate_prop_reference(
                prop, style, prop_refs_dir, force_regenerate=self.force_regenerate
            )
            prop_reference_images[prop.identifier] = ref_path
            # Add to global reference images for the selectors to find
            self.global_reference_images.append({
                "path": ref_path,
                "description": f"Visual reference for prop: {prop.identifier}. {prop.static_features}"
            })
        self.logger.info(f"Prop reference generation completed for {len(prop_reference_images)} props.")

            # characters_path = os.path.join(self.working_dir, "characters.json")
            # if os.path.exists(characters_path):
            #     with open(characters_path, "r", encoding="utf-8") as f:
            #         characters = [CharacterInScene.model_validate(c) for c in json.load(f)]
            #     print(f"🚀 Loaded {len(characters)} characters from existing file.")
            # else:
            #     print(f"🔍 Extracting characters from script...")
            #     characters = await self.extract_characters(script=script)
            #     with open(characters_path, "w", encoding="utf-8") as f:
            #         json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=4)
            #     print(f"☑️ Extracted {len(characters)} characters from script and saved to {characters_path}.")

        if character_portraits_registry is None:
            character_portraits_registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, "r", encoding="utf-8") as f:
                    character_portraits_registry = json.load(f)
                print(f"🚀 Loaded {len(character_portraits_registry)} character portraits from existing file.")
            else:
                print(f"🔍 Generating character portraits...")
                character_portraits_registry = await self.generate_character_portraits(
                    characters=characters,
                    character_portraits_registry=None,
                    style=style,
                )

                with open(character_portraits_registry_path, "w", encoding="utf-8") as f:
                    json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)
                print(f"☑️ Generated {len(character_portraits_registry)} character portraits and saved to {character_portraits_registry_path}.")
        
        # CRITICAL FIX: Enable character compositing for ALL characters (not just S3)
        # This ensures visual consistency for both S3 and newly generated character portraits
        if character_portraits_registry:
            self.use_character_compositing = True
            self._extract_character_portrait_paths(character_portraits_registry)

        # Director: creative brief for storyboard/cinematography
        self.logger.info("Creating director brief for storyboard/cinematography...")
        script_for_director = script if isinstance(script, str) else json.dumps(script, ensure_ascii=False)
        director_brief = await self.video_director.direct(idea_or_script=script_for_director[:4000], user_requirement=effective_user_requirement)
        effective_user_requirement = f"{effective_user_requirement}\n\n{director_brief.to_context_block()}"
        self.logger.info("Director brief created successfully.")

        # Director reasoning: VideoDirector creative brief
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="script2video",
            director_name="VideoDirector",
            rationale=(
                "VideoDirector sets the creative brief for storyboard and cinematography: tone, pacing, "
                "visual style, and shot emphasis from the script and user_requirement. The brief steers "
                "StoryboardArtist.design_storyboard, decompose_visual_descriptions, and CameraImageGenerator. "
                "Content format (live-action/animated), audience, and trends refine the direction."
            ),
            inputs={
                "script_preview": (script_for_director or "")[:200],
                "user_requirement": (effective_user_requirement or "")[:200],
                "style": style,
                "content_format": content_format,
            },
            outputs={"director_brief": "In effective_user_requirement for design_storyboard and downstream."},
        )

        # Phase 1 reasoning: rationale for the input script driving this pipeline
        script_preview = (script[:500] + "…") if isinstance(script, str) and len(script) > 500 else (str(script)[:500] + "…" if script else "")
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="script2video",
            phase_label="Phase 1: Input script",
            content_type="input_script",
            rationale=(
                "The script is provided by the caller (e.g. video or another pipeline). It is the "
                "narrative driver: VideoDirector's brief, StoryboardArtist's shots, and shot decomposition "
                "all derive from it. user_requirement, content_format, audience, and trends refine the "
                "creative direction. Characters are extracted from the script or passed in; character "
                "portraits are generated or loaded from S3. The rationale is to make explicit how the "
                "input script and context shape the storyboard and final video."
            ),
            inputs={
                "script_preview": script_preview,
                "user_requirement": (user_requirement or "")[:200],
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
                "characters_source": "S3 resolution" if (characters and character_portraits_registry) else "extracted from script",
            },
            outputs={
                "characters.json": "Characters (extracted or from S3).",
                "character_portraits_registry.json": "Portraits (generated or from S3).",
                "storyboard.json": "Storyboard (from script); written in design_storyboard.",
                "shots/": "Shot descriptions and generated frames/videos.",
            },
        )

        # design shots
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "storyboard_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(f"Script: {script[:1000]}\nRequirement: {effective_user_requirement}")

        self.logger.info("Designing storyboard from script...")
        storyboard = await self.design_storyboard(
            script=script,
            characters=characters,
            user_requirement=effective_user_requirement,
            props=props,
            visual_anchors=visual_anchors,
        )
        self.logger.info(f"Storyboard designed with {len(storyboard)} shots.")

        # Skip intermediate steps if restitch_only
        if not restitch_only:
            # decompose visual descriptions of shots
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "decomposition_call.txt"), "w", encoding="utf-8") as f:
                f.write(f"Decomposing {len(storyboard)} shots")

            self.logger.info(f"Decomposing visual descriptions for {len(storyboard)} shots...")
            shot_descriptions = await self.decompose_visual_descriptions(
                shot_brief_descriptions=storyboard,
                characters=characters,
                props=props,
            )
            self.logger.info(f"Decomposed {len(shot_descriptions)} shot descriptions.")

            # Plan audio requirements at shot level
            audio_plan_path = os.path.join(self.working_dir, "audio_plan.json")
            audio_plan = None
            if os.path.exists(audio_plan_path) and not self.force_regenerate:
                self.logger.info("Loading existing audio plan...")
                audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
            
            if audio_plan is None:
                self.logger.info("Planning audio requirements for shots...")
                # Convert shot descriptions to a format AudioPlanner can use
                # Since we don't have Scene objects, we'll plan at shot level directly
                try:
                    # Create a simple scene representation from the script
                    from interfaces.content.scene import Scene
                    from interfaces.entities.environment import EnvironmentInScene
                    
                    # Extract scenes from script if possible, or create a single scene
                    # For now, treat all shots as one scene
                    scene_script = script if isinstance(script, str) else str(script)
                    single_scene = Scene(
                        idx=0,
                        is_last=True,
                        environment=EnvironmentInScene(
                            slugline="MIXED LOCATIONS",
                            description="Various locations from the script",
                        ),
                        characters=characters,
                        script=scene_script,
                    )
                    
                    shots_per_scene = {0: shot_descriptions}
                    
                    # Load previous audio plan if exists (for continuity)
                    previous_plan = None
                    parent_audio_plan_path = os.path.join(os.path.dirname(self.working_dir), "audio_plan.json")
                    if os.path.exists(parent_audio_plan_path):
                        previous_plan = self.audio_planner.load_audio_plan(parent_audio_plan_path)
                    
                    audio_plan = await self.audio_planner.plan_audio_for_scenes(
                        scenes=[single_scene],
                        shots_per_scene=shots_per_scene,
                        previous_audio_plan=previous_plan,
                        style=style,
                        audience=audience,
                        content_format=content_format or "live_action",
                        characters=characters,  # Pass characters for voice mapping
                    )
                    
                    # Save audio plan
                    self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                    self.logger.info(f"Audio plan created and saved with {len(audio_plan.scene_plans)} scene plans")
                except Exception as e:
                    self.logger.warning(f"Failed to create audio plan: {e}. Continuing without detailed audio planning.")
                    audio_plan = None
            else:
                self.logger.info("Using existing audio plan")
            
            # Store audio plan for later use in audio generation
            self.audio_plan = audio_plan

            # construct camera tree
            self.logger.info("Constructing camera tree...")
            camera_tree = await self.construct_camera_tree(
                shot_descriptions=shot_descriptions,
            )
            self.logger.info(f"Camera tree constructed with {len(camera_tree)} cameras.")

            # Cinematographer/picturization reasoning...
            # ... (Existing reasoning call) ...

            priority_shot_idxs = [camera.parent_cam_idx for camera in camera_tree if camera.parent_cam_idx is not None]
            
            # The first shot of the first camera is the establishment frame
            # We track it to maintain background locking across the entire scene
            establishment_frame_path = None
            if camera_tree:
                first_camera = camera_tree[0]
                if first_camera.active_shot_idxs:
                    establishment_frame_path = os.path.join(self.working_dir, "shots", f"{first_camera.active_shot_idxs[0]}", "first_frame.png")

            self.logger.info(f"Starting frame generation for {len(camera_tree)} cameras and {len(shot_descriptions)} shots...")
            tasks = [
                self.generate_frames_for_single_camera(
                    camera=camera,
                    shot_descriptions=shot_descriptions,
                    characters=characters,
                    props=props,
                    character_portraits_registry=character_portraits_registry,
                    priority_shot_idxs=priority_shot_idxs,
                    establishment_frame_path=establishment_frame_path if camera.idx != 0 else None,
                )
                for camera in camera_tree
            ]

            video_tasks = [
                self.generate_video_for_single_shot(
                    shot_description=shot_description,
                )
                for shot_description in shot_descriptions
            ]
            tasks.extend(video_tasks)
            self.logger.info(f"Executing {len(tasks)} generation tasks in parallel...")
            await asyncio.gather(*tasks)
            self.logger.info("Frame and video generation completed.")
        else:
            self.logger.info("Restitch only mode: Skipping shot decomposition and generation.")
            # We still need shot_descriptions to know what to concatenate
            shot_descriptions = await self.decompose_visual_descriptions(
                shot_brief_descriptions=storyboard,
                characters=characters,
                props=props,
            )

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path) and not self.force_regenerate and not restitch_only:
            print(f"🚀 Skipped concatenating videos, already exists.")
        else:
            print(f"🎬 Starting concatenating videos...")
            video_clips = []
            for shot_description in shot_descriptions:
                s_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "video.mp4")
                if os.path.exists(s_path):
                    video_clips.append(VideoFileClip(s_path))
                elif restitch_only:
                    self.logger.warning(f"  Restitch mode: Shot video NOT found at {s_path}. Skipping shot.")
            
            if video_clips:
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
                
                # Insert music segments into video timeline if needed
                final_video_clips = []
                current_shot_idx = 0
                
                for shot_description in shot_descriptions:
                    shot_idx = shot_description.idx
                    s_path = os.path.join(self.working_dir, "shots", f"{shot_idx}", "video.mp4")
                    
                    if os.path.exists(s_path):
                        final_video_clips.append(VideoFileClip(s_path))
                    
                    # Check if there's a music segment after this shot
                    # Music segments are keyed by (scene_idx, shot_idx)
                    # For Script2VideoPipeline, scene_idx is typically 0
                    music_key = (0, shot_idx)
                    if music_key in music_segments:
                        music_info = music_segments[music_key]
                        music_path = music_info["audio_path"]
                        
                        if os.path.exists(music_path):
                            # Create a video clip from the music audio
                            # Use a black screen or visual placeholder for the music segment
                            from moviepy import AudioFileClip, ColorClip
                            
                            music_audio = AudioFileClip(music_path)
                            duration = music_audio.duration
                            
                            # Create a simple visual for the music segment
                            # In the future, this could be enhanced with lyrics overlay, visualizer, etc.
                            music_video = ColorClip(
                                size=(1920, 1080),  # Standard HD
                                color=(0, 0, 0),  # Black background
                                duration=duration
                            ).set_audio(music_audio)
                            
                            temp_music_video = os.path.join(self.working_dir, f"music_segment_shot_{shot_idx}.mp4")
                            music_video.write_videofile(temp_music_video, codec="libx264", audio_codec="aac", fps=24)
                            music_video.close()
                            music_audio.close()
                            
                            if os.path.exists(temp_music_video):
                                final_video_clips.append(VideoFileClip(temp_music_video))
                            self.logger.info(
                                f"Inserted music segment after shot {shot_idx}: "
                                f"{music_info['music_style']} ({duration}s)"
                            )
                
                # Concatenate all clips (video + music segments)
                if final_video_clips:
                    final_video = concatenate_videoclips(final_video_clips)
                else:
                    # Fallback to original behavior if no clips
                    final_video = concatenate_videoclips(video_clips)
                
                # Generate and add audio using AudioPlan if available
                audio_path = os.path.join(self.working_dir, "final_audio.mp3")
                if not os.path.exists(audio_path) or self.force_regenerate:
                    self.logger.info("Generating audio track for final video...")
                    
                    # Use AudioPlan if available for voice-over/dialogue
                    if hasattr(self, 'audio_plan') and self.audio_plan:
                        try:
                            from utils.pipeline.voice_generator import generate_audio_track_from_plan
                            
                            self.logger.info("Generating audio track from AudioPlan (includes dialogue/voice-over)...")
                            audio_path = await generate_audio_track_from_plan(
                                audio_plan=self.audio_plan,
                                video_duration=final_video.duration,
                                output_path=audio_path,
                                working_dir=self.working_dir,
                                force_regenerate=self.force_regenerate,
                                voice_memory=self.voice_memory,  # Pass voice memory for character consistency
                            )
                            
                            if audio_path and os.path.exists(audio_path):
                                self.logger.info(f"Generated audio track with voice from AudioPlan: {audio_path}")
                            else:
                                self.logger.warning("AudioPlan generation failed, falling back to background music only")
                                audio_path = None
                        except Exception as e:
                            self.logger.warning(f"Failed to generate audio from AudioPlan: {e}. Falling back to background music.")
                            audio_path = None
                    
                    # Fallback: Generate background music only (if AudioPlan not available or failed)
                    if not audio_path or not os.path.exists(audio_path):
                        # Collect all audio descriptions
                        audio_descriptions = []
                        for shot_description in shot_descriptions:
                            if shot_description.audio_desc and shot_description.audio_desc.strip():
                                audio_descriptions.append(shot_description.audio_desc)
                        
                        # Generate background music/sound effects
                        try:
                            from utils.pipeline.audio_helper import generate_audio_for_video
                            
                            audio_path = await generate_audio_for_video(
                                video_duration=final_video.duration,
                                audio_descriptions=audio_descriptions if audio_descriptions else None,
                                output_path=audio_path,
                                force_regenerate=self.force_regenerate,
                            )
                            
                            if audio_path:
                                self.logger.info(f"Generated background music track: {audio_path}")
                            else:
                                self.logger.warning("Audio generation failed, video will have no audio")
                                audio_path = None
                        except Exception as e:
                            self.logger.warning(f"Failed to generate audio: {e}. Continuing without audio.")
                            audio_path = None
                
                # Add audio to video if available
                if audio_path and os.path.exists(audio_path):
                    try:
                        audio_clip = AudioFileClip(audio_path)
                        # Ensure audio matches video duration
                        if audio_clip.duration > final_video.duration:
                            audio_clip = audio_clip.subclip(0, final_video.duration)
                        elif audio_clip.duration < final_video.duration:
                            # Loop audio if shorter than video
                            loops_needed = int(final_video.duration / audio_clip.duration) + 1
                            audio_clips = [audio_clip] * loops_needed
                            audio_clip = concatenate_audioclips(audio_clips).subclip(0, final_video.duration)
                        
                        final_video = final_video.set_audio(audio_clip)
                        final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac", preset="medium")
                        audio_clip.close()
                        self.logger.info(f"Added audio to final video: {final_video_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to add audio to video: {e}. Saving video without audio.")
                        final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
                else:
                    # Save video without audio
                    final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
                
                for c in video_clips: c.close()
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
            total_duration_seconds = len(shot_descriptions) * 5  # Default estimate

        # Generate monetization plan
        is_shorts = self.shorts_mode.get("enabled", False)
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=f"Video from script",
            description=script[:500] if script else "",
            audience=audience or "General",
            duration_seconds=total_duration_seconds,
            genre="Entertainment",
            is_shorts=is_shorts,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # Save output metadata
        output_metadata = {
            "run_id": self.run_id,
            "script": script[:500] if script else "",
            "user_requirement": user_requirement,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "content_format": content_format,
            "video_path": final_video_path,
            "duration_seconds": total_duration_seconds,
            "is_shorts": is_shorts,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=script_preview,
                storyboard=storyboard,
                video_metadata=output_metadata
            )
            output_metadata["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(os.path.join(self.working_dir, "output.json"), "w", encoding="utf-8") as f:
            json.dump(output_metadata, f, ensure_ascii=False, indent=2)

        return output_metadata

    def _resolve_visible_prop_indices(
        self,
        shot_description: ShotDescription,
        candidate_indices: List[int],
        frame_desc: Optional[str],
        props: List[PropInScene],
    ) -> List[int]:
        """Resolve which props are visible in a shot using regex word boundaries."""
        descriptions = [frame_desc, shot_description.visual_desc]
        mentioned_indices = []
        
        for idx, prop in enumerate(props):
            identifier = prop.identifier
            if not identifier:
                continue
            
            pattern = rf"(?i)\b({re.escape(identifier)})\b"
            
            for desc in descriptions:
                if not desc:
                    continue
                if re.search(pattern, desc):
                    mentioned_indices.append(idx)
                    break

        mentioned_indices = list(dict.fromkeys(mentioned_indices))
        if candidate_indices:
            candidate_indices = [idx for idx in candidate_indices if 0 <= idx < len(props)]
            if not mentioned_indices:
                return candidate_indices
            if set(candidate_indices).issubset(set(mentioned_indices)):
                return candidate_indices
            return mentioned_indices

        return mentioned_indices

    def _resolve_visible_character_indices(
        self,
        shot_description: ShotDescription,
        candidate_indices: List[int],
        frame_desc: Optional[str],
        characters: List[CharacterInScene],
    ) -> List[int]:
        """
        Resolve which characters are visible in a shot using regex word boundaries.
        
        Uses strict word boundary matching to avoid false positives (e.g., "Jo" matching "John").
        Supports both plain names and bracketed names like <CharacterName>.
        """
        descriptions = [frame_desc, shot_description.visual_desc]
        mentioned_indices = []
        
        for idx, character in enumerate(characters):
            identifier = character.identifier_in_scene
            if not identifier:
                continue
            
            # Use regex with word boundaries for precise matching
            # Matches: "CharName", "<CharName>", "CharName's", etc.
            pattern = rf"(?i)\b({re.escape(identifier)}|<{re.escape(identifier)}>)\b"
            
            for desc in descriptions:
                if not desc:
                    continue
                if re.search(pattern, desc):
                    mentioned_indices.append(idx)
                    break

        mentioned_indices = list(dict.fromkeys(mentioned_indices))
        if candidate_indices:
            candidate_indices = [idx for idx in candidate_indices if 0 <= idx < len(characters)]
            if not mentioned_indices:
                return candidate_indices
            if set(candidate_indices).issubset(set(mentioned_indices)):
                return candidate_indices
            return mentioned_indices

        return mentioned_indices

    def _extract_character_portrait_paths(
        self,
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]],
    ) -> None:
        """
        Extract character portrait paths from the registry.
        
        These portraits are stored separately for compositing onto generated frames
        to ensure visual consistency across the video.
        """
        self.character_portraits = {}
        
        for identifier, views in character_portraits_registry.items():
            # Prefer front view, fall back to other views
            for view_key in ["front", "side", "back"]:
                view_data = views.get(view_key, {})
                portrait_path = view_data.get("path", "")
                
                if portrait_path and os.path.exists(portrait_path):
                    self.character_portraits[identifier] = portrait_path
                    self.logger.info(f"Registered character portrait for compositing: {identifier} -> {portrait_path}")
                    break
        
        if self.character_portraits:
            self.logger.info(f"Character compositing enabled for {len(self.character_portraits)} characters")

    def _composite_characters_on_frame(
        self,
        frame_path: str,
        visible_characters: List[CharacterInScene],
        frame_desc: str,
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]],
    ) -> None:
        """
        Post-process a generated frame by compositing character portraits.
        
        AI image generators cannot reliably reproduce specific character designs
        from reference images alone. This method overlays the actual character
        portraits onto the generated scene to ensure visual consistency.
        
        Args:
            frame_path: Path to the generated frame image
            visible_characters: Characters that should appear in this frame
            frame_desc: Frame description (for positioning hints)
            character_portraits_registry: Registry with character portrait paths
        """
        if not self.use_character_compositing:
            return
        
        if not visible_characters:
            return
        
        if not os.path.exists(frame_path):
            return
        
        # Collect character portraits for visible characters using view/expression selectors
        portraits_to_composite = []
        
        # Get view and expression from frame description
        view = get_character_view_for_shot(frame_desc)
        expression = get_character_expression_for_shot(frame_desc)
        
        for char in visible_characters:
            identifier = char.identifier_in_scene
            portrait_path = None
            
            # Check if this character has a portrait in our list (legacy format)
            if identifier in self.character_portraits:
                portrait_path = self.character_portraits[identifier]
                if not os.path.exists(portrait_path):
                    portrait_path = None
            
            # Check the registry with view/expression selection
            if not portrait_path and identifier in character_portraits_registry:
                registry_entry = character_portraits_registry[identifier]
                
                # Try view-specific entry
                view_data = registry_entry.get(view.value, {})
                if isinstance(view_data, dict):
                    # Try expression-specific path
                    expr_data = view_data.get(expression.value, {})
                    if isinstance(expr_data, dict):
                        portrait_path = expr_data.get("path")
                    else:
                        portrait_path = expr_data if isinstance(expr_data, str) else None
                    if not portrait_path:
                        portrait_path = view_data.get("path")
                elif isinstance(view_data, str):
                    portrait_path = view_data
                
                # Fallback to front view
                if not portrait_path:
                    front_entry = registry_entry.get("front", {})
                    if isinstance(front_entry, dict):
                        # Try expression-specific in front view
                        expr_data = front_entry.get(expression.value, {})
                        if isinstance(expr_data, dict):
                            portrait_path = expr_data.get("path")
                        else:
                            portrait_path = expr_data if isinstance(expr_data, str) else None
                        if not portrait_path:
                            portrait_path = front_entry.get("path")
                    elif isinstance(front_entry, str):
                        portrait_path = front_entry
            
            if portrait_path and os.path.exists(portrait_path):
                portraits_to_composite.append(portrait_path)
                self.logger.info(f"Using character portrait ({view.value}/{expression.value}) for compositing: {identifier}")
        
        if not portraits_to_composite:
            return
        
        try:
            if len(portraits_to_composite) == 1:
                # Single character - infer position from description
                position = get_character_position_from_description(frame_desc)
                scale = get_character_scale_from_shot_type(frame_desc)
                
                composite_character_on_image(
                    background_path=frame_path,
                    character_path=portraits_to_composite[0],
                    output_path=frame_path,
                    position=position,
                    scale_factor=scale,
                    blend_mode="soft",
                )
                self.logger.info(f"Composited 1 character onto: {frame_path}")
            else:
                # Multiple characters
                composite_multiple_characters(
                    background_path=frame_path,
                    character_paths=portraits_to_composite,
                    output_path=frame_path,
                )
                self.logger.info(f"Composited {len(portraits_to_composite)} characters onto: {frame_path}")
                
        except Exception as e:
            self.logger.warning(f"Failed to composite characters onto {frame_path}: {e}")


    async def generate_frames_for_single_camera(
        self,
        camera: Camera,
        shot_descriptions: List[ShotDescription],
        characters: List[CharacterInScene],
        props: List[PropInScene],
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]],
        priority_shot_idxs: List[int],
        establishment_frame_path: Optional[str] = None,
    ):
        # 1. generate the first_frame of the first shot of the camera
        first_shot_idx = camera.active_shot_idxs[0]
        first_shot_ff_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", "first_frame.png")

        if os.path.exists(first_shot_ff_path) and not self.force_regenerate:
            print(f"🚀 Skipped generating first_frame for shot {first_shot_idx}, already exists.")
            self.frame_events[first_shot_idx]["first_frame"].set()

        else:
            print(f"🖼️ Starting first_frame generation for shot {first_shot_idx}...")
            available_image_path_and_text_pairs = []

            resolved_ff_vis_char_idxs = self._resolve_visible_character_indices(
                shot_description=shot_descriptions[first_shot_idx],
                candidate_indices=shot_descriptions[first_shot_idx].ff_vis_char_idxs,
                frame_desc=shot_descriptions[first_shot_idx].ff_desc,
                characters=characters,
            )
            resolved_ff_vis_prop_idxs = self._resolve_visible_prop_indices(
                shot_description=shot_descriptions[first_shot_idx],
                candidate_indices=shot_descriptions[first_shot_idx].ff_vis_prop_idxs,
                frame_desc=shot_descriptions[first_shot_idx].ff_desc,
                props=props,
            )
            for character_idx in resolved_ff_vis_char_idxs:
                identifier_in_scene = characters[character_idx].identifier_in_scene
                registry_item = character_portraits_registry[identifier_in_scene]
                for view, item in registry_item.items():
                    available_image_path_and_text_pairs.append((item["path"], item["description"]))

            for prop_idx in resolved_ff_vis_prop_idxs:
                prop = props[prop_idx]
                available_image_path_and_text_pairs.append(("", f"PROP REFERENCE: {prop.identifier} - {prop.description}. {prop.static_features}"))

            for item in self.global_reference_images:
                available_image_path_and_text_pairs.append((item["path"], item["description"]))
            
            # generate the first_frame based on the shot_description.ff_desc
            if camera.parent_shot_idx is not None:
                # generate the first_frame based on the transition video
                parent_shot_idx = camera.parent_shot_idx
                await self.frame_events[parent_shot_idx]["first_frame"].wait()
                parent_shot_ff_path = os.path.join(self.working_dir, "shots", f"{parent_shot_idx}", "first_frame.png")
                transition_video_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", f"transition_video_from_shot_{parent_shot_idx}.mp4")

                if os.path.exists(transition_video_path) and not self.force_regenerate:
                    print(f"🚀 Skipped generating transition video for shot {first_shot_idx} from shot {parent_shot_idx}, already exists.")
                else:
                    print(f"🖼️ Starting transition video generation for shot {first_shot_idx} from shot {parent_shot_idx}...")
                    transition_video_output = await self.camera_image_generator.generate_transition_video(
                        first_shot_visual_desc=shot_descriptions[parent_shot_idx].visual_desc,
                        second_shot_visual_desc=shot_descriptions[first_shot_idx].visual_desc,
                        first_shot_ff_path=parent_shot_ff_path,
                    )
                    transition_video_output.save(transition_video_path)
                    print(f"☑️ Generated transition video for shot {first_shot_idx} from shot {parent_shot_idx}, saved to {transition_video_path}.")

                new_camera_image_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", f"new_camera_{camera.idx}.png")
                if os.path.exists(new_camera_image_path) and not self.force_regenerate:
                    print(f"🚀 Skipped generating new camera image for shot {first_shot_idx}, already exists.")
                else:
                    print(f"🖼️ Starting new camera image generation for shot {first_shot_idx}...")
                    new_camera_image = self.camera_image_generator.get_new_camera_image(transition_video_path)
                    new_camera_image.save(new_camera_image_path)
                    print(f"☑️ Generated new camera image for shot {first_shot_idx} (not completed), saved to {new_camera_image_path}.")

                    available_image_path_and_text_pairs.append(
                        (
                            new_camera_image_path,
                            f"The composition and background are correct but some elements may be wrong. The wrong elements should be replaced.\nWrong elements: {camera.missing_info}.\nYou must select this image as the main reference and replace the characters in the image with the provided character portraits. Don't change the background."
                        )
                    )


            # 如果子镜头缺少信息，则需要选择参考图像生成
            if camera.parent_shot_idx is None or camera.missing_info is not None:
                ff_selector_output_path = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", "first_frame_selector_output.json")
                if os.path.exists(ff_selector_output_path) and not self.force_regenerate:
                    with open(ff_selector_output_path, 'r', encoding='utf-8') as f:
                        ff_selector_output = json.load(f)
                    print(f"🚀 Loaded existing reference image selection and prompt for first_frame of shot {first_shot_idx} from {ff_selector_output_path}.")
                else:
                    print(f"🔍 Selecting reference images and generating prompt for first_frame of shot {first_shot_idx}...")
                    ff_selector_output = await self.reference_image_selector.select_reference_images_and_generate_prompt(
                        available_image_path_and_text_pairs=available_image_path_and_text_pairs,
                        frame_description=shot_descriptions[first_shot_idx].ff_desc,
                        establishment_frame_path=establishment_frame_path
                    )
                    with open(ff_selector_output_path, 'w', encoding='utf-8') as f:
                        json.dump(ff_selector_output, f, ensure_ascii=False, indent=4)

                    print(f"☑️ Selected reference images and generated prompt for first_frame of shot {first_shot_idx}, saved to {ff_selector_output_path}.")

                reference_image_path_and_text_pairs, prompt = ff_selector_output["reference_image_path_and_text_pairs"], ff_selector_output["text_prompt"]
                prefix_prompt = ""
                for i, (image_path, text) in enumerate(reference_image_path_and_text_pairs):
                    prefix_prompt += f"Image {i}: {text}\n"
                prompt = f"{prefix_prompt}\n{prompt}"
                # Filter out empty or non-existent paths
                reference_image_paths = [
                    item[0] for item in reference_image_path_and_text_pairs 
                    if item[0] and os.path.exists(item[0])
                ]
                
                # Save debug prompt
                debug_dir = os.path.join(self.working_dir, "shots", f"{first_shot_idx}", "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "first_frame_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(prompt)

                # TRACK 1: RAW GENERATION (Gelled Characters)
                first_shot_ff_raw_path = first_shot_ff_path.replace(".png", "_raw.png")
                raw_image: ImageOutput = await self.image_generator.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    size="1600x900",
                )
                raw_image.save(first_shot_ff_raw_path)
                
                # TRACK 2: STORYBOARD GENERATION (Composited S3 Characters)
                # Generate a clean background first
                bg_prompt = prompt
                for char_idx in resolved_ff_vis_char_idxs:
                    if 0 <= char_idx < len(characters):
                        name = characters[char_idx].identifier_in_scene
                        bg_prompt = re.sub(rf"(?i)\b{re.escape(name)}\b", "the center area", bg_prompt)
                
                bg_prompt += " EMPTY CINEMATIC ENVIRONMENT ONLY. No characters."
                
                # Use first valid reference image for background, or None if none exist
                bg_ref_paths = [reference_image_paths[0]] if reference_image_paths and len(reference_image_paths) > 0 and os.path.exists(reference_image_paths[0]) else None
                
                bg_image: ImageOutput = await self.image_generator.generate_single_image(
                    prompt=bg_prompt,
                    reference_image_paths=bg_ref_paths,
                    size="1600x900",
                )
                bg_image.save(first_shot_ff_path)
                
                # Composite characters into STORYBOARD frame
                visible_chars_for_compositing = [
                    characters[idx] for idx in resolved_ff_vis_char_idxs 
                    if 0 <= idx < len(characters)
                ]
                self._composite_characters_on_frame(
                    frame_path=first_shot_ff_path,
                    visible_characters=visible_chars_for_compositing,
                    frame_desc=shot_descriptions[first_shot_idx].ff_desc,
                    character_portraits_registry=character_portraits_registry,
                )
                
                self.frame_events[first_shot_idx]["first_frame"].set()
                print(f"☑️ Generated first_frame for shot {first_shot_idx}, saved to {first_shot_ff_path}.")
            else:
                # Save raw frame (before any potential compositing) for video generation
                first_shot_ff_raw_path = first_shot_ff_path.replace(".png", "_raw.png")
                shutil.copy(new_camera_image_path, first_shot_ff_raw_path)
                shutil.copy(new_camera_image_path, first_shot_ff_path)
                self.frame_events[first_shot_idx]["first_frame"].set()
                print(f"☑️ Generated first_frame for shot {first_shot_idx}, saved to {first_shot_ff_path}.")


        # 2. generate the following frames of the camera
        priority_tasks = []
        normal_tasks = []

        if shot_descriptions[first_shot_idx].variation_type in ["medium", "large"]:
            resolved_lf_vis_char_idxs = self._resolve_visible_character_indices(
                shot_description=shot_descriptions[first_shot_idx],
                candidate_indices=shot_descriptions[first_shot_idx].lf_vis_char_idxs,
                frame_desc=shot_descriptions[first_shot_idx].lf_desc,
                characters=characters,
            )
            resolved_lf_vis_prop_idxs = self._resolve_visible_prop_indices(
                shot_description=shot_descriptions[first_shot_idx],
                candidate_indices=shot_descriptions[first_shot_idx].lf_vis_prop_idxs,
                frame_desc=shot_descriptions[first_shot_idx].lf_desc,
                props=props,
            )
            task = self.generate_frame_for_single_shot(
                shot_idx=first_shot_idx, 
                frame_type="last_frame", 
                first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                frame_desc=shot_descriptions[first_shot_idx].lf_desc,
                visible_characters=[characters[idx] for idx in resolved_lf_vis_char_idxs],
                visible_props=[props[idx] for idx in resolved_lf_vis_prop_idxs],
                character_portraits_registry=character_portraits_registry,
            )
            normal_tasks.append(task)

        for shot_idx in camera.active_shot_idxs[1:]:
            resolved_ff_vis_char_idxs = self._resolve_visible_character_indices(
                shot_description=shot_descriptions[shot_idx],
                candidate_indices=shot_descriptions[shot_idx].ff_vis_char_idxs,
                frame_desc=shot_descriptions[shot_idx].ff_desc,
                characters=characters,
            )
            resolved_ff_vis_prop_idxs = self._resolve_visible_prop_indices(
                shot_description=shot_descriptions[shot_idx],
                candidate_indices=shot_descriptions[shot_idx].ff_vis_prop_idxs,
                frame_desc=shot_descriptions[shot_idx].ff_desc,
                props=props,
            )
            first_frame_task = self.generate_frame_for_single_shot(
                    shot_idx=shot_idx, 
                    frame_type="first_frame", 
                    first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                    frame_desc=shot_descriptions[shot_idx].ff_desc,
                    visible_characters=[characters[idx] for idx in resolved_ff_vis_char_idxs],
                    visible_props=[props[idx] for idx in resolved_ff_vis_prop_idxs],
                    character_portraits_registry=character_portraits_registry,
                    establishment_frame_path=establishment_frame_path
                )
            if shot_idx in priority_shot_idxs:
                priority_tasks.append(first_frame_task)
            else:
                normal_tasks.append(first_frame_task)


            if shot_descriptions[shot_idx].variation_type in ["medium", "large"]:
                resolved_lf_vis_char_idxs = self._resolve_visible_character_indices(
                    shot_description=shot_descriptions[shot_idx],
                    candidate_indices=shot_descriptions[shot_idx].lf_vis_char_idxs,
                    frame_desc=shot_descriptions[shot_idx].lf_desc,
                    characters=characters,
                )
                resolved_lf_vis_prop_idxs = self._resolve_visible_prop_indices(
                    shot_description=shot_descriptions[shot_idx],
                    candidate_indices=shot_descriptions[shot_idx].lf_vis_prop_idxs,
                    frame_desc=shot_descriptions[shot_idx].lf_desc,
                    props=props,
                )
                last_frame_task = self.generate_frame_for_single_shot(
                    shot_idx=shot_idx, 
                    frame_type="last_frame", 
                    first_shot_ff_path_and_text_pair=(first_shot_ff_path, shot_descriptions[first_shot_idx].ff_desc),
                    frame_desc=shot_descriptions[shot_idx].lf_desc,
                    visible_characters=[characters[idx] for idx in resolved_lf_vis_char_idxs],
                    visible_props=[props[idx] for idx in resolved_lf_vis_prop_idxs],
                    character_portraits_registry=character_portraits_registry,
                    establishment_frame_path=establishment_frame_path
                )
                normal_tasks.append(last_frame_task)


        await asyncio.gather(*priority_tasks)
        await asyncio.gather(*normal_tasks)



    async def generate_video_for_single_shot(
        self,
        shot_description: ShotDescription,
    ):
        video_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "video.mp4")
        if os.path.exists(video_path) and not self.force_regenerate:
            print(f"🚀 Skipped generating video for shot {shot_description.idx}, already exists.")
        else:
            await self.frame_events[shot_description.idx]["first_frame"].wait()
            if shot_description.variation_type in ["medium", "large"]:
                await self.frame_events[shot_description.idx]["last_frame"].wait()

            frame_paths = []
            first_frame_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "first_frame.png")
            first_frame_raw_path = first_frame_path.replace(".png", "_raw.png")
            # Use raw frame for video if available, otherwise fallback to composited
            video_ref_ff = first_frame_raw_path if os.path.exists(first_frame_raw_path) else first_frame_path
            frame_paths.append(video_ref_ff)
            
            if shot_description.variation_type in ["medium", "large"]:
                last_frame_path = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "last_frame.png")
                last_frame_raw_path = last_frame_path.replace(".png", "_raw.png")
                # Use raw frame for video if available
                video_ref_lf = last_frame_raw_path if os.path.exists(last_frame_raw_path) else last_frame_path
                frame_paths.append(video_ref_lf)

            print(f"🎬 Starting video generation for shot {shot_description.idx}...")
            duration = None
            if shot_description.duration_seconds is not None:
                duration = int(shot_description.duration_seconds)
                if self.shorts_mode.get("enabled"):
                    min_shot_seconds = self.shorts_mode.get("min_shot_seconds", 4)
                    max_shot_seconds = self.shorts_mode.get("max_shot_seconds", 8)
                    duration = max(min_shot_seconds, min(max_shot_seconds, duration))
            
            video_prompt = shot_description.motion_desc + "\n" + shot_description.audio_desc
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "shots", f"{shot_description.idx}", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "video_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(video_prompt)

            video_output = await self.video_generator.generate_single_video(
                prompt=video_prompt,
                reference_image_paths=frame_paths,
                duration=duration,
            )
            video_output.save(video_path)
            print(f"☑️ Generated video for shot {shot_description.idx}, saved to {video_path}.")

    async def generate_frame_for_single_shot(
        self,
        shot_idx: int,
        frame_type: Literal["first_frame", "last_frame"],
        first_shot_ff_path_and_text_pair: Tuple[str, str],
        frame_desc: str,
        visible_characters: List[CharacterInScene],
        visible_props: List[PropInScene] = None,
        character_portraits_registry: Dict[str, Dict[str, Dict[str, str]]] = None,
        establishment_frame_path: Optional[str] = None,
    ) -> ImageOutput:

        frame_image_path = os.path.join(self.working_dir, "shots", f"{shot_idx}", f"{frame_type}.png")

        if os.path.exists(frame_image_path) and not self.force_regenerate:
            print(f"🚀 Skipped generating {frame_type} for shot {shot_idx}, already exists.")

        else:
            print(f"🖼️ Starting {frame_type} generation for shot {shot_idx}...")
            available_image_path_and_text_pairs = []
            for visible_character in visible_characters:
                identifier_in_scene = visible_character.identifier_in_scene
                registry_item = character_portraits_registry[identifier_in_scene]
                for view, item in registry_item.items():
                    available_image_path_and_text_pairs.append((item["path"], item["description"]))

            for prop in (visible_props or []):
                available_image_path_and_text_pairs.append(("", f"PROP REFERENCE: {prop.identifier} - {prop.description}. {prop.static_features}"))

            available_image_path_and_text_pairs.append(first_shot_ff_path_and_text_pair)

            for item in self.global_reference_images:
                available_image_path_and_text_pairs.append((item["path"], item["description"]))

            selector_output_path = os.path.join(self.working_dir, "shots", f"{shot_idx}", f"{frame_type}_selector_output.json")
            if os.path.exists(selector_output_path) and not self.force_regenerate:
                with open(selector_output_path, 'r', encoding='utf-8') as f:
                    selector_output = json.load(f)
                print(f"🚀 Loaded existing reference image selection and prompt for {frame_type} frame of shot {shot_idx} from {selector_output_path}.")
            else:
                print(f"🔍 Selecting reference images and generating prompt for {frame_type} frame of shot {shot_idx}...")
                selector_output = await self.reference_image_selector.select_reference_images_and_generate_prompt(
                    available_image_path_and_text_pairs=available_image_path_and_text_pairs,
                    frame_description=frame_desc,
                    establishment_frame_path=establishment_frame_path
                )
                with open(selector_output_path, 'w', encoding='utf-8') as f:
                    json.dump(selector_output, f, ensure_ascii=False, indent=4)
                print(f"☑️ Selected reference images and generated prompt for {frame_type} frame of shot {shot_idx}, saved to {selector_output_path}.")

            reference_image_path_and_text_pairs, prompt = selector_output["reference_image_path_and_text_pairs"], selector_output["text_prompt"]
            
            # LIMIT to top 2 character references to avoid AI generator confusion/inserts
            # We filter the pairs to only include at most 2 character-related images
            char_refs = []
            other_refs = []
            for path, text in reference_image_path_and_text_pairs:
                if "character" in text.lower() or any(c.identifier_in_scene.lower() in text.lower() for c in visible_characters):
                    char_refs.append((path, text))
                else:
                    other_refs.append((path, text))
            
            # Reconstruct filtered list: top 2 chars + other refs (up to 4 total)
            filtered_pairs = char_refs[:2] + other_refs[:2]
            
            prefix_prompt = ""
            for i, (image_path, text) in enumerate(filtered_pairs):
                prefix_prompt += f"Image {i}: {text}\n"
            
            # Stronger instruction to incorporate characters naturally
            prompt = f"{prefix_prompt}\n{prompt}. Incorporate characters naturally into the scene. No collages, no picture-in-picture, no separate reference image inserts."
            # Filter out empty or non-existent paths
            reference_image_paths = [
                item[0] for item in filtered_pairs 
                if item[0] and os.path.exists(item[0])
            ]

            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "shots", f"{shot_idx}", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"{frame_type}_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

            # TRACK 1: BACKGROUND GENERATION (Clean Environment)
            bg_prompt = prompt
            for char in visible_characters:
                bg_prompt = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_prompt)
            bg_prompt += " EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures."
            
            # Use first valid reference image for background, or None if none exist
            bg_ref_paths = [reference_image_paths[0]] if reference_image_paths and len(reference_image_paths) > 0 and os.path.exists(reference_image_paths[0]) else None
            
            bg_image: ImageOutput = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=bg_ref_paths,
                size="1600x900",
            )
            bg_image.save(frame_image_path)
            
            # TRACK 2: COMPOSITE CHARACTERS (S3 Portraits)
            self._composite_characters_on_frame(
                frame_path=frame_image_path, 
                visible_characters=visible_characters,
                frame_desc=frame_desc,
                character_portraits_registry=character_portraits_registry,
            )
            
            # TRACK 3: RAW GENERATION (Gelled Characters)
            raw_frame_path = frame_image_path.replace(".png", "_raw.png")
            
            # Build character context with static_features
            char_desc_parts = []
            for char in visible_characters:
                if char.static_features:
                    char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
            char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
            
            # Add view and expression guidance
            view = get_character_view_for_shot(frame_desc)
            expression = get_character_expression_for_shot(frame_desc)
            view_instruction = f" Camera angle: {view.value} view."
            expression_instruction = f" Character expressions: {expression.value}."
            
            raw_prompt = f"{prompt}.{char_context}{view_instruction}{expression_instruction} High quality animation frame, expressive characters gelled into scene. Blend characters naturally into environment. No text, no collages, no picture-in-picture."
            
            # Build raw references: composite frame + character portraits with view/expression
            raw_refs = [frame_image_path]  # Start with composite frame
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
                        front_entry = character_portraits_registry[char_id].get("front", {})
                        if isinstance(front_entry, dict):
                            path = front_entry.get("path")
                        else:
                            path = str(front_entry) if front_entry else None
                    
                    if path and os.path.exists(path) and path not in raw_refs:
                        raw_refs.append(path)
            
            raw_image: ImageOutput = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                size="1600x900",
                strength=0.55,  # Blend with composite
            )
            raw_image.save(raw_frame_path)
            
            print(f"☑️ Generated {frame_type} frame for shot {shot_idx}, saved to {frame_image_path}.")


        self.frame_events[shot_idx][frame_type].set()
        return frame_image_path


    async def construct_camera_tree(
        self,
        shot_descriptions: List[ShotDescription],
    ):
        camera_tree_path = os.path.join(self.working_dir, "camera_tree.json")

        if os.path.exists(camera_tree_path):
            with open(camera_tree_path, "r", encoding="utf-8") as f:
                camera_tree = json.load(f)
            camera_tree = [Camera.model_validate(camera) for camera in camera_tree]
            print(f"🚀 Loaded {len(camera_tree)} cameras from existing file.")
            return camera_tree

        cameras: List[Camera] = []
        for shot_description in shot_descriptions:
            if shot_description.cam_idx not in [camera.idx for camera in cameras]:
                cameras.append(Camera(idx=shot_description.cam_idx, active_shot_idxs=[shot_description.idx]))
            else:
                cameras[shot_description.cam_idx].active_shot_idxs.append(shot_description.idx)

        camera_tree = await self.camera_image_generator.construct_camera_tree(cameras=cameras, shot_descs=shot_descriptions)
        with open(camera_tree_path, "w", encoding="utf-8") as f:
            json.dump([camera.model_dump() for camera in camera_tree], f, ensure_ascii=False, indent=4)
        print(f"✅ Constructed camera tree and saved to {camera_tree_path}.")
        return camera_tree




    async def extract_characters(
        self,
        script: str,
    ):
        save_path = os.path.join(self.working_dir, "characters.json")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
            characters = [CharacterInScene.model_validate(character) for character in characters]
            print(f"🚀 Loaded {len(characters)} characters from existing file.")
        else:
            characters = await self.character_extractor.extract_characters(script)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump([character.model_dump() for character in characters], f, ensure_ascii=False, indent=4)
            print(f"✅ Extracted {len(characters)} characters from script and saved to {save_path}.")

        for character in characters:
            self.character_portrait_events[character.idx] = asyncio.Event()

        return characters


    async def generate_character_portraits(
        self,
        characters: List[CharacterInScene],
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]],
        style: str,
    ):
        character_portraits_registry_path = os.path.join(self.working_dir, "character_portraits_registry.json")
        if character_portraits_registry is None:
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, 'r', encoding='utf-8') as f:
                    character_portraits_registry = json.load(f)
            else:
                character_portraits_registry = {}


        tasks = [
            self.generate_portraits_for_single_character(character, style)
            for character in characters
            if character.identifier_in_scene not in character_portraits_registry
        ]
        if tasks:
            for future in asyncio.as_completed(tasks):
                character_portraits_registry.update(await future)
                with open(character_portraits_registry_path, 'w', encoding='utf-8') as f:
                    json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)

            print(f"✅ Completed character portrait generation for {len(characters)} characters.")
        else:
            print("🚀 All characters already have portraits, skipping portrait generation.")
        return character_portraits_registry


    async def generate_portraits_for_single_character(
        self,
        character: CharacterInScene,
        style: str,
    ):
        character_dir = os.path.join(self.working_dir, "character_portraits", f"{character.idx}_{character.identifier_in_scene}")
        os.makedirs(character_dir, exist_ok=True)

        front_portrait_path = os.path.join(character_dir, "front.png")
        if os.path.exists(front_portrait_path):
            pass
        else:
            front_portrait_output = await self.character_portraits_generator.generate_front_portrait(character, style, output_dir=character_dir)
            front_portrait_output.save(front_portrait_path)


        side_portrait_path = os.path.join(character_dir, "side.png")
        if os.path.exists(side_portrait_path):
            pass
        else:
            side_portrait_output = await self.character_portraits_generator.generate_side_portrait(character, front_portrait_path, output_dir=character_dir)
            side_portrait_output.save(side_portrait_path)

        back_portrait_path = os.path.join(character_dir, "back.png")
        if os.path.exists(back_portrait_path):
            pass
        else:
            back_portrait_output = await self.character_portraits_generator.generate_back_portrait(character, front_portrait_path, output_dir=character_dir)
            back_portrait_output.save(back_portrait_path)

        self.character_portrait_events[character.idx].set()

        print(f"☑️ Completed character portrait generation for {character.identifier_in_scene}.")

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



    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str,
        props: Optional[List[PropInScene]] = None,
        visual_anchors: Optional[List[str]] = None,
    ):
        storyboard_path = os.path.join(self.working_dir, "storyboard.json")
        if os.path.exists(storyboard_path):
            with open(storyboard_path, 'r', encoding='utf-8') as f:
                storyboard = json.load(f)
            storyboard = [ShotBriefDescription.model_validate(shot) for shot in storyboard]
            print(f"🚀 Loaded {len(storyboard)} shot brief descriptions from existing file.")
        else:
            print(f"🔍 Designing storyboard...")
            storyboard = await self.storyboard_artist.design_storyboard(
                script=script,
                characters=characters,
                props=props,
                visual_anchors=visual_anchors,
                user_requirement=user_requirement,
                retry_timeout=150,
            )
            with open(storyboard_path, 'w', encoding='utf-8') as f:
                json.dump([shot.model_dump() for shot in storyboard], f, ensure_ascii=False, indent=4)
            print(f"✅ Designed storyboard and saved to {storyboard_path}.")

        if self.shorts_mode.get("enabled"):
            max_shots = self.shorts_mode.get("max_shots")
            if isinstance(max_shots, int) and max_shots > 0:
                storyboard = storyboard[:max_shots]
            for idx, shot in enumerate(storyboard):
                shot.is_last = idx == len(storyboard) - 1
            target_seconds = self.shorts_mode.get("target_duration_seconds")
            min_shot_seconds = self.shorts_mode.get("min_shot_seconds", 4)
            max_shot_seconds = self.shorts_mode.get("max_shot_seconds", 8)
            if target_seconds and storyboard:
                default_shot_seconds = int(round(target_seconds / len(storyboard)))
                default_shot_seconds = max(min_shot_seconds, min(max_shot_seconds, default_shot_seconds))
                for shot in storyboard:
                    if shot.duration_seconds is None:
                        shot.duration_seconds = default_shot_seconds
        for shot_brief_description in storyboard:
            self.shot_desc_events[shot_brief_description.idx] = asyncio.Event()

        return storyboard



    async def decompose_visual_descriptions(
        self,
        shot_brief_descriptions: List[ShotBriefDescription],
        characters: List[CharacterInScene],
        props: List[PropInScene] = None,
    ):
        tasks = [
            self.decompose_visual_description_for_single_shot_brief_description(shot_brief_description, characters, props)
            for shot_brief_description in shot_brief_descriptions
        ]

        shot_descriptions = await asyncio.gather(*tasks)
        return shot_descriptions


    async def decompose_visual_description_for_single_shot_brief_description(
        self,
        shot_brief_description: ShotBriefDescription,
        characters: List[CharacterInScene],
        props: List[PropInScene] = None,
    ):
        shot_description_path = os.path.join(self.working_dir, "shots", f"{shot_brief_description.idx}", "shot_description.json")
        os.makedirs(os.path.dirname(shot_description_path), exist_ok=True)

        if os.path.exists(shot_description_path):
            with open(shot_description_path, 'r', encoding='utf-8') as f:
                shot_description = ShotDescription.model_validate(json.load(f))
            if (
                shot_description.duration_seconds is None
                and shot_brief_description.duration_seconds is not None
            ):
                shot_description.duration_seconds = shot_brief_description.duration_seconds
            print(f"🚀 Loaded shot {shot_brief_description.idx} description from existing file.")
        else:
            shot_description = await self.storyboard_artist.decompose_visual_description(
                shot_brief_desc=shot_brief_description,
                characters=characters,
                props=props,
                retry_timeout=120,
            )
            with open(shot_description_path, 'w', encoding='utf-8') as f:
                json.dump(shot_description.model_dump(), f, ensure_ascii=False, indent=4)
            print(f"✅ Decomposed visual description for shot {shot_brief_description.idx} and saved to {shot_description_path}.")

        self.shot_desc_events[shot_brief_description.idx].set()

        if shot_description.variation_type in ["medium", "large"]:
            self.frame_events[shot_brief_description.idx] = {
                "first_frame": asyncio.Event(),
                "last_frame": asyncio.Event(),
            }
        else:
            self.frame_events[shot_brief_description.idx] = {
                "first_frame": asyncio.Event(),
            }

        return shot_description
