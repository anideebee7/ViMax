import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, Literal

import aiohttp
import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.audio.lyricist import Lyricist, LyricsDraft
from agents.creative.audio.composer import SongComposer, SongCompositionPlan
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_image_generator
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_song_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from interfaces.output.image_output import ImageOutput
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from configs.constants.content_constants import is_kids_audience


class SongPipeline:
    def __init__(
        self,
        chat_model,
        audio_generator_primary,
        audio_generator_fallback,
        working_dir: str = ".working_dir/song",
        image_generator: Optional[object] = None,
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        target_duration_seconds: Optional[int] = None,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.audio_generator_primary = audio_generator_primary
        self.audio_generator_fallback = audio_generator_fallback
        self.image_generator = image_generator
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate
        self.target_duration_seconds = target_duration_seconds

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="song",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.lyricist = Lyricist(chat_model=self.chat_model)
        self.song_composer = SongComposer(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="song", run_id=self.run_id, local_dir=self.working_dir)

    @classmethod
    def init_from_config(cls, config_path: str):
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

        chat_model_rpm = config.get("chat_model", {}).get("max_requests_per_minute", None)
        chat_model_rpd = config.get("chat_model", {}).get("max_requests_per_day", None)
        audio_primary_rpm = config.get("audio_generator_primary", {}).get("max_requests_per_minute", None)
        audio_primary_rpd = config.get("audio_generator_primary", {}).get("max_requests_per_day", None)
        audio_fallback_rpm = config.get("audio_generator_fallback", {}).get("max_requests_per_minute", None)
        audio_fallback_rpd = config.get("audio_generator_fallback", {}).get("max_requests_per_day", None)
        image_rpm = config.get("image_generator", {}).get("max_requests_per_minute", None)
        image_rpd = config.get("image_generator", {}).get("max_requests_per_day", None)

        chat_model_rate_limiter = RateLimiter(
            max_requests_per_minute=chat_model_rpm,
            max_requests_per_day=chat_model_rpd
        ) if (chat_model_rpm or chat_model_rpd) else None

        audio_primary_rate_limiter = RateLimiter(
            max_requests_per_minute=audio_primary_rpm,
            max_requests_per_day=audio_primary_rpd
        ) if (audio_primary_rpm or audio_primary_rpd) else None

        audio_fallback_rate_limiter = RateLimiter(
            max_requests_per_minute=audio_fallback_rpm,
            max_requests_per_day=audio_fallback_rpd
        ) if (audio_fallback_rpm or audio_fallback_rpd) else None

        image_rate_limiter = RateLimiter(
            max_requests_per_minute=image_rpm,
            max_requests_per_day=image_rpd
        ) if (image_rpm or image_rpd) else None

        audio_primary_cls_module, audio_primary_cls_name = config["audio_generator_primary"]["class_path"].rsplit(".", 1)
        audio_primary_cls = getattr(importlib.import_module(audio_primary_cls_module), audio_primary_cls_name)
        audio_primary_args = config["audio_generator_primary"]["init_args"]
        audio_primary_args = {k: _resolve_env(v) for k, v in audio_primary_args.items()}
        audio_primary_args["rate_limiter"] = audio_primary_rate_limiter
        audio_generator_primary = audio_primary_cls(**audio_primary_args)

        audio_fallback_cls_module, audio_fallback_cls_name = config["audio_generator_fallback"]["class_path"].rsplit(".", 1)
        audio_fallback_cls = getattr(importlib.import_module(audio_fallback_cls_module), audio_fallback_cls_name)
        audio_fallback_args = config["audio_generator_fallback"]["init_args"]
        audio_fallback_args = {k: _resolve_env(v) for k, v in audio_fallback_args.items()}
        audio_fallback_args["rate_limiter"] = audio_fallback_rate_limiter
        audio_generator_fallback = audio_fallback_cls(**audio_fallback_args)

        # Use unified image generator with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        image_generator = None
        if config.get("image_generator"):
            image_generator = create_image_generator(rate_limiter=image_rate_limiter)

        # Initialize trend analyzer if configured
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            audio_generator_primary=audio_generator_primary,
            audio_generator_fallback=audio_generator_fallback,
            image_generator=image_generator,
            trend_analyzer=trend_analyzer,
            working_dir=_resolve_path(config["working_dir"]) or config["working_dir"],
            force_regenerate=bool(config.get("force_regenerate", False)),
            target_duration_seconds=config.get("target_duration_seconds"),
        )

    async def _download_file(self, url: str, save_path: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024):
                        f.write(chunk)

    async def _generate_cover_image(self, prompt: str, output_path: str) -> Optional[str]:
        if not self.image_generator:
            return None
        
        # Save debug prompt
        debug_dir = os.path.join(self.working_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "cover_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)

        image_output: ImageOutput = await self.image_generator.generate_single_image(prompt=prompt)
        image_output.save(output_path)
        return output_path

    def _build_music_prompt(
        self,
        lyrics: Dict[str, Any],
        composition_plan: Dict[str, Any],
        style: str,
        audience: Optional[str],
        trendy: bool,
    ) -> str:
        tags = ", ".join(lyrics.get("tags", []) or [])
        return (
            f"Title: {lyrics.get('title', '').strip()}\n"
            f"Genre: {lyrics.get('genre') or ''}\n"
            f"Mood: {lyrics.get('mood') or ''}\n"
            f"Instrumentation: {lyrics.get('instrumentation') or ''}\n"
            f"Tempo BPM: {lyrics.get('bpm') or ''}\n"
            f"Audience: {audience or ''}\n"
            f"Trendy: {'yes' if trendy else 'no'}\n"
            f"Style: {style}\n"
            f"Tags: {tags}\n\n"
            f"Lyrics:\n{lyrics.get('lyrics', '').strip()}\n\n"
            f"Composition Plan:\n{json.dumps(composition_plan, ensure_ascii=False)}"
        )

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
    ) -> Dict[str, Any]:
        """
        Run the song pipeline.
        
        Args:
            idea: Song idea/concept (optional if auto_ideate=True)
            user_requirement: Additional requirements (optional if auto_ideate=True)
            style: Music style
            audience: Target audience
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate the idea
            ideation_mode: Mode for auto-ideation
            brand_hint: Brand name hint for brand-mode ideation
        
        Returns:
            Dictionary containing output metadata
        """
        lyrics_path = os.path.join(self.working_dir, "lyrics.txt")
        song_json_path = os.path.join(self.working_dir, "song.json")
        audio_path = os.path.join(self.working_dir, "audio.mp3")
        cover_path = os.path.join(self.working_dir, "cover.png")

        if os.path.exists(song_json_path) and not self.force_regenerate:
            with open(song_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="music")
            trend_context_block = trend_context.to_context_block()
            # Save trend data
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # Auto-ideation
        ideation_result: Optional[IdeationResult] = None
        brand_ctx: Optional[BrandContext] = None
        game_ctx: Optional[GameContext] = None
        
        if auto_ideate:
            self.logger.info(f"🧠 Auto-ideating song in {ideation_mode} mode...")
            
            # Load brand/game context if brand mode
            if ideation_mode == "brand" and brand_hint:
                resolution = resolve_s3_entities(
                    texts=[brand_hint],
                    brand_hint=brand_hint,
                    working_dir=self.working_dir,
                )
                brand_ctx = resolution.get("brand_context")
                game_ctx = resolution.get("game_context")
                
                if brand_ctx or game_ctx:
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
            
            audience = audience or ideation_result.target_audience
            # genre = genre or ideation_result.genre # Remove invalid attribute
            style = style or ideation_result.tone or "pop"
            
            # Use ideation result
            idea = ideation_result.idea
            user_requirement = ideation_result.to_prompt()
            audience = audience or ideation_result.target_audience
            # genre = genre or ideation_result.genre # Remove invalid attribute
            style = style or ideation_result.tone or "pop"
            
            # Save ideation result
            ideation_output = ideation_result.model_dump()
            if brand_ctx:
                ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx:
                ideation_output["game_context"] = game_ctx.model_dump()
            with open(os.path.join(self.working_dir, "ideation.json"), "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)
            
            print(f"💡 Auto-generated song idea: {ideation_result.title}")
            if brand_ctx:
                print(f"   Brand: {brand_ctx.name}")

        if not idea:
            raise ValueError("Either provide an 'idea' or set 'auto_ideate=True'")

        # Enhance user requirement with trend context
        effective_user_requirement = user_requirement or ""
        if trend_context_block:
            effective_user_requirement = f"{user_requirement}\n\n{trend_context_block}"

        # DETECT KIDS AUDIENCE
        if is_kids_audience(audience):
            effective_user_requirement = f"KIDS SONG: Simple, repetitive, playful, and magical.\n{effective_user_requirement}"
            style = f"upbeat kids music, {style}"
            print(f"👦 Targeting kids audience - applying playful style.")

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
            target_duration_seconds=self.target_duration_seconds,
        )

        with open(lyrics_path, "w", encoding="utf-8") as f:
            f.write(lyrics_draft.lyrics)

        # Phase 1 reasoning: rationale behind the lyrics and composition plan
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song",
            phase_label="Phase 1: Lyrics and composition plan",
            content_type="lyrics",
            rationale=(
                "The lyrics are generated from the idea, user_requirement, style, and audience. Lyricist produces "
                "structure, imagery, and rhyme. SongComposer then creates a composition_plan (sections, key, BPM, "
                "instrumentation) so the music matches the lyrics and style. Trends and brand context (when "
                "auto_ideate with brand mode) can influence theme and tone. The rationale is to have lyrics and "
                "a production-ready plan that align for the audio generator."
            ),
            inputs={
                "idea": (idea or "")[:200],
                "user_requirement": (user_requirement or effective_user_requirement or "")[:200],
                "style": style,
                "audience": audience,
                "trendy": trendy,
                "target_duration_seconds": self.target_duration_seconds,
                "auto_ideate": auto_ideate,
            },
            outputs={
                "lyrics.txt": "Lyrics text.",
                "song.json": "Full payload including lyrics and composition_plan (used for audio generation).",
            },
        )

        # Song reasoning: lyrics, composition, and music direction
        write_song_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song",
            rationale=(
                "Lyrics: theme, structure, rhyme from Lyricist to fit idea, style, and audience. "
                "Composition: SongComposer produces composition_plan (sections, key, BPM, instrumentation, "
                "total_duration) so the music supports the lyrics. Music direction: the combined "
                "lyrics+composition_plan and style drive the audio generator (ElevenLabs or Piapi Suno) "
                "for mood, dynamics, and production. Trends and brand context (when auto_ideate) can "
                "influence theme and tone."
            ),
            inputs={
                "idea": (idea or "")[:150],
                "style": style,
                "audience": audience,
                "composition_plan": "sections, key, BPM, instrumentation, total_duration" if composition_plan else None,
            },
            outputs={
                "lyrics.txt": "Lyrics.",
                "song.json": "Lyrics + composition_plan.",
                "audio.mp3": "Generated audio from lyrics+composition.",
            },
        )

        total_duration = composition_plan.total_duration_seconds
        if self.target_duration_seconds:
            total_duration = self.target_duration_seconds
        music_length_ms = max(3000, int(total_duration * 1000)) if total_duration else None

        music_prompt = self._build_music_prompt(
            lyrics=lyrics_draft.model_dump(),
            composition_plan=composition_plan.model_dump(),
            style=style,
            audience=audience,
            trendy=trendy,
        )

        audio_provider = "elevenlabs"
        try:
            # Build ElevenLabs composition plan if primary is ElevenLabs
            elevenlabs_plan = None
            if hasattr(self.audio_generator_primary, "compose_music"):
                elevenlabs_plan = {
                    "positive_global_styles": [style] if style else [],
                    "sections": [
                        {
                            "section_name": section.name,
                            "lines": section.lines or [],
                            "positive_local_styles": [section.description] if section.description else [],
                            "duration_ms": section.duration_seconds * 1000
                        }
                        for section in composition_plan.sections
                    ]
                }

            await self.audio_generator_primary.compose_music(
                prompt=music_prompt,
                composition_plan=elevenlabs_plan,
                music_length_ms=music_length_ms,
                output_path=audio_path,
            )
        except Exception as exc:
            self.logger.warning("Primary audio generation failed: %s", exc)
            audio_provider = "piapi_suno"
            audio_url = await self.audio_generator_fallback.generate_music(
                prompt=music_prompt,
                lyrics=lyrics_draft.lyrics,
                style=style,
            )
            if not audio_url:
                raise RuntimeError("Fallback music generation failed without audio URL.")
            await self._download_file(audio_url, audio_path)

        cover_prompt = (
            f"Album cover for '{lyrics_draft.title}'. "
            f"Genre: {lyrics_draft.genre or 'modern'}. Mood: {lyrics_draft.mood or 'inspiring'}. "
            f"Style: {style}. Clean, high contrast, professional."
        )
        cover_file = await self._generate_cover_image(cover_prompt, cover_path)

        # Cinematographer/picturization: cover image only (no video in song)
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="song",
            rationale=(
                "This pipeline has no video or storyboard; the only visual is the cover image. The cover "
                "prompt uses title, genre, mood, and style to produce a single 'album cover' image. "
                "Picturization is limited to that one asset for artwork/thumbnail use."
            ),
            inputs={"cover_prompt": cover_prompt[:200], "style": style},
            outputs={"cover.png": "Album cover image."},
        )

        # Generate monetization plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_music(
            title=lyrics_draft.title,
            genre=lyrics_draft.genre or "Pop",
            mood=lyrics_draft.mood or "Uplifting",
            audience=audience or "General",
            duration_seconds=total_duration or 60,
            lyrics_preview=lyrics_draft.lyrics[:300] if lyrics_draft.lyrics else None,
            trend_context=trend_context_block if trend_context_block else None,
        )

        payload = {
            "run_id": self.run_id,
            "idea": idea,
            "user_requirement": user_requirement,
            "style": style,
            "audience": audience,
            "trendy": trendy,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "ideation_result": ideation_result.model_dump() if ideation_result else None,
            "lyrics": lyrics_draft.model_dump(),
            "composition_plan": composition_plan.model_dump(),
            "audio_path": audio_path,
            "cover_path": cover_file,
            "audio_provider": audio_provider,
            "monetization_plan": monetization_plan.model_dump(),
        }

        with open(song_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp3"])

        return payload
