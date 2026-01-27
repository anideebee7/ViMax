"""
Idea to Short Movie Pipeline

Generates short film scripts (5-20 minutes) using film-mode screenwriting
with monetization recommendations.
"""
import json
import logging
import os
from typing import Optional, Dict, Any, List, Literal

import yaml

from configs.constants.content_constants import CONTENT_FORMAT_LIVE_ACTION, CONTENT_FORMAT_ANIMATED
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing import Screenwriter
from agents.producers.analysis import CharacterExtractor
from agents.producers.business import MonetizationAdvisor
from agents.directors.film import ShortMovieDirector
from agents.planners.strategy import IdeationEngine
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from utils.pipeline.entity_resolver import resolve_s3_entities
from configs.constants.pipeline_profiles import SHORT_MOVIE_PROFILE


class ShortMoviePipeline:
    """Pipeline to generate short film scripts."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/short_movie",
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
            pipeline_name="short_movie",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        # Film mode configuration for screenwriter
        film_mode = {
            "enabled": True,
            "format": "short_film",
            "max_scenes": 15,
            "target_duration_minutes": 15,
        }
        self.screenwriter = Screenwriter(chat_model=self.chat_model, shorts_mode=film_mode, pipeline_kind="short_film")
        self.short_movie_director = ShortMovieDirector(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="short_movie", run_id=self.run_id, local_dir=self.working_dir)

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

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            working_dir=_resolve_path(config["working_dir"]) or config["working_dir"],
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
        )

    async def __call__(
        self,
        premise: Optional[str] = None,
        genre: str = "drama",
        target_duration_minutes: int = 15,
        audience: Optional[str] = None,
        style: str = "cinematic",
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        brand_hint: Optional[str] = None,
        content_format: Literal["live_action", "animated"] = CONTENT_FORMAT_LIVE_ACTION,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a short film script from a premise.

        Args:
            premise: Film premise/logline (optional if auto_ideate=True)
            genre: Film genre (drama, comedy, thriller, action, sci-fi, etc.)
            target_duration_minutes: Target duration (5-20 minutes)
            audience: Target audience (G, PG, teens, adults, family, etc.)
            style: Visual/narrative style
            trendy: Whether to incorporate trending themes
            auto_ideate: If True, automatically generate film premise
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
            content_format: 'live_action' or 'animated'
            brand_id: S3 brand ID for context
            game_id: S3 game ID for context

        Returns:
            Dictionary with story, script, characters, and monetization plan
        """
        output_json_path = os.path.join(self.working_dir, "shortmovie_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Initialize context
        brand_ctx: Optional[BrandContext] = None
        game_ctx: Optional[GameContext] = None
        
        # Resolve S3 entities (brand, game)
        if brand_id or game_id or (auto_ideate and brand_hint):
            texts = []
            if brand_id: texts.append(f"@brand:{brand_id}")
            elif brand_hint: texts.append(brand_hint)
            if game_id: texts.append(f"@game:{game_id}")
            
            if texts:
                resolution = resolve_s3_entities(
                    texts=texts,
                    brand_hint=brand_id or brand_hint,
                    game_hint=game_id,
                    working_dir=self.working_dir,
                )
                brand_ctx = resolution.get("brand_context")
                game_ctx = resolution.get("game_context")

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
            self.logger.info(f"🧠 Auto-ideating short movie in {ideation_mode} mode...")
            
            if ideation_mode == "brand" and (brand_ctx or game_ctx):
                ideation_result = await self.ideation_engine.ideate_for_brand(
                    content_type="movie", # Use movie for short films too
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                    trend_context=trend_context,
                )
            
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(
                    content_type="movie",
                    mode=ideation_mode,
                    audience=audience or "General",
                    trend_context=trend_context,
                    brand_context=brand_ctx,
                    game_context=game_ctx,
                )
            
            premise = ideation_result.idea
            audience = audience or ideation_result.target_audience
            genre = genre or ideation_result.tone or "drama"
            
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_result.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated short movie premise: {ideation_result.title}")

        if not premise:
            raise ValueError("Either provide a 'premise' or set 'auto_ideate=True'")

        format_note = (
            "Content format: ANIMATED. Write for animation: stylized, expressive; imaginative visuals."
            if content_format == CONTENT_FORMAT_ANIMATED
            else "Content format: live-action."
        )
        # Build user requirement
        user_requirement = f"""
Genre: {genre}
Style: {style}
Target audience: {audience or 'General'}
Target duration: {target_duration_minutes} minutes
{format_note}
Format: Short film with clear three-act structure
"""
        if trend_context_block:
            user_requirement = f"{user_requirement}\n\n{trend_context_block}"

        # Director: creative brief for screenwriter
        director_brief = await self.short_movie_director.direct(
            premise=premise,
            genre=genre,
            target_duration_minutes=target_duration_minutes,
            style=style,
            audience=audience,
            additional_context=f"{format_note}\n{trend_context_block or ''}".strip() or None,
        )
        user_requirement = f"{user_requirement}\n\n{director_brief.to_context_block()}"

        # Director reasoning: ShortMovieDirector creative brief
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="short_movie",
            director_name="ShortMovieDirector",
            rationale=(
                "ShortMovieDirector sets the creative brief for the short film: tone, pacing, three-act "
                "structure, and visual style. The brief aligns premise, genre, target_duration, format "
                "(live-action/animated), and audience so the Screenwriter delivers a coherent short. "
                "Trends can influence thematic choices when enabled."
            ),
            inputs={
                "premise": premise[:150],
                "genre": genre,
                "target_duration_minutes": target_duration_minutes,
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
            f.write(f"Premise: {premise}\nRequirement: {user_requirement}")

        story = await self.screenwriter.develop_story(idea=premise, user_requirement=user_requirement)
        with open(story_path, "w", encoding="utf-8") as f:
            f.write(story)

        # Extract characters
        self.logger.info("Extracting characters...")
        characters = await self.character_extractor.extract_characters(story)
        characters_path = os.path.join(self.working_dir, "characters.json")
        with open(characters_path, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)

        # Write script
        self.logger.info("Writing script...")
        
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "script_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(f"Story: {story[:1000]}\nRequirement: {user_requirement}")

        script = await self.screenwriter.write_script_based_on_story(
            story=story,
            user_requirement=user_requirement,
        )
        script_path = os.path.join(self.working_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # Phase 1 reasoning: rationale behind the story and script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="short_movie",
            phase_label="Phase 1: Story and script",
            content_type="script",
            rationale=(
                "The short film script uses a clear three-act structure and film-mode screenwriting (not shorts). "
                "ShortMovieDirector sets tone and pacing; Screenwriter develops the story from the premise "
                "and writes scene-by-scene. CharacterExtractor pulls characters from the story. "
                "Target duration, genre, style, format (live-action/animated), and trends shape the narrative."
            ),
            inputs={
                "premise": premise[:200] + "…" if len(premise) > 200 else premise,
                "genre": genre,
                "target_duration_minutes": target_duration_minutes,
                "style": style,
                "audience": audience,
                "content_format": content_format,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={
                "story.txt": "Developed story from premise.",
                "characters.json": "Extracted characters from story.",
                "script.json": "Scene-by-scene short film script.",
            },
        )

        # Cinematographer/picturization: script-only; director's visual_style guides future production
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="short_movie",
            rationale=(
                "This pipeline produces script only; no in-pipeline storyboard or video. The director's "
                "visual_style and three-act structure define how the narrative would be picturized in a "
                "downstream pipeline (e.g. script2video or short_video). Genre and format "
                "shape shot design when produced."
            ),
            inputs={"style": style, "content_format": content_format},
            outputs={"story.txt": "Story.", "script.json": "Scene-by-scene short film script for future picturization.", "characters.json": "Character list."},
        )

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=f"Short Film: {premise[:50]}...",
            description=story[:500],
            audience=audience or "General",
            duration_seconds=target_duration_minutes * 60,
            genre=genre,
            is_shorts=False,
            trend_context=trend_context_block if trend_context_block else None,
        )

        payload = {
            "run_id": self.run_id,
            "premise": premise,
            "genre": genre,
            "target_duration_minutes": target_duration_minutes,
            "content_format": content_format,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "story": story,
            "characters": [c.model_dump() for c in characters],
            "script": script,
            "monetization_plan": monetization_plan.model_dump(),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=story,
                storyboard=script,
                video_metadata=payload
            )
            payload["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3()

        return payload
