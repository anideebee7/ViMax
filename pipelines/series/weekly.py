"""Weekly Content Series Pipeline

Orchestrates the Content Planner to generate a 7-day multi-flavor content plan,
then generates a series of videos (shorts and long-form) based on that plan.
Supports flavors for IntelliVerse PlayX, Luxe, TechX, AutoCurio, and Health.
"""
import json
import logging
import os
import asyncio
from typing import Optional, Dict, Any, List, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.planners.content import ContentPlanner
from pipelines.base.idea import VideoPipeline
from tools.fetchers import GoogleTrendsFetcher
from tools.fetchers import YouTubeTrendsFetcher
from tools.fetchers import NewsAPIFetcher
from tools.fetchers import RedditFetcher
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.core.rate_limiter import RateLimiter
from utils.pipeline.generator_factory import create_generators
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression

logger = logging.getLogger(__name__)


class WeeklySeriesPipeline:
    """Pipeline to generate a weekly video series based on trending topics for specific brand flavors."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        video_generator=None,
        working_dir: str = ".working_dir/series/weekly_series",
        fetcher_config: Optional[Dict] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
        flavor: str = "health",
        brand_id: str = "intelli-verse-x",
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.fetcher_config = fetcher_config or {}
        self.force_regenerate = force_regenerate
        self.flavor = flavor.lower()
        self.brand_id = brand_id

        self.base_working_dir = working_dir
        # Note: pipeline_name uses flavor for weekly series
        pipeline_name = f"weekly_{self.flavor}"
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name=pipeline_name,
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.content_planner = ContentPlanner(flavor=self.flavor, brand_id=self.brand_id)
        self.continuity_memory = ContinuityMemory(working_dir=self.working_dir)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def init_from_config(cls, config_path: str, flavor: str = "health"):
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
        image_generator, video_generator = create_generators()

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=_resolve_path(config.get("working_dir", f".working_dir/series/weekly_{flavor}")),
            fetcher_config=config.get("data_sources", {}),
            force_regenerate=bool(config.get("force_regenerate", False)),
            flavor=flavor,
            brand_id=config.get("brand_id", "intelli-verse-x")
        )

    async def fetch_data(self) -> tuple:
        """Fetch data from all configured sources."""
        data_sources = self.fetcher_config
        tasks = []
        
        # Google Trends
        if data_sources.get('google_trends', {}).get('enabled', True):
            trends_fetcher = GoogleTrendsFetcher()
            tasks.append(('google_trends', trends_fetcher.fetch_trends()))
        else:
            tasks.append(('google_trends', asyncio.create_task(asyncio.sleep(0, result=[]))))
        
        # YouTube
        if data_sources.get('youtube', {}).get('enabled', True):
            api_key = data_sources.get('youtube', {}).get('api_key', '')
            if api_key and api_key != '<YOUR_YOUTUBE_API_KEY>':
                youtube_fetcher = YouTubeTrendsFetcher(api_key=api_key)
                tasks.append(('youtube', youtube_fetcher.fetch_trending()))
            else:
                tasks.append(('youtube', asyncio.create_task(asyncio.sleep(0, result=[]))))
        else:
            tasks.append(('youtube', asyncio.create_task(asyncio.sleep(0, result=[]))))
        
        # NewsAPI
        if data_sources.get('newsapi', {}).get('enabled', True):
            api_key = data_sources.get('newsapi', {}).get('api_key', '')
            if api_key and api_key != '<YOUR_NEWSAPI_KEY>':
                newsapi_fetcher = NewsAPIFetcher(api_key=api_key)
                tasks.append(('newsapi', newsapi_fetcher.fetch_health_headlines()))
            else:
                tasks.append(('newsapi', asyncio.create_task(asyncio.sleep(0, result=[]))))
        else:
            tasks.append(('newsapi', asyncio.create_task(asyncio.sleep(0, result=[]))))
        
        # Reddit
        if data_sources.get('reddit', {}).get('enabled', True):
            reddit_fetcher = RedditFetcher()
            tasks.append(('reddit', reddit_fetcher.fetch_all_subreddits()))
        else:
            tasks.append(('reddit', asyncio.create_task(asyncio.sleep(0, result=[]))))
        
        results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
        
        result_dict = {}
        for (source_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                self.logger.error(f"Error fetching {source_name}: {result}")
                result_dict[source_name] = []
            else:
                result_dict[source_name] = result
        
        return (
            result_dict.get('google_trends', []),
            result_dict.get('youtube', []),
            result_dict.get('newsapi', []),
            result_dict.get('reddit', [])
        )

    async def __call__(
        self,
        num_days: int = 7,
        max_shorts_per_day: int = 1,
        include_long_form: bool = True,
        style: str = "cinematic",
        audience: Optional[str] = None,
        push_to_s3: bool = True,
    ) -> Dict[str, Any]:
        """Generate the weekly content series."""
        
        # Default audience based on flavor
        if not audience:
            audiences = {
                "health": "health conscious adults",
                "playx": "gamers and entertainment seekers",
                "luxe": "luxury lifestyle enthusiasts",
                "techx": "tech enthusiasts and early adopters",
                "autocurio": "automotive and engineering curious minds"
            }
            audience = audiences.get(self.flavor, "general audience")

        # 1. Fetch Data
        self.logger.info(f"📊 Fetching trending data for flavor: {self.flavor}...")
        google_trends, youtube_items, newsapi_items, reddit_items = await self.fetch_data()
        
        # 2. Plan Content
        self.logger.info("🧠 Planning weekly content...")
        plan = self.content_planner.plan_weekly_content(
            google_trends=google_trends,
            youtube_items=youtube_items,
            newsapi_items=newsapi_items,
            reddit_items=reddit_items,
            top_n=10
        )
        
        # Save locally
        with open(os.path.join(self.working_dir, "weekly_plan.json"), "w") as f:
            json.dump(plan, f, indent=2)
            
        # Push to S3 if requested
        if push_to_s3:
            self.content_planner.push_plan_to_s3(plan)
            
        calendar = plan.get('calendar7Days', [])[:num_days]
        long_form_topics = plan.get('longForm', []) if include_long_form else []
        
        generated_videos = []
        
        # Load series-level continuity state (cross-day persistence)
        self.continuity_memory.load_series_state()
        
        # 3. Generate Shorts
        self.logger.info(f"🎬 Generating shorts for {len(calendar)} days...")
        for day in calendar:
            # Load continuity state at start of day
            self.continuity_memory.load_series_state()
            
            day_name = day['day']
            day_dir = os.path.join(self.working_dir, f"day_{day_name}")
            os.makedirs(day_dir, exist_ok=True)
            
            for i, short_data in enumerate(day['shorts'][:max_shorts_per_day]):
                short_topic = short_data['topic']
                short_hook = short_data['hook']
                short_dir = os.path.join(day_dir, f"short_{i}")
                
                self.logger.info(f"🎥 Generating short for {day_name} ({self.flavor}): {short_topic}")
                
                # Use VideoPipeline for each short
                i2v = VideoPipeline(
                    chat_model=self.chat_model,
                    image_generator=self.image_generator,
                    video_generator=self.video_generator,
                    working_dir=short_dir,
                    shorts_mode={"enabled": True, "target_duration_seconds": 20, "max_shots": 4},
                    use_run_id=False,
                    pipeline_kind="viral_shorts"
                )
                
                # Share continuity memory with VideoPipeline for cross-day consistency
                i2v.continuity_memory = self.continuity_memory
                
                try:
                    video_result = await i2v(
                        idea=f"Create a high-energy {self.flavor} short about {short_topic}. Hook: {short_hook}",
                        user_requirement=f"Topic: {short_topic}. Hook: {short_hook}. Format: YouTube Shorts/TikTok. Brand: {self.content_planner.config['channel']}",
                        style=style,
                        audience=audience,
                        trendy=True
                    )
                    
                    # Save continuity state after short
                    self.continuity_memory.save_series_state()
                    
                    generated_videos.append({
                        "type": "short",
                        "day": day_name,
                        "topic": short_topic,
                        "video_path": video_result.get("video_path")
                    })
                except Exception as e:
                    self.logger.error(f"Failed to generate short for {short_topic}: {e}")

        # 4. Generate Long-form
        if include_long_form:
            self.logger.info(f"🎬 Generating {len(long_form_topics)} long-form videos...")
            for i, long_data in enumerate(long_form_topics):
                # Load continuity state at start of long-form
                self.continuity_memory.load_series_state()
                
                long_topic = long_data['topic']
                long_title = long_data['title']
                long_dir = os.path.join(self.working_dir, f"long_form_{i}")
                
                self.logger.info(f"🎥 Generating long-form: {long_topic}")
                
                i2v = VideoPipeline(
                    chat_model=self.chat_model,
                    image_generator=self.image_generator,
                    video_generator=self.video_generator,
                    working_dir=long_dir,
                    shorts_mode={"enabled": False},
                    use_run_id=False,
                    pipeline_kind="feature_film" # or some other kind
                )
                
                # Share continuity memory with VideoPipeline
                i2v.continuity_memory = self.continuity_memory
                
                try:
                    video_result = await i2v(
                        idea=f"Detailed {self.flavor} video about {long_topic}. Title: {long_title}",
                        user_requirement=f"Provide a deep dive into {long_topic}. Scientific/Expert approach. Brand: {self.content_planner.config['channel']}",
                        style=style,
                        audience=audience,
                        trendy=True
                    )
                    
                    # Save continuity state after long-form
                    self.continuity_memory.save_series_state()
                    
                    generated_videos.append({
                        "type": "long_form",
                        "topic": long_topic,
                        "video_path": video_result.get("video_path")
                    })
                except Exception as e:
                    self.logger.error(f"Failed to generate long-form for {long_topic}: {e}")

        output = {
            "run_id": self.run_id,
            "flavor": self.flavor,
            "plan": plan,
            "generated_videos": generated_videos,
            "working_dir": self.working_dir
        }
        
        with open(os.path.join(self.working_dir, "weekly_series_output.json"), "w") as f:
            json.dump(output, f, indent=2)
            
        return output
