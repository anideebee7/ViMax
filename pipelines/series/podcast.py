"""
Idea to Podcast Series Pipeline

Generates a video podcast series with multiple episodes, 
from a single idea or topic.
"""
import json
import logging
import os
import asyncio
from typing import Optional, Dict, Any, List

import yaml
import importlib
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

from agents.planners.strategy import PodcastPlanner, PodcastSeriesPlan, PodcastEpisodePlan
from agents.directors.audio import PodcastDirector
from agents.creative.writing import PodcastScreenwriter
from agents.producers.visuals import StoryboardArtist
from pipelines.content.podcast import Podcast2VideoPipeline, PodcastConfig
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from configs.constants.pipeline_profiles import PODCAST_PROFILE


class PodcastSeriesPipeline:
    """Pipeline to generate a video podcast series.
    
    Supports resuming from a run_id and processes episodes in parallel.
    """

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/podcast_series",
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
            pipeline_name="podcast_series",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.series_planner = PodcastPlanner(chat_model=self.chat_model)
        self.series_director = PodcastDirector(chat_model=self.chat_model)
        self.screenwriter = PodcastScreenwriter(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="podcast")
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="podcast_series", run_id=self.run_id, local_dir=self.working_dir)

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
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 20,
        audience: Optional[str] = None,
        series_goals: Optional[str] = None,
        trendy: bool = False,
        visual_style: str = "modern professional podcast studio, vibrant and clean",
        max_episodes_to_generate: Optional[int] = None,
        # S3 Entity Integration
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a video podcast series."""
        output_json_path = os.path.join(self.working_dir, "podcastseries_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Step 0: Fetch trends if needed
        trend_context_block = ""
        if trendy and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="podcast")
            trend_context_block = trend_context.to_context_block()

        # Step 1: Director's Brief
        brief_path = os.path.join(self.working_dir, "director_brief.json")
        if os.path.exists(brief_path) and not self.force_regenerate:
            with open(brief_path, "r") as f:
                from interfaces import DirectorBrief
                director_brief = DirectorBrief(**json.load(f))
        else:
            director_brief = await self.series_director.direct(
                topic=topic,
                num_episodes=num_episodes,
                episode_duration_minutes=episode_duration_minutes,
                audience=audience,
                visual_style=visual_style,
                additional_context=trend_context_block,
            )
            with open(brief_path, "w") as f:
                json.dump(director_brief.model_dump(), f, indent=2)

        # Director reasoning
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast_series",
            director_name="PodcastSeriesDirector",
            rationale=(
                "The director sets the tone for the podcast series, focusing on studio aesthetics, "
                "host dynamics, and consistent visual style across all episodes."
            ),
            inputs={
                "topic": topic,
                "audience": audience,
                "visual_style": visual_style,
            },
            outputs={"director_brief.json": "Creative brief for the podcast series."},
        )

        # Step 2: Series Plan
        plan_path = os.path.join(self.working_dir, "series_plan.json")
        if os.path.exists(plan_path) and not self.force_regenerate:
            with open(plan_path, "r") as f:
                series_plan = PodcastSeriesPlan(**json.load(f))
        else:
            series_plan = await self.series_planner.plan_series(
                topic=topic,
                num_episodes=num_episodes,
                episode_duration_minutes=episode_duration_minutes,
                audience=audience or "general listeners",
                series_goals=series_goals,
                additional_context=director_brief.to_context_block(),
            )
            with open(plan_path, "w") as f:
                json.dump(series_plan.model_dump(), f, indent=2)

        # Phase 1 reasoning
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast_series",
            phase_label="Phase 1: Series Planning and Scripting",
            content_type="podcast_series_plan",
            rationale=(
                "The series plan defines the narrative arc and episode structure. "
                "Each episode is planned with specific hooks, key points, and segments."
            ),
            inputs={
                "topic": topic,
                "num_episodes": num_episodes,
                "director_brief": director_brief.to_context_block()[:200],
            },
            outputs={"series_plan.json": "Complete series and episode breakdown."},
        )

        # Load series-level continuity state (cross-episode persistence)
        from utils.pipeline.continuity import ContinuityMemory
        series_continuity = ContinuityMemory(working_dir=self.working_dir)
        series_continuity.load_series_state()
        
        # Step 3: Write Scripts and Generate Videos for each episode
        episodes_dir = os.path.join(self.working_dir, "episodes")
        os.makedirs(episodes_dir, exist_ok=True)
        
        episode_results = []
        episodes_to_process = series_plan.episodes
        if max_episodes_to_generate:
            episodes_to_process = episodes_to_process[:max_episodes_to_generate]

        # Use a semaphore to limit parallel execution
        semaphore = asyncio.Semaphore(2)

        async def process_episode(ep_plan: PodcastEpisodePlan):
            async with semaphore:
                # Load continuity state at start of episode
                series_continuity.load_series_state()
                
                ep_dir = os.path.join(episodes_dir, f"episode_{ep_plan.episode_number:02d}")
                os.makedirs(ep_dir, exist_ok=True)
                
                script_path = os.path.join(ep_dir, "script.txt")
                if os.path.exists(script_path) and not self.force_regenerate:
                    with open(script_path, "r") as f:
                        script_text = f.read()
                else:
                    script_obj = await self.screenwriter.write_script(
                        episode_plan=json.dumps(ep_plan.model_dump(), indent=2),
                        series_context=series_plan.series_description,
                        visual_style=visual_style,
                    )
                    script_text = script_obj.script_text
                    with open(script_path, "w") as f:
                        f.write(script_text)

                # Initialize single episode pipeline
                ep_config = PodcastConfig(
                    brand_id=brand_id or "intelli-verse-x",
                    working_dir=ep_dir,
                    video_style=visual_style,
                )
                
                ep_pipeline = Podcast2VideoPipeline(
                    chat_model=self.chat_model,
                    image_generator=self.image_generator,
                    video_generator=self.video_generator,
                    config=ep_config,
                )
                
                # Share continuity memory with episode pipeline for cross-episode consistency
                ep_pipeline.continuity_memory = series_continuity

                # Run episode pipeline
                try:
                    ep_output = await ep_pipeline.run(
                        script_path=script_path,
                        audience=audience,
                        trendy=trendy,
                    )
                    
                    # Save continuity state after episode
                    series_continuity.save_series_state()
                    
                    return {
                        "episode_number": ep_plan.episode_number,
                        "title": ep_plan.title,
                        "video_path": ep_output.get("video_path"),
                        "duration_seconds": ep_output.get("duration_seconds"),
                    }
                except Exception as e:
                    self.logger.error(f"Failed to generate episode {ep_plan.episode_number}: {e}")
                    return {
                        "episode_number": ep_plan.episode_number,
                        "error": str(e),
                    }

        tasks = [process_episode(ep) for ep in episodes_to_process]
        episode_results = await asyncio.gather(*tasks)

        # Cinematographer reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="podcast_series",
            rationale=(
                "Picturization for the podcast series focuses on a consistent studio setting "
                "with dynamic camera angles that emphasize character interaction and dialogue."
            ),
            inputs={
                "visual_style": visual_style,
                "total_episodes": len(episode_results),
            },
            outputs={
                "episodes/episode_XX/": "Individual episode video outputs.",
            },
        )

        # Step 4: Final Payload
        payload = {
            "run_id": self.run_id,
            "topic": topic,
            "series_plan": series_plan.model_dump(),
            "director_brief": director_brief.model_dump(),
            "episode_results": episode_results,
        }

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])

        return payload
