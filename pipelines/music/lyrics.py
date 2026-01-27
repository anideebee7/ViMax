"""
Idea to Lyrics Pipeline

Generates song lyrics from an idea with trend analysis
and monetization recommendations.
"""
import json
import logging
import os
from typing import Optional, Dict, Any, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.audio.lyricist import Lyricist, LyricsDraft
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.reasoning import write_phase1_reasoning, write_song_reasoning
from utils.pipeline.run_memory import RunMemory
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from configs.constants.content_constants import is_kids_audience


class LyricsPipeline:
    """Pipeline to generate song lyrics from an idea."""

    def __init__(
        self,
        chat_model,
        working_dir: str = ".working_dir/lyrics",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="lyrics",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.lyricist = Lyricist(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="lyrics", run_id=self.run_id, local_dir=self.working_dir)

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

        # Initialize trend analyzer if configured
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
        idea: Optional[str] = None,
        user_requirement: Optional[str] = None,
        style: str = "pop",
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        audience: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand"] = "creativity",
        brand_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate lyrics from an idea.

        Args:
            idea: The song idea or theme (optional if auto_ideate=True)
            user_requirement: Additional requirements for the lyrics (optional if auto_ideate=True)
            style: Style description (e.g., "upbeat pop", "melancholic ballad")
            genre: Optional genre specification
            mood: Optional mood specification
            audience: Target audience (e.g., "kids", "teens", "adults")
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate song idea
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand hint for brand-mode ideation

        Returns:
            Dictionary with lyrics, metadata, and monetization plan
        """
        lyrics_path = os.path.join(self.working_dir, "lyrics.txt")
        output_json_path = os.path.join(self.working_dir, "lyrics_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends for music...")
            trend_context = await self.trend_analyzer.fetch_trends(category="music")
            trend_context_block = trend_context.to_context_block()
            # Save trend data
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating song in {ideation_mode} mode...")
            
            # Use IdeationEngine
            ideation_result = await self.ideation_engine.ideate(
                content_type="song",
                mode=ideation_mode,
                audience=audience,
                trend_context=trend_context
            )
            
            idea = ideation_result.idea
            user_requirement = ideation_result.to_prompt()
            audience = audience or ideation_result.target_audience
            # genre = genre or ideation_result.genre # Remove invalid attribute
            style = style or ideation_result.tone or "pop"
            
            # Save ideation result
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_result.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated song idea: {ideation_result.title}")

        if not idea:
            raise ValueError("Either provide an 'idea' or set 'auto_ideate=True'")

        # Enhance user requirement with trend context
        effective_user_requirement = user_requirement or ""
        if genre:
            effective_user_requirement = f"Genre: {genre}\n{effective_user_requirement}"
        if mood:
            effective_user_requirement = f"Mood: {mood}\n{effective_user_requirement}"
        if trend_context_block:
            effective_user_requirement = f"{effective_user_requirement}\n\n{trend_context_block}"

        # DETECT KIDS AUDIENCE
        if is_kids_audience(audience):
            effective_user_requirement = f"KIDS SONG: Magical, simple, repetitive, and playful.\n{effective_user_requirement}"
            style = f"upbeat kids music, {style}"
            print(f"👦 Targeting kids audience - applying playful style.")

        # Generate lyrics
        self.logger.info("Generating lyrics...")
        
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

        # Save lyrics text
        with open(lyrics_path, "w", encoding="utf-8") as f:
            f.write(lyrics_draft.lyrics)

        # Phase 1 reasoning: rationale behind the lyrics
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="lyrics",
            phase_label="Phase 1: Lyrics",
            content_type="lyrics",
            rationale=(
                "The lyrics are generated from the idea, user_requirement, style, genre, and mood. "
                "The Lyricist shapes structure (verses, chorus, bridge), imagery, and rhyme to fit the "
                "style and audience. Trend context, when enabled, can influence themes and phrasing. "
                "The rationale is to produce lyrics that are coherent, on-brief, and suitable for "
                "the intended genre and mood."
            ),
            inputs={
                "idea": idea[:200] + "…" if idea and len(idea) > 200 else idea,
                "user_requirement": (user_requirement or "")[:200],
                "style": style,
                "genre": genre,
                "mood": mood,
                "audience": audience,
                "trendy": trendy,
            },
            outputs={
                "lyrics.txt": "Plain lyrics text.",
                "lyrics_output.json": "Full payload including lyrics metadata (title, genre, mood, etc.).",
            },
        )

        # Song reasoning: lyrics only (theme, structure, rhyme, audience)
        write_song_reasoning(
            working_dir=self.working_dir,
            pipeline_name="lyrics",
            rationale=(
                "Lyrics rationale: theme and structure (verses, chorus, bridge) follow the idea and "
                "user_requirement. Lyricist chooses rhyme, imagery, and phrasing to fit style, genre, "
                "and mood. Audience (e.g. kids, teens) influences vocabulary and content. No composition "
                "or music direction in this pipeline—lyrics only, for use in song or external setting."
            ),
            inputs={"idea": (idea or "")[:150], "style": style, "genre": genre, "mood": mood, "audience": audience},
            outputs={"lyrics.txt": "Plain lyrics.", "lyrics_output.json": "Lyrics and metadata."},
        )

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise(
            content_type="Song Lyrics / Songwriting",
            content_summary=f"Title: {lyrics_draft.title}\nGenre: {lyrics_draft.genre or genre or 'Pop'}\nMood: {lyrics_draft.mood or mood or 'Uplifting'}\n\nLyrics preview:\n{lyrics_draft.lyrics[:300]}...",
            audience=audience or "General",
            duration=None,
            genre=lyrics_draft.genre or genre,
            additional_context=trend_context_block if trend_context_block else None,
        )

        # Build output payload
        payload = {
            "run_id": self.run_id,
            "idea": idea,
            "user_requirement": user_requirement,
            "style": style,
            "genre": lyrics_draft.genre or genre,
            "mood": lyrics_draft.mood or mood,
            "audience": audience,
            "trendy": trendy,
            "lyrics": lyrics_draft.model_dump(),
            "lyrics_path": lyrics_path,
            "monetization_plan": monetization_plan.model_dump(),
        }

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3()

        return payload
