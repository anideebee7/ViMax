"""
Idea to Learning Series Pipeline

Generates educational video series with curriculum structure,
actual video content for each episode, and monetization recommendations.

Supports S3 characters (e.g., Autocurio) and game/brand icons for branding.
"""
import json
import logging
import os
import asyncio
import shutil
from typing import Optional, Dict, Any, List

import yaml
import importlib
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.planners.content import CurriculumPlanner, Episode
from agents.directors.film import LearningSeriesDirector
from agents.producers.audio import AudioPlanner
from agents.producers.business import MonetizationAdvisor
from agents.producers.visuals import StoryboardArtist
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
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
from utils.pipeline.checkpoint import CheckpointManager
from utils.media.video import concat_videos, ffmpeg_concat_videos
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene
from interfaces.content.director_brief import DirectorBrief
from configs.constants.pipeline_profiles import LEARNING_SERIES_PROFILE


# =============================================================================
# Visual Description Models for Educational Content
# =============================================================================

class EpisodeSegmentVisual(BaseModel):
    """Visual description for a single segment of an educational episode."""
    
    segment_name: str = Field(..., description="Segment name (hook, teach, show, practice, recap)")
    duration_seconds: int = Field(..., description="Duration of this segment in seconds")
    visual_description: str = Field(..., description="Detailed visual description for video generation")
    on_screen_text: List[str] = Field(default_factory=list, description="Text to display on screen")
    visual_type: str = Field(..., description="Type: instructor, diagram, screencast, animation, b-roll")


class EpisodeVisualPlan(BaseModel):
    """Complete visual plan for an educational episode."""
    
    episode_number: int = Field(..., description="Episode number")
    episode_title: str = Field(..., description="Episode title")
    total_duration_seconds: int = Field(..., description="Total duration")
    segments: List[EpisodeSegmentVisual] = Field(..., description="Visual segments")
    thumbnail_description: str = Field(..., description="Thumbnail image description")
    color_scheme: str = Field(..., description="Color scheme for consistency")


VISUAL_PLANNER_SYSTEM_PROMPT = """
[Role]
You are a world-class educational visual producer and lead designer for top-tier online platforms. You are a master of "Pedagogical Visualization" - the art of making complex intellectual concepts instantly clear, engaging, and unforgettable through cinematic visuals.

[Task]
Create a detailed visual plan for an educational video episode that is a creative and pedagogical masterpiece. Your goal is a 10/10 score for learning retention, visual clarity, and student obsession.

[Guidelines - The Pedagogical Architecture Standard]
- PEDAGOGICAL CLARITY: Every shot must have a specific learning purpose. Use high-contrast compositions to direct attention to key data.
- INFOGRAPHIC FUSION: Plan every frame to seamlessly integrate text overlays, dynamic diagrams, and highlighted concepts.
- STEP-BY-STEP VIZ: Break complex systems into visceral, logical visual sequences.
- KINETIC ENGAGEMENT: Use "Lens-Based" movement (push-ins for focus, pans for overview) to keep the learner's brain in a state of flow.
- SYMBOLIC COLORS: Use a consistent, professional color DNA to represent different types of information (e.g., blue for theory, green for application).
- SCORE GOAL: Aim for absolute perfection. Your plan should feel like it defines the future of digital learning.
{character_guidelines}
{branding_guidelines}
"""

VISUAL_PLANNER_HUMAN_PROMPT = """
<EPISODE>
Episode {episode_number}: {episode_title}
Duration: {duration_minutes} minutes

Hook: {hook}

Learning Objectives:
{objectives}

Key Concepts:
{concepts}

Content Outline:
{outline}

Practical Exercise: {exercise}

Summary Points:
{summary}
</EPISODE>

<TOPIC>
{topic}
</TOPIC>

<STYLE>
{style}
</STYLE>
{director_context}
{character_context}
{branding_context}
Create a detailed visual plan for this educational episode with specific visuals for each segment.
"""

# Character integration guidelines
CHARACTER_GUIDELINES_TEMPLATE = """
[Character Integration - {character_name}]
- The character {character_name} should appear in KEY TEACHING MOMENTS
- Use {character_name} to explain complex concepts in an engaging way
- {character_name} should appear in: Hook, important Teach segments, and Recap
- Character Description: {character_description}
- Character Appearance: {character_appearance}
- Personality: {character_personality}
- IMPORTANT: Include {character_name} in visual descriptions naturally as a teaching companion
"""

# Branding guidelines - centered watermark
BRANDING_GUIDELINES_TEMPLATE = """
[Branding Watermark - {app_name}]
- ALWAYS include the {app_name} app logo/icon as a CENTERED WATERMARK in EVERY frame
- Position: CENTER of frame (not corner)
- Opacity: LOW (15-20% transparency) - visible but not distracting
- This is a trademark watermark that must be present throughout ALL episodes
- Brand colors: {brand_colors}
- The watermark creates consistent branding without interfering with content
"""


