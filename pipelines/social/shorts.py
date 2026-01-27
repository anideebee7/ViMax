"""Viral Shorts/Reels Pipeline: focused on maximum engagement and attention capture."""

import json
import logging
import os
from typing import Optional, Dict, Any, List, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing.viral import ViralScreenwriter
from agents.directors.social.viral import ViralSocialDirector
from agents.planners.strategy import IdeationEngine
from pipelines.base.idea import VideoPipeline
from utils.core.run_id import generate_run_id, write_run_metadata, extract_run_id_from_path, initialize_run_directory
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression
from interfaces.entities.ideation import IdeationResult
from utils.pipeline.trend_analyzer import TrendAnalyzer

class ViralShortsPipeline:
    """Specialized pipeline for generating viral-optimized short-form videos."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/social/viral_shorts",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.trend_analyzer = trend_analyzer
        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="viral_shorts",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.screenwriter = ViralScreenwriter(chat_model=self.chat_model)
        self.director = ViralSocialDirector(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        # Pass run_id to nested VideoPipeline so it doesn't create a new one
        # Use use_run_id=False since we're already in a run_id-specific directory
        self.video_pipeline = VideoPipeline(
            chat_model=self.chat_model,
            image_generator=self.image_generator,
            video_generator=self.video_generator,
            working_dir=os.path.join(self.working_dir, "production"),
            shorts_mode={"enabled": True, "format": "youtube_shorts"},
            pipeline_kind="viral_shorts",
            run_id=None,  # Don't create new run_id for nested pipeline
            use_run_id=False,  # Use the working_dir directly without run_id subfolder
        )
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def init_from_config(
        cls, 
        config_path: str,
        run_id: Optional[str] = None,
        working_dir: Optional[str] = None,
    ) -> "ViralShortsPipeline":
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        # ... (Config resolution logic similar to other pipelines) ...
        # (Simplified for brevity in this initial implementation)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))
        
        def _resolve_env(v):
            if not isinstance(v, str): return v
            if v.startswith("${") and v.endswith("}"): return os.getenv(v[2:-1], "")
            if v.startswith("ENV:"): return os.getenv(v[4:], "")
            return v

        chat_model_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
        chat_model = init_chat_model(**chat_model_args)

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        from utils.pipeline.generator_factory import create_generators_from_config
        image_generator, video_generator = create_generators_from_config(config)

        # Trend analyzer (optional)
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        # Use provided working_dir, otherwise use config default
        # If working_dir is provided and is absolute, use it as-is (resume scenario)
        # Otherwise, use config default and let __init__ handle run_id subdirectory
        resolved_working_dir = working_dir
        if not resolved_working_dir:
            resolved_working_dir = config.get("working_dir", ".working_dir/social/viral_shorts")

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=resolved_working_dir,
            trend_analyzer=trend_analyzer,
            run_id=run_id,  # Pass run_id to __init__ - it will use it if provided
        )

    async def __call__(
        self,
        idea: Optional[str] = None,
        platform: Literal["YouTube Shorts", "Instagram Reels", "TikTok"] = "YouTube Shorts",
        audience: str = "Gen Z / Alpha",
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand"] = "viral",
        generate_video: bool = True,
    ) -> Dict[str, Any]:
        """Run the viral shorts pipeline."""
        
        # 1. Fetch trends if needed
        trend_context = None
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info(f"Fetching trends for {platform} content...")
            trend_context = await self.trend_analyzer.fetch_trends(category="entertainment")

        # 2. Auto-ideation
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating viral short in {ideation_mode} mode...")
            
            # Use IdeationEngine
            ideation_result = await self.ideation_engine.ideate(
                content_type="shorts",
                mode=ideation_mode,
                audience=audience,
                trend_context=trend_context
            )
            
            idea = ideation_result.idea
            audience = audience or ideation_result.target_audience
            
            # Save ideation result
            with open(os.path.join(self.working_dir, "ideation.json"), "w") as f:
                json.dump(ideation_result.model_dump(), f, indent=2)
            
            print(f"💡 Auto-generated viral idea: {ideation_result.title}")

        if not idea:
            raise ValueError("Either provide an 'idea' or set 'auto_ideate=True'")

        # 3. Resolve S3 context if provided
        entity_context = ""
        if brand_id or game_id:
            texts = []
            if brand_id: texts.append(f"@brand:{brand_id}")
            if game_id: texts.append(f"@game:{game_id}")
            resolution = resolve_s3_entities(texts=texts, working_dir=self.working_dir)
            entity_context = f"Context from S3: {resolution.get('brand_data', {}).get('description', '')}"

        # 4. Viral Screenwriting
        self.logger.info("Writing viral-optimized script...")
        viral_script = await self.screenwriter.write_viral_short(
            idea=idea,
            user_requirement=f"Optimize for {platform}. {entity_context}"
        )
        
        with open(os.path.join(self.working_dir, "viral_script.json"), "w") as f:
            json.dump(viral_script.model_dump(), f, indent=2)

        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="viral_shorts",
            phase_label="Phase 1: Viral Scripting",
            content_type="viral_script",
            rationale=f"Script focuses on immediate attention capture ({viral_script.hook_verbal}) and high retention through {len(viral_script.pattern_interrupts)} pattern interrupts.",
            inputs={"idea": idea, "platform": platform},
            outputs={"viral_script.json": "Detailed viral structure including loop and engagement bait."}
        )

        # 5. Viral Direction
        self.logger.info("Creating viral visual brief...")
        director_brief = await self.director.direct_viral_short(
            idea=f"{viral_script.title}: {viral_script.hook_verbal}",
            platform=platform,
            audience=audience
        )
        
        with open(os.path.join(self.working_dir, "director_brief.json"), "w") as f:
            json.dump(director_brief.model_dump(), f, indent=2)

        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="viral_shorts",
            director_name="ViralSocialDirector",
            rationale=f"Visuals focus on {director_brief.visual_style} to ensure high production value aesthetic compatible with {platform} algorithms.",
            inputs={"script_title": viral_script.title},
            outputs={"director_brief.json": "Visual hooks, framing, and pacing instructions."}
        )

        # 6. Video Production (bridging to Idea2Video)
        result = {"script": viral_script.model_dump(), "director": director_brief.model_dump()}
        
        if generate_video:
            self.logger.info("Initiating video production...")
            # Prepare detailed requirement for production
            production_idea = f"{viral_script.hook_visual}. {viral_script.hook_verbal}. {' '.join(viral_script.beats)}"
            production_requirement = f"""
            VISUAL STYLE: {director_brief.visual_style}
            PACING: Rapid visual changes every 1.5s.
            OVERLAYS: Include kinetic text for {', '.join(viral_script.on_screen_text) if hasattr(viral_script, 'on_screen_text') else ''}
            LOOP: {viral_script.loop_strategy}
            """
            
            # Convert brand_id/game_id to brand_hint for VideoPipeline
            brand_hint = None
            if brand_id:
                brand_hint = f"@brand:{brand_id}"
            elif game_id:
                brand_hint = f"@game:{game_id}"
            
            video_output = await self.video_pipeline(
                idea=production_idea,
                user_requirement=production_requirement,
                style=director_brief.visual_style,
                brand_hint=brand_hint
            )
            result["video_production"] = video_output

        return result
