"""TV Series Pipeline

Generates narrative episodic content with series arcs, characters, and scene-by-scene generation.
Categorized under pipelines/series/ for structural symmetry.
"""
import json
import logging
import os
import asyncio
import shutil
from typing import Optional, Dict, Any, List, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents. creative.writing import TVScreenwriter, TVSeriesScript
from agents.directors.film import TVSeriesDirector
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from agents.producers.analysis import CharacterExtractor
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.viral_extractor import extract_viral_shorts
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.series_bible import SeriesBible
from utils.pipeline.run_memory import RunMemory
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression
from pipelines.base.script import Script2VideoPipeline
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene
from interfaces.content.director_brief import DirectorBrief


class TVSeriesPipeline:
    """Pipeline to generate narrative TV series content."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/series/tv_series",
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
            pipeline_name="tv_series",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.tv_screenwriter = TVScreenwriter(chat_model=self.chat_model) # This is a specialized agent
        self.tv_series_director = TVSeriesDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(chat_model=self.chat_model)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        # Initialize voice memory for series-level voice consistency
        from utils.pipeline.voice_memory import VoiceMemory
        self.voice_memory = VoiceMemory(working_dir=self.working_dir, series_id=self.run_id)
        self.audio_planner = AudioPlanner(
            chat_model=self.chat_model,
            pipeline_kind="tv_series",
            working_dir=self.working_dir,
            voice_memory=self.voice_memory,
        )
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="tv_series", run_id=self.run_id, local_dir=self.working_dir)

    @classmethod
    def init_from_config(cls, config_path: str):
        """Initialize pipeline from YAML config file."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))

        def _resolve_env(value):
            if not isinstance(value, str): return value
            if value.startswith("${") and value.endswith("}"): return os.getenv(value[2:-1], "")
            if value.startswith("ENV:"): return os.getenv(value[4:], "")
            return value

        def _resolve_path(path_value: Optional[str]) -> Optional[str]:
            if not path_value: return None
            return path_value if os.path.isabs(path_value) else os.path.join(base_dir, path_value)

        chat_model_args = config["chat_model"]["init_args"]
        chat_model_args = {k: _resolve_env(v) for k, v in chat_model_args.items()}
        chat_model = init_chat_model(**chat_model_args)

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=_resolve_path(config.get("working_dir", ".working_dir/series/tv_series")),
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
        )

    async def __call__(
        self,
        premise: Optional[str] = None,
        genre: str = "drama",
        num_episodes: int = 5,
        episode_duration_minutes: int = 30,
        style: str = "cinematic",
        audience: Optional[str] = None,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand"] = "creativity",
        brand_hint: Optional[str] = None,
        max_episodes_to_generate: Optional[int] = 1,
    ) -> Dict[str, Any]:
        """Generate narrative TV series content."""
        
        # 0. Load Series Bible
        bible = SeriesBible.load(self.working_dir, series_title=premise or "TV Series")
        
        # 1. Trends
        trend_context: Optional[TrendContext] = None
        if trendy and self.trend_analyzer:
            trend_context = await self.trend_analyzer.fetch_trends(category="entertainment")

        # 2. Ideation
        if auto_ideate:
            # Simplified ideation call
            ideation_result = await self.ideation_engine.ideate(
                content_type="tv_series",
                mode=ideation_mode,
                audience=audience or "general viewers",
                trend_context=trend_context
            )
            premise = ideation_result.idea
            audience = audience or ideation_result.target_audience

        if not premise:
            raise ValueError("Premise is required for TV series pipeline.")

        # 3. Director Brief
        director_brief = await self.tv_series_director.direct(
            premise=premise,
            genre=genre,
            num_episodes=num_episodes,
            episode_duration_minutes=episode_duration_minutes,
            audience=audience,
            visual_style=style,
            additional_context=trend_context.to_context_block() if trend_context else None
        )

        # 4. Series Script
        script = await self.tv_screenwriter.write_series_script(
            premise=premise,
            genre=genre,
            audience=audience,
            num_episodes=num_episodes,
            episode_duration_minutes=episode_duration_minutes,
            style=style,
            additional_context=director_brief.to_context_block()
        )

        # 5. Extract Characters for visual consistency
        # Concatenate script parts for extraction
        all_scenes_text = "\n".join([s.action for ep in script.episodes for s in ep.scenes])
        characters = await self.character_extractor.extract_characters(all_scenes_text)

        # Load series-level continuity state (cross-episode persistence)
        self.continuity_memory.load_series_state()
        
        # 6. Process Episodes (Visual generation)
        episode_outputs = []
        ep_limit = max_episodes_to_generate or len(script.episodes)
        
        for i, episode in enumerate(script.episodes[:ep_limit]):
            # Load continuity state at start of episode
            self.continuity_memory.load_series_state()
            
            ep_dir = os.path.join(self.working_dir, f"episode_{episode.episode_number:02d}")
            os.makedirs(ep_dir, exist_ok=True)
            
            # Use Script2Video for each episode
            s2v = Script2VideoPipeline(
                chat_model=self.chat_model,
                image_generator=self.image_generator,
                video_generator=self.video_generator,
                working_dir=ep_dir,
                use_run_id=False,
                pipeline_kind="tv_series"
            )
            
            # Share continuity memory with Script2VideoPipeline for cross-episode consistency
            if hasattr(s2v, 'continuity_memory'):
                s2v.continuity_memory = self.continuity_memory
            
            # Sync voice memory from series for cross-episode voice consistency
            if hasattr(s2v, 'voice_memory') and hasattr(self, 'voice_memory'):
                s2v.voice_memory.sync_from_series(self.working_dir)
                # Also share the voice_memory instance reference
                s2v.voice_memory = self.voice_memory
            
            # Enrich user requirement with bible context
            bible_context = f"SERIES CONTEXT:\nCharacters: {json.dumps({k: v.model_dump() for k, v in bible.characters.items()}, indent=2)}\nProps: {json.dumps({k: v.model_dump() for k, v in bible.props.items()}, indent=2)}\nWorld State: {bible.world_state.model_dump_json()}"
            ep_requirement = f"{director_brief.to_context_block()}\n\n{bible_context}"
            
            # Combine scenes into a single script string for S2V
            ep_script_text = "\n\n".join([f"SCENE {s.scene_number}: {s.title}\n{s.action}\nDialogue: {s.dialogue}" for s in episode.scenes])
            
            ep_result = await s2v(
                script=ep_script_text,
                user_requirement=ep_requirement,
                style=style,
                characters=characters,
                audience=audience
            )
            
            # Load and aggregate audio plan from Script2VideoPipeline for series-level continuity
            scene_audio_plan_path = os.path.join(ep_dir, "audio_plan.json")
            if os.path.exists(scene_audio_plan_path):
                scene_audio_plan = self.audio_planner.load_audio_plan(scene_audio_plan_path)
                if scene_audio_plan:
                    # Store for series-level audio planning continuity
                    series_audio_plan_path = os.path.join(self.working_dir, f"episode_{episode.episode_number:02d}_audio_plan.json")
                    self.audio_planner.save_audio_plan(scene_audio_plan, series_audio_plan_path)
            
            # Save continuity state after episode
            self.continuity_memory.save_series_state()
            
            # Sync voice memory to series for cross-episode consistency
            if hasattr(s2v, 'voice_memory') and hasattr(self, 'voice_memory'):
                s2v.voice_memory.sync_to_series(self.working_dir)
            
            episode_outputs.append({
                "episode_number": episode.episode_number,
                "title": episode.title,
                "video_path": ep_result.get("video_path")
            })

        # 7. Monetization
        monetization_plan = await self.monetization_advisor.advise_for_video(
            title=script.title,
            description=script.synopsis,
            audience=audience or "General",
            duration_seconds=episode_duration_minutes * 60,
            genre=genre,
            is_shorts=False
        )

        # 8. Viral Shorts Extraction (if content > 2 mins)
        viral_shorts = []
        # Check first episode for viral potential
        if episode_outputs and episode_duration_minutes >= 2:
            first_ep_path = episode_outputs[0].get("video_path")
            if first_ep_path:
                self.logger.info("Extracting viral clips for social media...")
                script_full_text = json.dumps(script.model_dump(), ensure_ascii=False)
                viral_shorts = await extract_viral_shorts(
                    chat_model=self.chat_model,
                    working_dir=self.working_dir,
                    final_video_path=first_ep_path,
                    script_content=script_full_text,
                    total_duration_seconds=episode_duration_minutes * 60,
                    content_type="tv_series"
                )

        # 9. Update Series Bible with new knowledge
        for char in characters:
            bible.update_character(char.identifier_in_scene, {"key_memories": [f"Participated in series: {script.title}"]})
        bible.record_event(f"Generated series '{script.title}' with {len(episode_outputs)} episodes.")
        bible.save(self.working_dir)

        output = {
            "run_id": self.run_id,
            "title": script.title,
            "premise": premise,
            "synopsis": script.synopsis,
            "episodes": episode_outputs,
            "viral_shorts": viral_shorts,
            "monetization_plan": monetization_plan.model_dump(),
            "working_dir": self.working_dir
        }
        
        with open(os.path.join(self.working_dir, "tv_series_output.json"), "w") as f:
            json.dump(output, f, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])
            
        return output