class LearningSeriesPipeline:
    """Pipeline to generate educational video series with actual video content.
    
    Supports S3 integration for:
    - Characters (e.g., Autocurio) that appear in teaching moments
    - Game/Brand icons for consistent branding (top right watermark)
    """

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/learning_series",
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
            pipeline_name="learning_series",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.curriculum_planner = CurriculumPlanner(chat_model=self.chat_model)
        self.learning_series_director = LearningSeriesDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="learning_series")
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.audio_planner = AudioPlanner(chat_model=self.chat_model, pipeline_kind="learning_series")
        self.checkpoint = CheckpointManager(
            working_dir=self.working_dir,
            run_id=self.run_id,
            pipeline_type="learning_series"
        )
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="learning_series", run_id=self.run_id, local_dir=self.working_dir)
        
        # S3 entity data (populated during __call__ if specified)
        self.characters: List[CharacterInScene] = []
        self.featured_character: Optional[CharacterInScene] = None
        self.game_icon_path: Optional[str] = None
        self.brand_icon_path: Optional[str] = None
        self.app_name: Optional[str] = None
        self.brand_colors: str = "vibrant, professional"

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

        # Rate limiters
        image_rpm = config.get("image_generator", {}).get("max_requests_per_minute")
        video_rpm = config.get("video_generator", {}).get("max_requests_per_minute")

        image_rate_limiter = RateLimiter(max_requests_per_minute=image_rpm) if image_rpm else None
        video_rate_limiter = RateLimiter(max_requests_per_minute=video_rpm) if video_rpm else None

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators(
            image_rate_limiter=image_rate_limiter,
            video_rate_limiter=video_rate_limiter,
        )

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir or resolve from config
        resolved_working_dir = working_dir or (_resolve_path(config["working_dir"]) or config["working_dir"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=resolved_working_dir,
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
        )

    async def _plan_episode_visuals(
        self,
        episode: Episode,
        topic: str,
        style: str = "professional educational",
        director_brief: Optional[DirectorBrief] = None,
    ) -> EpisodeVisualPlan:
        """Generate visual plan for an episode."""
        parser = PydanticOutputParser(pydantic_object=EpisodeVisualPlan)
        director_context = director_brief.to_context_block() if director_brief else ""
        
        # Build character guidelines if we have a featured character
        character_guidelines = ""
        character_context = ""
        if self.featured_character:
            char = self.featured_character
            char_name = char.identifier_in_scene
            character_guidelines = CHARACTER_GUIDELINES_TEMPLATE.format(
                character_name=char_name,
                character_description=char.description or "A friendly animated character",
                character_appearance=char.appearance or char.static_features or "Colorful, animated, approachable design",
                character_personality=char.personality or "Curious, helpful, engaging",
            )
            character_context = f"""
<CHARACTER>
Featured Character: {char_name}
Description: {char.description or 'A friendly teaching companion'}
Appearance: {char.appearance or char.static_features or 'Animated, colorful, engaging design'}
Role: Appears in key teaching moments to explain concepts
Voice/Personality: {char.personality or 'Curious and helpful'}
</CHARACTER>
"""
        
        # Build branding guidelines if we have app/game icon
        branding_guidelines = ""
        branding_context = ""
        if self.app_name:
            branding_guidelines = BRANDING_GUIDELINES_TEMPLATE.format(
                app_name=self.app_name,
                brand_colors=self.brand_colors,
            )
            branding_context = f"""
<BRANDING>
App/Game: {self.app_name}
IMPORTANT: Include {self.app_name} icon/logo in TOP RIGHT corner of every visual
Brand Colors: {self.brand_colors}
</BRANDING>
"""
        
        messages = [
            SystemMessage(content=VISUAL_PLANNER_SYSTEM_PROMPT.format(
                format_instructions=parser.get_format_instructions(),
                character_guidelines=character_guidelines,
                branding_guidelines=branding_guidelines,
            )),
            HumanMessage(content=VISUAL_PLANNER_HUMAN_PROMPT.format(
                episode_number=episode.episode_number,
                episode_title=episode.title,
                duration_minutes=episode.duration_minutes,
                hook=episode.hook,
                objectives="\n".join(f"- {obj}" for obj in episode.learning_objectives),
                concepts="\n".join(f"- {c}" for c in episode.key_concepts),
                outline="\n".join(f"- {o}" for o in episode.outline),
                exercise=episode.practical_exercise or "No exercise",
                summary="\n".join(f"- {s}" for s in episode.summary_points),
                topic=topic,
                style=style,
                director_context=f"<DIRECTOR_BRIEF>\n{director_context}\n</DIRECTOR_BRIEF>\n" if director_context else "",
                character_context=character_context,
                branding_context=branding_context,
            )),
        ]
        
        chain = self.chat_model | parser
        return await chain.ainvoke(messages)

    def _build_character_prompt(self, segment_name: str) -> str:
        """Build character inclusion prompt based on segment type."""
        if not self.featured_character:
            return ""
        
        char = self.featured_character
        char_name = char.identifier_in_scene
        # Include character in key segments: Hook, Teach (important concepts), Recap
        key_segments = ["hook", "teach", "recap", "show"]
        if segment_name.lower() in key_segments:
            return f"""
FEATURED CHARACTER: {char_name}
- {char_name} appears in frame as a teaching companion
- Appearance: {char.appearance or char.static_features or 'Animated, friendly character'}
- {char_name} gestures and reacts to explain the concept
- Character is positioned naturally within the scene
"""
        return ""
    
    def _build_branding_prompt(self) -> str:
        """Build branding/watermark prompt with centered low-visibility logo."""
        if not self.app_name:
            return ""
        return f"""
BRANDING WATERMARK (REQUIRED):
- {self.app_name} app logo/icon appears as a CENTERED WATERMARK
- Position: CENTER of the frame
- Visibility: LOW OPACITY (15-20% transparency) - subtle but always present
- The watermark should be visible but NOT distracting from the educational content
- Consistent across ALL frames and segments
- This is a trademark watermark - must appear throughout
"""

    def _get_brand_icon_path(self) -> Optional[str]:
        """Get the brand/game icon path for watermarking."""
        # Prefer game icon, then brand icon
        if self.game_icon_path and os.path.exists(self.game_icon_path):
            return self.game_icon_path
        if self.brand_icon_path and os.path.exists(self.brand_icon_path):
            return self.brand_icon_path
        return None

    async def _generate_transition_frame(
        self,
        previous_frame_path: str,
        current_segment: EpisodeSegmentVisual,
        episode_dir: str,
        segment_idx: int,
    ) -> Optional[str]:
        """Generate a transition frame between segments for smooth visual flow."""
        from utils.media.image import generate_transition_frame
        
        transition_path = os.path.join(episode_dir, f"transition_{segment_idx:02d}.png")
        
        return await generate_transition_frame(
            image_generator=self.image_generator,
            previous_frame_path=previous_frame_path,
            current_shot_description=current_segment.visual_description,
            output_path=transition_path,
            style="professional educational",
            strength=0.4,
        )
    
    async def _generate_segment_image(
        self,
        segment: EpisodeSegmentVisual,
        episode_dir: str,
        segment_idx: int,
        episode_number: Optional[int] = None,
        location: Optional[str] = None,
        previous_frame: Optional[str] = None,
    ) -> Optional[str]:
        """Generate an image for a segment with full continuity support."""
        if not self.image_generator:
            return None
        
        try:
            # Get establishment frame and previous shot reference
            location_name = location or f"episode_{episode_number or 0}"
            establishment_frame = self.continuity_memory.location_establishment_frames.get(location_name)
            previous_shot_ref = previous_frame or self.continuity_memory.previous_shot_frame
            
            # Get lighting from continuity memory for consistency
            lighting_context = self.continuity_memory.get_lighting_for_location(location_name)
            lighting_instruction = f" Lighting: {lighting_context}." if lighting_context else ""
            
            # Get scene context for lighting if available
            scene_id = f"episode_{episode_number or 0}"
            scene_context = self.continuity_memory.get_scene_context(scene_id)
            if scene_context.lighting and not lighting_instruction:
                lighting_instruction = f" Lighting: {scene_context.lighting}."
            
            # Build educational-style prompt with character and branding
            character_prompt = self._build_character_prompt(segment.segment_name)
            branding_prompt = self._build_branding_prompt()
            
            # Build character context with static_features
            char_context = ""
            if self.featured_character and self.featured_character.static_features:
                char_context = f" Character: {self.featured_character.identifier_in_scene}: {self.featured_character.static_features}."
            
            # Add view and expression guidance
            view_instruction = ""
            expression_instruction = ""
            if self.featured_character:
                view = get_character_view_for_shot(segment.visual_description)
                expression = get_character_expression_for_shot(segment.visual_description)
                view_instruction = f" Camera angle: {view.value} view."
                expression_instruction = f" Character expression: {expression.value}."
            
            bg_prompt = f"""Educational video background. {segment.visual_description}
Style: Professional, clean, broadcast quality.{lighting_instruction}
Type: {segment.visual_type}
EMPTY ENVIRONMENT ONLY. No characters, no people, no robots, no figures.
{branding_prompt}
"""
            
            image_path = os.path.join(episode_dir, f"segment_{segment_idx:02d}_{segment.segment_name}.png")
            raw_image_path = image_path.replace(".png", "_raw.png")
            
            # --- TRACK 1: BACKGROUND GENERATION (Clean Environment) ---
            bg_refs = []
            if establishment_frame and os.path.exists(establishment_frame):
                bg_refs.append(establishment_frame)
            elif previous_shot_ref and os.path.exists(previous_shot_ref):
                bg_refs.append(previous_shot_ref)
            
            # Save debug prompt
            debug_dir = os.path.join(episode_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"segment_{segment_idx:02d}_{segment.segment_name}_bg_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(bg_prompt)

            bg_output = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=bg_refs if bg_refs else None,
            )
            bg_output.save(image_path)
            
            # --- TRACK 2: COMPOSITE CHARACTER (S3 Portrait) ---
            if self.featured_character and segment.segment_name.lower() in ["hook", "teach", "recap", "show"]:
                self._composite_character_on_segment(
                    image_path=image_path,
                    segment_name=segment.segment_name,
                    visual_desc=segment.visual_description,
                )
            
            # Post-process: add trademark watermark (game/app icon only)
            trademark_icon = self._get_brand_icon_path()
            if trademark_icon:
                self._add_watermark_to_image(image_path, trademark_icon)
            
            # --- TRACK 3: RAW GENERATION (Gelled Character) ---
            raw_prompt = f"""Educational video frame. {segment.visual_description}{char_context}{view_instruction}{expression_instruction}
Style: Professional, clean, broadcast quality, bright lighting.
Type: {segment.visual_type}
{character_prompt}
{branding_prompt}
Blend characters naturally into environment. No collages, no picture-in-picture, no separate reference image inserts.
"""
            if segment.on_screen_text:
                raw_prompt += f"\nText overlay: {segment.on_screen_text[0]}"
            
            # Build reference images for raw track
            raw_refs = [image_path]  # Start with composite frame
            if self.featured_character and segment.segment_name.lower() in ["hook", "teach", "recap", "show"]:
                char_portrait = self._get_character_portrait_path()
                if char_portrait and os.path.exists(char_portrait):
                    raw_refs.append(char_portrait)
            
            with open(os.path.join(debug_dir, f"segment_{segment_idx:02d}_{segment.segment_name}_raw_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(raw_prompt)

            raw_output = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
                strength=0.55,  # Blend with composite
            )
            raw_output.save(raw_image_path)
            
            # Register establishment frame for location
            if location_name not in self.continuity_memory.location_establishment_frames:
                self.continuity_memory.location_establishment_frames[location_name] = raw_image_path if os.path.exists(raw_image_path) else image_path
            
            # Detect props mentioned in segment description
            visible_prop_ids = []
            # Simple prop detection - can be enhanced with proper prop extraction
            prop_keywords = ["book", "whiteboard", "diagram", "chart", "screen", "tablet", "laptop", "pen", "paper"]
            for keyword in prop_keywords:
                if keyword.lower() in segment.visual_description.lower():
                    visible_prop_ids.append(keyword)
            
            # Update continuity memory with character and prop states
            visible_char_ids = [self.featured_character.identifier_in_scene] if self.featured_character else []
            self.continuity_memory.update_for_shot(
                shot_idx=segment_idx,
                frame_path=raw_image_path if os.path.exists(raw_image_path) else image_path,
                scene_id=f"episode_{episode_number or 0}",
                location=location_name,
                visible_characters=visible_char_ids,
                visible_props=visible_prop_ids if visible_prop_ids else None,
                shot_description=segment.visual_description,
            )
            
            self.logger.info(f"Generated image for segment: {segment.segment_name}")
            return raw_image_path if os.path.exists(raw_image_path) else image_path
        except Exception as e:
            self.logger.warning(f"Failed to generate image for {segment.segment_name}: {e}")
            return None
    
    def _add_watermark_to_image(self, image_path: str, watermark_path: str, opacity: float = 0.15) -> None:
        """Add a centered watermark overlay to an image.
        
        This ensures the brand/game icon appears consistently in all frames,
        since AI generators cannot reliably add watermarks from text prompts alone.
        """
        try:
            from PIL import Image
            
            # Open the base image and watermark
            base_image = Image.open(image_path).convert("RGBA")
            watermark = Image.open(watermark_path).convert("RGBA")
            
            # Calculate watermark size (20% of the smaller dimension)
            base_width, base_height = base_image.size
            watermark_size = int(min(base_width, base_height) * 0.20)
            
            # Resize watermark while maintaining aspect ratio
            wm_width, wm_height = watermark.size
            aspect_ratio = wm_width / wm_height
            if wm_width > wm_height:
                new_width = watermark_size
                new_height = int(watermark_size / aspect_ratio)
            else:
                new_height = watermark_size
                new_width = int(watermark_size * aspect_ratio)
            
            watermark = watermark.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Apply opacity to watermark
            alpha = watermark.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            watermark.putalpha(alpha)
            
            # Calculate center position
            x = (base_width - new_width) // 2
            y = (base_height - new_height) // 2
            
            # Composite watermark onto base image
            base_image.paste(watermark, (x, y), watermark)
            
            # Convert back to RGB and save
            base_image = base_image.convert("RGB")
            base_image.save(image_path)
            
            self.logger.info(f"Added watermark to: {image_path}")
        except Exception as e:
            self.logger.warning(f"Failed to add watermark to {image_path}: {e}")

    def _get_character_portrait_path_with_view(
        self, 
        char_identifier: str, 
        view: CharacterView, 
        expression: CharacterExpression
    ) -> Optional[str]:
        """Get portrait path with view and expression support."""
        if not char_identifier:
            return None
        
        # 1. Check local character portraits directory
        gen_chars_dir = os.path.join(self.working_dir, "character_portraits")
        if os.path.exists(gen_chars_dir):
            for folder_name in os.listdir(gen_chars_dir):
                if char_identifier.lower() in folder_name.lower():
                    char_dir = os.path.join(gen_chars_dir, folder_name)
                    # Try view-specific path
                    view_path = os.path.join(char_dir, f"{view.value}.png")
                    if os.path.exists(view_path):
                        return view_path
                    # Fallback to front
                    front_path = os.path.join(char_dir, "front.png")
                    if os.path.exists(front_path):
                        return front_path

        # 2. Check S3 characters directory
        s3_chars_dir = os.path.join(self.working_dir, "s3_characters")
        if os.path.exists(s3_chars_dir):
            char_dir = None
            for folder_name in os.listdir(s3_chars_dir):
                if folder_name.lower() == char_identifier.lower():
                    char_dir = os.path.join(s3_chars_dir, folder_name)
                    break
            
            if char_dir and os.path.exists(char_dir):
                # Try view-specific path
                view_path = os.path.join(char_dir, f"{view.value}.png")
                if os.path.exists(view_path):
                    return view_path
                # Fallback to front
                front_path = os.path.join(char_dir, "front.png")
                if os.path.exists(front_path):
                    return front_path
        
        return None
    
    def _get_character_portrait_path_for(self, char_identifier: str) -> Optional[str]:
        """Get the front portrait path for a specific character by identifier."""
        if not char_identifier:
            return None
        
        # 1. Check local character portraits directory (for generated portraits)
        gen_chars_dir = os.path.join(self.working_dir, "character_portraits")
        if os.path.exists(gen_chars_dir):
            for folder_name in os.listdir(gen_chars_dir):
                if char_identifier.lower() in folder_name.lower():
                    char_dir = os.path.join(gen_chars_dir, folder_name)
                    front_path = os.path.join(char_dir, "front.png")
                    if os.path.exists(front_path):
                        return front_path

        # 2. Check S3 characters directory (case-insensitive)
        s3_chars_dir = os.path.join(self.working_dir, "s3_characters")
        if os.path.exists(s3_chars_dir):
            char_dir = None
            for folder_name in os.listdir(s3_chars_dir):
                if folder_name.lower() == char_identifier.lower():
                    char_dir = os.path.join(s3_chars_dir, folder_name)
                    break
            
            if char_dir and os.path.exists(char_dir):
                # Look for front portrait first
                front_path = os.path.join(char_dir, "front.png")
                if os.path.exists(front_path):
                    return front_path
                
                # Check for any image in the character directory
                for f in os.listdir(char_dir):
                    if f.endswith(('.png', '.jpg', '.jpeg')):
                        return os.path.join(char_dir, f)
        
        return None
    
    def _get_character_portrait_path(self) -> Optional[str]:
        """Get the front portrait path for the featured character."""
        if not self.featured_character:
            return None
        return self._get_character_portrait_path_for(self.featured_character.identifier_in_scene)
    
    def _composite_character_on_segment(
        self,
        image_path: str,
        segment_name: str,
        visual_desc: str = "",
    ) -> None:
        """
        Composite S3 character portraits onto a generated segment image.
        
        AI image generators cannot reliably reproduce specific character designs
        from reference images. This post-processing step overlays the actual
        S3 character portrait(s) to ensure visual consistency.
        
        Args:
            image_path: Path to the generated segment image
            segment_name: Segment name (hook, teach, etc.) to determine if character should appear
            visual_desc: Visual description for positioning hints
        """
        import re
        
        # Only composite on key teaching segments
        key_segments = ["hook", "teach", "recap", "show"]
        if segment_name.lower() not in key_segments:
            return
        
        if not os.path.exists(image_path):
            return
        
        # Collect all visible characters from visual description using regex
        visible_characters = []
        for char in self.characters:
            char_name = char.identifier_in_scene
            if not char_name:
                continue
            # Use word boundary regex for precise matching
            pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
            if re.search(pattern, visual_desc):
                visible_characters.append(char)
        
        # If no characters mentioned in desc but we have a featured character, use it
        if not visible_characters and self.featured_character:
            visible_characters = [self.featured_character]
        
        if not visible_characters:
            return
        
        # Collect portrait paths for visible characters with view/expression selection
        portraits_to_composite = []
        for char in visible_characters:
            # Use view/expression selector to get correct portrait
            view = get_character_view_for_shot(visual_desc)
            expression = get_character_expression_for_shot(visual_desc)
            
            # Try to get view/expression-specific portrait
            portrait_path = self._get_character_portrait_path_with_view(
                char.identifier_in_scene, view, expression
            )
            
            # Fallback to default portrait path
            if not portrait_path:
                portrait_path = self._get_character_portrait_path_for(char.identifier_in_scene)
            
            if portrait_path and os.path.exists(portrait_path):
                portraits_to_composite.append({
                    "path": portrait_path,
                    "name": char.identifier_in_scene
                })
        
        if not portraits_to_composite:
            return
        
        try:
            if len(portraits_to_composite) == 1:
                # Single character - infer position from description
                position = get_character_position_from_description(visual_desc, portraits_to_composite[0]["name"])
                scale = get_character_scale_from_shot_type(visual_desc)
                
                # For educational content, position character to the side
                # so they don't obstruct content
                if position == "center":
                    position = "right"  # Move to side for teaching content
                
                composite_character_on_image(
                    background_path=image_path,
                    character_path=portraits_to_composite[0]["path"],
                    output_path=image_path,
                    position=position,
                    scale_factor=min(scale, 0.35),  # Keep character smaller for educational content
                    vertical_offset=0.05,
                    blend_mode="soft",
                )
                self.logger.info(f"Composited {portraits_to_composite[0]['name']} onto segment: {segment_name}")
            else:
                # Multiple characters - use composite_multiple_characters
                paths = [p["path"] for p in portraits_to_composite]
                composite_multiple_characters(
                    background_path=image_path,
                    character_paths=paths,
                    output_path=image_path,
                    scale_factors=[0.3] * len(paths),  # Smaller for educational content
                )
                names = ", ".join([p["name"] for p in portraits_to_composite])
                self.logger.info(f"Composited {len(paths)} characters ({names}) onto segment: {segment_name}")
            
        except Exception as e:
            self.logger.warning(f"Failed to composite character on {segment_name}: {e}")

    async def _generate_segment_video(
        self,
        segment: EpisodeSegmentVisual,
        episode_dir: str,
        segment_idx: int,
        first_frame_path: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a video clip for a segment."""
        if not self.video_generator:
            return None
        
        try:
            # Build educational video prompt with character and branding
            character_prompt = self._build_character_prompt(segment.segment_name)
            branding_prompt = self._build_branding_prompt()
            
            prompt = f"""Educational video segment for online course.
{segment.visual_description}

Style: Professional educational content, clear visuals, engaging presentation.
Visual Type: {segment.visual_type}
Duration: {segment.duration_seconds} seconds
Atmosphere: Welcoming, authoritative, encouraging.
Camera: Steady, professional broadcast style.
{character_prompt}
{branding_prompt}
"""
            video_path = os.path.join(episode_dir, f"segment_{segment_idx:02d}_{segment.segment_name}.mp4")
            
            # Build reference images list - prefer first frame (which already has watermark)
            ref_images = []
            raw_frame_path = first_frame_path.replace(".png", "_raw.png") if first_frame_path else None
            # Use raw frame for video if available, otherwise fallback to composited
            video_ref_frame = raw_frame_path if raw_frame_path and os.path.exists(raw_frame_path) else first_frame_path
            
            if video_ref_frame and os.path.exists(video_ref_frame):
                ref_images.append(video_ref_frame)
            else:
                # If no first frame, add trademark icon as reference
                trademark_icon = self._get_brand_icon_path()
                if trademark_icon:
                    ref_images.append(trademark_icon)
            
            # Save debug prompt
            debug_dir = os.path.join(episode_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"segment_{segment_idx:02d}_{segment.segment_name}_video_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

            video_output = await self.video_generator.generate_single_video(
                prompt=prompt,
                reference_image_paths=ref_images if ref_images else None,
            )
            video_output.save(video_path)
            self.logger.info(f"Generated video for segment: {segment.segment_name}")
            return video_path
        except Exception as e:
            self.logger.warning(f"Failed to generate video for {segment.segment_name}: {e}")
            return None

    async def _generate_episode_video(
        self,
        episode: Episode,
        visual_plan: EpisodeVisualPlan,
        topic: str,
        episode_dir: str,
        generate_videos: bool = True,
    ) -> Dict[str, Any]:
        """Generate all visual content for an episode using parallel processing."""
        os.makedirs(episode_dir, exist_ok=True)
        
        # Plan audio requirements for this episode
        audio_plan_path = os.path.join(episode_dir, "audio_plan.json")
        audio_plan = None
        if os.path.exists(audio_plan_path) and not self.force_regenerate:
            self.logger.info(f"Loading existing audio plan for episode {episode.episode_number}...")
            audio_plan = self.audio_planner.load_audio_plan(audio_plan_path)
        
        if audio_plan is None:
            self.logger.info(f"Planning audio requirements for episode {episode.episode_number}...")
            try:
                from interfaces.content.scene import Scene
                from interfaces.entities.environment import EnvironmentInScene
                
                # Convert episode segments to Scene objects for audio planning
                scene_objects = []
                for idx, segment in enumerate(visual_plan.segments):
                    # Build script from segment visual description and episode content
                    segment_script = f"{segment.visual_description}"
                    if episode and hasattr(episode, 'segments') and idx < len(episode.segments):
                        ep_seg = episode.segments[idx]
                        if hasattr(ep_seg, 'narration') and ep_seg.narration:
                            segment_script += f"\nNarration: {ep_seg.narration}"
                        elif hasattr(ep_seg, 'content') and ep_seg.content:
                            segment_script += f"\nContent: {ep_seg.content}"
                    
                    scene_obj = Scene(
                        idx=idx,
                        is_last=(idx == len(visual_plan.segments) - 1),
                        environment=EnvironmentInScene(
                            slugline=f"EDUCATIONAL EPISODE {episode.episode_number} - {segment.segment_name}",
                            description=segment.segment_name,
                        ),
                        characters=[self.featured_character] if self.featured_character else [],
                        script=segment_script,
                    )
                    scene_objects.append(scene_obj)
                
                # Load previous episode audio plan for continuity
                previous_plan = None
                if episode.episode_number > 1:
                    prev_episode_dir = os.path.join(self.working_dir, f"episode_{episode.episode_number - 1:02d}")
                    prev_audio_plan_path = os.path.join(prev_episode_dir, "audio_plan.json")
                    if os.path.exists(prev_audio_plan_path):
                        previous_plan = self.audio_planner.load_audio_plan(prev_audio_plan_path)
                
                audio_plan = await self.audio_planner.plan_audio_for_scenes(
                    scenes=scene_objects,
                    shots_per_scene=None,
                    previous_audio_plan=previous_plan,
                    style="professional educational",
                    audience=None,
                    content_format="animated",
                )
                
                self.audio_planner.save_audio_plan(audio_plan, audio_plan_path)
                self.logger.info(f"Audio plan created for episode {episode.episode_number} with {len(audio_plan.scene_plans)} segment plans")
            except Exception as e:
                self.logger.warning(f"Failed to create audio plan for episode {episode.episode_number}: {e}. Continuing without detailed audio planning.")
                audio_plan = None
        
        segment_images = [None] * len(visual_plan.segments)
        segment_videos = [None] * len(visual_plan.segments)
        
        # Parallel semaphore to avoid overloading APIs
        semaphore = asyncio.Semaphore(5)
        
        async def process_segment(idx, segment):
            async with semaphore:
                # Get previous segment frame for transition
                previous_segment_frame = None
                if idx > 0:
                    prev_image = segment_images[idx - 1]
                    if prev_image and prev_image.get("path"):
                        previous_segment_frame = prev_image["path"]
                    else:
                        # Try to get from continuity memory
                        previous_segment_frame = self.continuity_memory.get_transition_reference()
                
                # 1. Generate transition frame if needed (for smooth segment transitions)
                transition_frame_path = None
                if previous_segment_frame and self.image_generator and idx > 0:
                    transition_frame_path = await self._generate_transition_frame(
                        previous_frame_path=previous_segment_frame,
                        current_segment=segment,
                        episode_dir=episode_dir,
                        segment_idx=idx,
                    )
                
                # 2. Generate image for current segment
                image_path = await self._generate_segment_image(
                    segment, 
                    episode_dir, 
                    idx,
                    episode_number=episode.episode_number,
                    location=f"episode_{episode.episode_number}",
                    previous_frame=transition_frame_path or previous_segment_frame,
                )
                if image_path:
                    segment_images[idx] = {
                        "segment": segment.segment_name,
                        "path": image_path,
                        "transition_frame": transition_frame_path,
                    }
                
                # 3. Generate video if enabled
                if generate_videos:
                    # Use transition frame if available, otherwise use segment image
                    video_ref_frame = transition_frame_path if transition_frame_path else image_path
                    video_path = await self._generate_segment_video(
                        segment, episode_dir, idx, first_frame_path=video_ref_frame or image_path
                    )
                    if video_path:
                        segment_videos[idx] = {
                            "segment": segment.segment_name,
                            "path": video_path,
                            "duration_seconds": segment.duration_seconds,
                        }

        # Launch all segments in parallel
        tasks = [process_segment(i, s) for i, s in enumerate(visual_plan.segments)]
        await asyncio.gather(*tasks)
        
        # Filter out Nones from failed segments
        valid_images = [img for img in segment_images if img is not None]
        valid_videos = [vid for vid in segment_videos if vid is not None]
        
        # Generate thumbnail
        thumbnail_path = None
        if self.image_generator:
            try:
                thumb_prompt = f"YouTube thumbnail for educational video. {visual_plan.thumbnail_description}. Eye-catching, professional, clean design."
                thumb_path = os.path.join(episode_dir, "thumbnail.png")
                
                # Save debug prompt
                debug_dir = os.path.join(episode_dir, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "thumbnail_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(thumb_prompt)

                thumb_output = await self.image_generator.generate_single_image(prompt=thumb_prompt)
                thumb_output.save(thumb_path)
                thumbnail_path = thumb_path
            except Exception as e:
                self.logger.warning(f"Failed to generate thumbnail: {e}")
        
        # Concatenate videos into full episode using ffmpeg (OOM safe)
        final_video_path = None
        if valid_videos and generate_videos:
            try:
                video_paths = [v["path"] for v in valid_videos]
                final_video_path = os.path.join(episode_dir, f"episode_{episode.episode_number:02d}_full.mp4")
                
                if len(video_paths) > 5:
                    ffmpeg_concat_videos(video_paths, final_video_path)
                else:
                    concat_videos(video_paths, final_video_path)
                
                # Generate and add audio if video doesn't have audio
                from moviepy import VideoFileClip
                from utils.pipeline.audio_helper import ensure_video_has_audio
                
                # Collect audio descriptions from episode content
                audio_descriptions = []
                if episode and hasattr(episode, 'segments'):
                    for segment in episode.segments:
                        if hasattr(segment, 'narration') and segment.narration:
                            audio_descriptions.append(segment.narration[:200])
                        elif hasattr(segment, 'content') and segment.content:
                            audio_descriptions.append(segment.content[:200])
                
                await ensure_video_has_audio(
                    video_path=final_video_path,
                    audio_descriptions=audio_descriptions if audio_descriptions else None,
                    working_dir=episode_dir,
                    force_regenerate=self.force_regenerate,
                )
                
                self.logger.info(f"Created full episode video: {final_video_path}")
            except Exception as e:
                self.logger.warning(f"Failed to concatenate episode video: {e}")
        
        return {
            "episode_number": episode.episode_number,
            "title": episode.title,
            "visual_plan": visual_plan.model_dump(),
            "segment_images": valid_images,
            "segment_videos": valid_videos,
            "thumbnail_path": thumbnail_path,
            "final_video_path": final_video_path,
        }

    def _resolve_s3_entities(
        self,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_names: Optional[List[str]] = None,
        featured_character_name: Optional[str] = None,
    ) -> None:
        """Resolve S3 entities and download assets."""
        self.logger.info("="*60)
        self.logger.info("Resolving S3 entities...")
        self.logger.info(f"  brand_id: {brand_id}")
        self.logger.info(f"  game_id: {game_id}")
        self.logger.info(f"  character_names: {character_names}")
        self.logger.info(f"  featured_character_name: {featured_character_name}")
        
        # Build texts with character tags for entity resolution
        texts = []
        if character_names:
            for char_name in character_names:
                texts.append(f"@character:{char_name}")
        
        # Resolve entities from S3 (synchronous function)
        resolution = resolve_s3_entities(
            texts=texts,
            brand_hint=brand_id,
            game_hint=game_id,
            working_dir=self.working_dir,
        )
        
        # Store characters
        self.characters = resolution.get("characters") or []
        self.logger.info(f"Resolved {len(self.characters)} characters: {[c.identifier_in_scene for c in self.characters]}")
        
        # Set featured character (case-insensitive)
        if featured_character_name and self.characters:
            for char in self.characters:
                if char.identifier_in_scene.lower() == featured_character_name.lower():
                    self.featured_character = char
                    self.logger.info(f"Featured character set: {char.identifier_in_scene}")
                    break
        if not self.featured_character and self.characters:
            # Default to first character if none specified
            self.featured_character = self.characters[0]
            self.logger.info(f"Featured character (default): {self.featured_character.identifier_in_scene}")
        
        # Handle game icon/branding
        game_data = resolution.get("game_data") or {}
        resolved_game_id = resolution.get("game_id")
        if game_data:
            self.app_name = game_data.get("name") or resolved_game_id or game_id
            self.logger.info(f"Game branding set: {self.app_name}")
        
        # Handle brand as fallback
        brand_data = resolution.get("brand_data") or {}
        resolved_brand_id = resolution.get("brand_id")
        if brand_data and not self.app_name:
            self.app_name = brand_data.get("name") or resolved_brand_id or brand_id
            self.logger.info(f"Brand branding set: {self.app_name}")
        
        # =========================================================================
        # Extract and store game/brand icon paths from reference_images
        # =========================================================================
        reference_images = resolution.get("reference_images") or []
        self.logger.info(f"Reference images downloaded: {len(reference_images)}")
        
        for ref_img in reference_images:
            ref_path = ref_img.get("path")
            ref_desc = ref_img.get("description", "").lower()
            self.logger.info(f"  - {ref_img.get('description')}: {ref_path} (exists: {os.path.exists(ref_path) if ref_path else False})")
            
            if ref_path and os.path.exists(ref_path):
                if "game icon" in ref_desc or "game_icon" in ref_path:
                    self.game_icon_path = ref_path
                    self.logger.info(f"  -> Set as GAME ICON: {self.game_icon_path}")
                elif "brand logo" in ref_desc or "brand_logo" in ref_path:
                    self.brand_icon_path = ref_path
                    self.logger.info(f"  -> Set as BRAND LOGO: {self.brand_icon_path}")
        
        # When game_id is specified for trademark, use ONLY the game/app icon.
        # Exclude the brand logo so the "old" brand logo does not appear in the video.
        if game_id and self.game_icon_path:
            if self.brand_icon_path and os.path.exists(self.brand_icon_path):
                try:
                    os.remove(self.brand_icon_path)
                    self.logger.info(f"Removed brand logo (using only game icon for trademark): {self.brand_icon_path}")
                except OSError as e:
                    self.logger.warning(f"Could not remove brand logo file: {e}")
            self.brand_icon_path = None
            self.logger.info("Trademark: using only game/app icon; brand logo excluded.")
        
        # Verify character portraits directory
        s3_char_dir = os.path.join(self.working_dir, "s3_characters")
        if os.path.exists(s3_char_dir):
            char_folders = os.listdir(s3_char_dir)
            self.logger.info(f"Character portraits available at: {s3_char_dir}")
            self.logger.info(f"  Folders: {char_folders}")
            
            # Log contents of each character folder
            for folder in char_folders:
                folder_path = os.path.join(s3_char_dir, folder)
                if os.path.isdir(folder_path):
                    files = os.listdir(folder_path)
                    self.logger.info(f"  {folder}/: {files}")
        else:
            self.logger.warning(f"Character portraits directory NOT found: {s3_char_dir}")
        
        # Verify final paths
        self.logger.info("="*60)
        self.logger.info("FINAL S3 ENTITY PATHS:")
        self.logger.info(f"  app_name: {self.app_name}")
        self.logger.info(f"  game_icon_path: {self.game_icon_path} (exists: {os.path.exists(self.game_icon_path) if self.game_icon_path else False})")
        self.logger.info(f"  brand_icon_path: {self.brand_icon_path} (exists: {os.path.exists(self.brand_icon_path) if self.brand_icon_path else False})")
        self.logger.info(f"  featured_character: {self.featured_character.identifier_in_scene if self.featured_character else None}")
        
        # Test character portrait path resolution
        if self.featured_character:
            portrait_path = self._get_character_portrait_path()
            self.logger.info(f"  character_portrait_path: {portrait_path} (exists: {os.path.exists(portrait_path) if portrait_path else False})")
        self.logger.info("="*60)
        
        # Save entity resolution info
        entity_info = {
            "brand_id": resolved_brand_id or brand_id,
            "game_id": resolved_game_id or game_id,
            "app_name": self.app_name,
            "game_icon_path": self.game_icon_path,
            "brand_icon_path": self.brand_icon_path,
            "featured_character": self.featured_character.identifier_in_scene if self.featured_character else None,
            "characters": [c.identifier_in_scene for c in self.characters] if self.characters else [],
        }
        with open(os.path.join(self.working_dir, "s3_entities.json"), "w") as f:
            json.dump(entity_info, f, indent=2)

    async def __call__(
        self,
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 10,
        audience: Optional[str] = None,
        skill_level: str = "beginner",
        learning_goals: Optional[str] = None,
        trendy: bool = False,
        generate_images: bool = True,
        generate_videos: bool = True,
        visual_style: str = "professional educational, clean, modern",
        max_episodes_to_generate: Optional[int] = None,
        restitch_only: bool = False,
        # S3 Entity Integration
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_names: Optional[List[str]] = None,
        featured_character: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate an educational video series with curriculum and actual video content.

        Args:
            topic: Course topic
            num_episodes: Number of episodes
            episode_duration_minutes: Duration per episode
            audience: Target audience (students, professionals, etc.)
            skill_level: Starting skill level
            learning_goals: Specific learning goals
            trendy: Whether to incorporate trending topics
            generate_images: Whether to generate images for segments
            generate_videos: Whether to generate video clips for segments
            visual_style: Visual style for the series
            max_episodes_to_generate: Limit video generation to N episodes (for testing)
            brand_id: S3 brand ID for branding (e.g., "intelli-verse-x")
            game_id: S3 game ID for app icon branding (e.g., "quizverse")
            character_names: List of S3 character names to include
            featured_character: Name of character to feature in teaching moments (e.g., "Autocurio")

        Returns:
            Dictionary with curriculum, episodes, videos, and monetization plan
        """
        output_json_path = os.path.join(self.working_dir, "learningseries_output.json")

        # RESUME CHECK: Try to sync from S3 if local folder is missing/incomplete
        if not os.path.exists(self.working_dir) or not os.path.exists(output_json_path):
            self.logger.info(f"Attempting to sync run state from S3 for run_id: {self.run_id}")
            if self.memory.sync_from_s3():
                self.logger.info("✅ Synced run state from S3")
                # Reload continuity memory after sync
                self.continuity_memory.load_series_state()
            else:
                self.logger.info("No existing run found in S3, starting fresh")

        # RESUME CHECK: Load checkpoint and check if run can be resumed
        checkpoint = self.checkpoint.load()
        can_resume = self.checkpoint.can_resume()
        
        if can_resume and not self.force_regenerate:
            resume_info = self.checkpoint.get_resume_info()
            self.logger.info(f"🔄 Resuming incomplete run (status: {resume_info['status']})")
            self.logger.info(f"   Completed phases: {resume_info['completed_phases']}")
            self.logger.info(f"   Completed episodes: {resume_info['completed_episodes']}")
            if resume_info.get('errors'):
                self.logger.warning(f"   Previous errors: {resume_info['errors']}")
        elif not checkpoint:
            # Initialize new checkpoint
            self.checkpoint.initialize(metadata={
                "topic": topic,
                "num_episodes": num_episodes,
                "audience": audience,
                "visual_style": visual_style,
            })

        # RESUME CHECK: If output exists and run is completed, return it
        if os.path.exists(output_json_path) and not self.force_regenerate and not restitch_only:
            if checkpoint and checkpoint.status == "completed":
                self.logger.info("✅ Run already completed, loading output")
                with open(output_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)

        # Step 0: Resolve S3 entities if specified
        if brand_id or game_id or character_names:
            print(f"🔗 Resolving S3 entities...")
            self._resolve_s3_entities(
                brand_id=brand_id,
                game_id=game_id,
                character_names=character_names,
                featured_character_name=featured_character,
            )
            if self.featured_character:
                print(f"   Featured Character: {self.featured_character.identifier_in_scene}")
            if self.app_name:
                print(f"   App Branding: {self.app_name}")

        # Fetch trends if trendy flag is set
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if trendy and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="education")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Curriculum
        curriculum_path = os.path.join(self.working_dir, "curriculum.json")
        curriculum = None
        director_brief = None
        
        if self.checkpoint.is_phase_completed("curriculum") and os.path.exists(curriculum_path) and not self.force_regenerate:
            self.logger.info(f"📚 Resuming: Curriculum already completed")
            with open(curriculum_path, "r", encoding="utf-8") as f:
                curriculum_data = json.load(f)
                from agents.curriculum_planner import Curriculum
                curriculum = Curriculum(**curriculum_data)
        elif os.path.exists(curriculum_path) and not self.force_regenerate:
            # Load existing curriculum and mark as completed
            self.logger.info(f"📚 Loading existing curriculum: {curriculum_path}")
            with open(curriculum_path, "r", encoding="utf-8") as f:
                curriculum_data = json.load(f)
                from agents.curriculum_planner import Curriculum
                curriculum = Curriculum(**curriculum_data)
            self.checkpoint.complete_phase("curriculum", output_files=[curriculum_path])
        else:
            # Generate new curriculum
            self.checkpoint.start_phase("curriculum")
            try:
                # Director: creative brief
                director_brief = await self.learning_series_director.direct(
                    topic=topic,
                    num_episodes=num_episodes,
                    episode_duration_minutes=episode_duration_minutes,
                    audience=audience,
                    skill_level=skill_level,
                    visual_style=visual_style,
                    additional_context=trend_context_block if trend_context_block else None,
                )
                series_context = f"{trend_context_block or ''}\n\n{director_brief.to_context_block()}".strip()

                # Step 1: Generate curriculum
                self.logger.info("📚 Generating curriculum...")
                
                # Save debug prompt
                debug_dir = os.path.join(self.working_dir, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "curriculum_prompt.txt"), "w", encoding="utf-8") as f:
                    f.write(f"Topic: {topic}\nContext: {series_context}")

                curriculum = await self.curriculum_planner.plan_curriculum(
                    topic=topic,
                    num_episodes=num_episodes,
                    episode_duration_minutes=episode_duration_minutes,
                    audience=audience or "general learners",
                    skill_level=skill_level,
                    learning_goals=learning_goals,
                    additional_context=series_context,
                )
                with open(curriculum_path, "w", encoding="utf-8") as f:
                    json.dump(curriculum.model_dump(), f, ensure_ascii=False, indent=2)
                
                self.checkpoint.complete_phase("curriculum", output_files=[curriculum_path])
            except Exception as e:
                self.checkpoint.fail_phase("curriculum", str(e))
                self.logger.error(f"Failed to generate curriculum: {e}")
                raise

        # Phase 1 reasoning: rationale behind the curriculum (script for the series)
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="learning_series",
            phase_label="Phase 1: Curriculum and episode scripts",
            content_type="curriculum",
            rationale=(
                "The curriculum is the narrative and pedagogical script for the series. CurriculumPlanner "
                "defines course title, learning objectives, and episode breakdown (hook, objectives, concepts, "
                "outline, exercise, summary). LearningSeriesDirector sets the visual style and pacing. "
                "Topic, audience, skill_level, and learning_goals drive structure so each episode builds "
                "clearly and stays on-level. Trends can suggest topical angles when enabled."
            ),
            inputs={
                "topic": topic,
                "num_episodes": num_episodes,
                "episode_duration_minutes": episode_duration_minutes,
                "audience": audience,
                "skill_level": skill_level,
                "learning_goals": (learning_goals or "")[:200],
                "visual_style": visual_style,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={
                "curriculum.json": "Curriculum (course_title, episodes with objectives, concepts, outline, exercise, summary).",
                "episodes/episode_XX.json": "Per-episode scripts (one file per episode).",
            },
        )
        
        print(f"✅ Curriculum generated: {curriculum.course_title}")
        print(f"   {num_episodes} episodes, {curriculum.total_duration_minutes} total minutes")

        # Save episode scripts
        episodes_dir = os.path.join(self.working_dir, "episodes")
        os.makedirs(episodes_dir, exist_ok=True)
        for episode in curriculum.episodes:
            episode_path = os.path.join(episodes_dir, f"episode_{episode.episode_number:02d}.json")
            with open(episode_path, "w", encoding="utf-8") as f:
                json.dump(episode.model_dump(), f, ensure_ascii=False, indent=2)

        # Step 2: Generate visual plans and videos for each episode
        episode_media = []
        episodes_to_generate = curriculum.episodes
        if max_episodes_to_generate:
            episodes_to_generate = curriculum.episodes[:max_episodes_to_generate]
        
        # Load series-level continuity state (cross-episode persistence)
        self.continuity_memory.load_series_state()
        
        if (generate_images or generate_videos) and (self.image_generator or self.video_generator):
            self.logger.info(f"🎬 Generating visual content for {len(episodes_to_generate)} episodes...")
            
            # RESUME CHECK: Full Series Video
            final_series_video_path = os.path.join(self.working_dir, "full_learning_series.mp4")
            if os.path.exists(final_series_video_path) and not self.force_regenerate:
                self.logger.info(f"  Resuming from existing full series video: {final_series_video_path}")
                # We still need to return the media list for the metadata
                # (Ideally we'd load episode_media.json if it exists)
                media_json_path = os.path.join(self.working_dir, "episode_media.json")
                if os.path.exists(media_json_path):
                    with open(media_json_path, "r", encoding="utf-8") as f:
                        episode_media = json.load(f)
                        return {**locals(), "episode_media": episode_media}

            # Limit concurrent episode generation
            episode_semaphore = asyncio.Semaphore(2) 

            async def process_episode(episode):
                async with episode_semaphore:
                    # RESUME CHECK: Skip if episode already completed
                    if self.checkpoint.is_episode_completed(episode.episode_number) and not self.force_regenerate:
                        episode_dir = os.path.join(self.working_dir, f"episode_{episode.episode_number:02d}")
                        final_ep_video = os.path.join(episode_dir, f"episode_{episode.episode_number:02d}_full.mp4")
                        if os.path.exists(final_ep_video):
                            self.logger.info(f"🎥 Resuming: Episode {episode.episode_number} already completed")
                            return {"episode_number": episode.episode_number, "final_video_path": final_ep_video}
                    
                    # Load continuity state at start of episode (for cross-episode consistency)
                    self.continuity_memory.load_series_state()
                    
                    episode_dir = os.path.join(self.working_dir, f"episode_{episode.episode_number:02d}")
                    final_ep_video = os.path.join(episode_dir, f"episode_{episode.episode_number:02d}_full.mp4")
                    
                    # RESUME CHECK: Check for existing video
                    if (os.path.exists(final_ep_video) and not self.force_regenerate) or restitch_only:
                        if restitch_only and not os.path.exists(final_ep_video):
                            self.logger.warning(f"  Restitch mode: Episode video NOT found at {final_ep_video}. Skipping.")
                            return {"episode_number": episode.episode_number, "error": "Video not found"}
                        
                        self.logger.info(f"🎥 Episode {episode.episode_number} already complete/restitching.")
                        # Mark as completed in checkpoint
                        self.checkpoint.complete_episode(episode.episode_number, output_files=[final_ep_video])
                        return {"episode_number": episode.episode_number, "final_video_path": final_ep_video}

                    self.logger.info(f"🎥 Processing Episode {episode.episode_number}: {episode.title}")
                    
                    # Start episode in checkpoint
                    self.checkpoint.start_episode(episode.episode_number)
                    
                    try:
                        # Plan visuals
                        visual_plan_path = os.path.join(episode_dir, "visual_plan.json")
                        if not os.path.exists(visual_plan_path) or self.force_regenerate:
                            visual_plan = await self._plan_episode_visuals(
                                episode=episode,
                                topic=topic,
                                style=visual_style,
                                director_brief=director_brief,
                            )
                            os.makedirs(episode_dir, exist_ok=True)
                            with open(visual_plan_path, "w", encoding="utf-8") as f:
                                json.dump(visual_plan.model_dump(), f, ensure_ascii=False, indent=2)
                        else:
                            with open(visual_plan_path, "r", encoding="utf-8") as f:
                                visual_plan = EpisodeVisualPlan(**json.load(f))
                        
                        # Generate media
                        media_result = await self._generate_episode_video(
                            episode=episode,
                            visual_plan=visual_plan,
                            topic=topic,
                            episode_dir=episode_dir,
                            generate_videos=generate_videos,
                        )
                        
                        # Save continuity state after episode (for next episode)
                        self.continuity_memory.save_series_state()
                        
                        # Mark episode as completed
                        output_files = [media_result.get("final_video_path")] if media_result.get("final_video_path") else []
                        self.checkpoint.complete_episode(episode.episode_number, output_files=output_files)
                        
                        return media_result
                    except Exception as e:
                        self.logger.error(f"Failed episode {episode.episode_number}: {e}")
                        self.checkpoint.fail_episode(episode.episode_number, str(e))
                        return {"episode_number": episode.episode_number, "error": str(e)}

            # Process episodes in parallel
            tasks = [process_episode(ep) for ep in episodes_to_generate]
            episode_media = await asyncio.gather(*tasks)
        else:
            self.logger.info("Skipping video generation (no generators configured or disabled)")

        # MEGA SCALE: Final Series Assembly
        final_series_video_path = None
        if generate_videos and episode_media:
            full_video_paths = [em["final_video_path"] for em in episode_media if em.get("final_video_path")]
            if len(full_video_paths) > 1:
                self.logger.info(f"🎬 Stitching {len(full_video_paths)} episodes into final 300-min series...")
                final_series_video_path = os.path.join(self.working_dir, "full_learning_series.mp4")
                try:
                    ffmpeg_concat_videos(full_video_paths, final_series_video_path)
                    
                    # Generate and add audio if video doesn't have audio
                    from moviepy import VideoFileClip
                    from utils.pipeline.audio_helper import ensure_video_has_audio
                    
                    # Collect audio descriptions from all episodes
                    audio_descriptions = []
                    if hasattr(self, 'series_plan') and self.series_plan and hasattr(self.series_plan, 'episodes'):
                        for ep in self.series_plan.episodes:
                            if hasattr(ep, 'title') and ep.title:
                                audio_descriptions.append(ep.title[:200])
                    
                    await ensure_video_has_audio(
                        video_path=final_series_video_path,
                        audio_descriptions=audio_descriptions if audio_descriptions else None,
                        working_dir=self.working_dir,
                        force_regenerate=self.force_regenerate,
                    )
                    
                    self.logger.info(f"✅ MEGA-SERIES COMPLETE: {final_series_video_path}")
                except Exception as e:
                    self.logger.error(f"Failed to stitch mega-series: {e}")

        # Cinematographer/picturization: EpisodeVisualPlan, segment types, visual_description, segment images/videos
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="learning_series",
            rationale=(
                "Picturization is driven by EpisodeVisualPlan per episode: segment types (hook, teach, show, "
                "practice, recap, preview) each have visual_description, visual_type, and on_screen_text. "
                "Images are generated from segment.visual_description with character and branding prompts; "
                "videos use the same cues plus first-frame reference. Director brief and the visual planner "
                "prompts (camera, lighting, atmosphere) shape the educational broadcast look. S3 "
                "character compositing and centered watermark apply in post for consistency."
            ),
            inputs={
                "visual_style": visual_style,
                "director_brief": director_brief.to_context_block()[:200] if director_brief else None,
                "featured_character": self.featured_character.identifier_in_scene if self.featured_character else None,
                "app_name": self.app_name,
            },
            outputs={
                "episode_XX/visual_plan.json": "Per-episode visual plan with segments.",
                "episode_XX/segment_*_*.png": "Segment images.",
                "episode_XX/segment_*_*.mp4": "Segment videos; concatenated to episode_*_full.mp4.",
            },
        )

        # Step 3: Generate monetization plan
        self.logger.info("💰 Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_educational(
            topic=curriculum.course_title,
            description=curriculum.course_description,
            audience=audience or "General learners",
            duration_minutes=curriculum.total_duration_minutes,
            is_series=True,
            num_episodes=num_episodes,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # Step 4: Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        if final_series_video_path and curriculum.total_duration_minutes >= 2:
            self.logger.info("Extracting viral clips for social media...")
            script_full_text = json.dumps(curriculum.model_dump(), ensure_ascii=False)
            viral_shorts = await extract_viral_shorts(
                chat_model=self.chat_model,
                working_dir=self.working_dir,
                final_video_path=final_series_video_path,
                script_content=script_full_text,
                total_duration_seconds=curriculum.total_duration_minutes * 60,
                content_type="learning_series"
            )

        # Build final output payload
        payload = {
            "run_id": self.run_id,
            "topic": topic,
            "num_episodes": num_episodes,
            "episode_duration_minutes": episode_duration_minutes,
            "audience": audience,
            "skill_level": skill_level,
            "visual_style": visual_style,
            "trendy": trendy,
            "generate_images": generate_images,
            "generate_videos": generate_videos,
            "viral_shorts": viral_shorts,
            # S3 Entity Integration
            "brand_id": brand_id,
            "game_id": game_id,
            "app_name": self.app_name,
            "featured_character": self.featured_character.identifier_in_scene if self.featured_character else None,
            "characters": [c.identifier_in_scene for c in self.characters] if self.characters else [],
            # Content
            "curriculum": curriculum.model_dump(),
            "episode_media": episode_media,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # Step 5: Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=json.dumps(curriculum.model_dump(), ensure_ascii=False),
                storyboard=episode_media,
                video_metadata=payload
            )
            payload["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Mark run as completed
        self.checkpoint.mark_completed()

        # Sync all assets and metadata to S3 memory (including checkpoint and continuity state)
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])
        
        print(f"\n✅ Learning series generation complete!")
        print(f"   Output: {output_json_path}")
        if episode_media:
            videos_generated = sum(1 for em in episode_media if em.get("final_video_path"))
            print(f"   Videos generated: {videos_generated}/{len(episodes_to_generate)} episodes")

        return payload
