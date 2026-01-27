#!/usr/bin/env python3
"""
Series Pipelines Detailed Rating Analysis.
Evaluates Learning Series, Podcast Series, TV Series, and Weekly Content.
Each has a unique rating bar tailored to its specific field and audience.
"""
import asyncio
import os
import sys
import json
import logging
import yaml
import re
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.series.learning import LearningSeriesPipeline
from pipelines.series.podcast import PodcastSeriesPipeline
from pipelines.series.tv import TVSeriesPipeline
from pipelines.series.weekly import WeeklySeriesPipeline
from agents.producers.analysis.evaluator import ScriptEvaluator
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_series_rating_analysis():
    # 1. Setup
    config_path = "configs/pipelines/video.yaml"
    if not os.path.exists(config_path):
        logger.error(f"Config not found at {config_path}")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Initialize chat model for evaluator
    def _resolve_env(v):
        if not isinstance(v, str): return v
        if v.startswith("${") and v.endswith("}"): return os.getenv(v[2:-1], "")
        return v

    chat_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
    chat_model = init_chat_model(**chat_args)
    
    evaluator = ScriptEvaluator(chat_model=chat_model)
    
    test_results = {}

    # --- CATEGORY 1: LEARNING SERIES ---
    logger.info("\n" + "="*80)
    logger.info("ANALYZING CATEGORY: LEARNING SERIES (Educational / Skill-Based)")
    logger.info("="*80)
    
    learning_pipeline = LearningSeriesPipeline.init_from_config(config_path)
    learning_pipeline.working_dir = ".working_dir/testing/series_audit/learning"
    os.makedirs(learning_pipeline.working_dir, exist_ok=True)
    
    learning_output = await learning_pipeline(
        topic="Mastering Prompt Engineering for AI Artists",
        num_episodes=3,
        max_episodes_to_generate=0,
        generate_images=False,
        generate_videos=False
    )
    
    # Custom Evaluation for Learning
    learning_eval_content = f"""CURRICULUM:\n{json.dumps(learning_output['curriculum'], indent=2)}"""
    learning_rating = await evaluator.evaluate(
        script_content=learning_eval_content,
        pipeline_name="Idea2LearningSeries",
        metadata={
            "field": "Education",
            "audience": "Aspiring AI Artists",
            "rating_bar": "Pedagogical Masterclass: Rating depends on clear objectives, Bloom's level alignment, and practical 'Aha!' exercises."
        }
    )
    test_results["learning"] = learning_rating.model_dump()

    # --- CATEGORY 2: PODCAST SERIES ---
    logger.info("\n" + "="*80)
    logger.info("ANALYZING CATEGORY: PODCAST SERIES (Conversational / Personality-Driven)")
    logger.info("="*80)
    
    podcast_pipeline = PodcastSeriesPipeline.init_from_config(config_path)
    podcast_pipeline.working_dir = ".working_dir/testing/series_audit/podcast"
    os.makedirs(podcast_pipeline.working_dir, exist_ok=True)
    
    # For audit, we only need the series plan
    podcast_output = await podcast_pipeline(
        topic="The Future of Work in 2030",
        num_episodes=2,
        max_episodes_to_generate=0 # This stops video generation but generates the plan
    )
    
    # Custom Evaluation for Podcast
    podcast_eval_content = f"""SERIES PLAN:\n{json.dumps(podcast_output['series_plan'], indent=2)}"""
    podcast_rating = await evaluator.evaluate(
        script_content=podcast_eval_content,
        pipeline_name="Idea2PodcastSeries",
        metadata={
            "field": "Audio/Social Commentary",
            "audience": "Global Tech Professionals",
            "rating_bar": "The Obsession Standard: Rating depends on curiosity gaps, voiceprint distinctiveness, and 'Mic-Drop' insights."
        }
    )
    test_results["podcast"] = podcast_rating.model_dump()

    # --- CATEGORY 3: TV SERIES ---
    logger.info("\n" + "="*80)
    logger.info("ANALYZING CATEGORY: TV SERIES (Narrative / Seasonal Arc)")
    logger.info("="*80)
    
    tv_pipeline = TVSeriesPipeline.init_from_config(config_path)
    tv_pipeline.working_dir = ".working_dir/testing/series_audit/tv"
    os.makedirs(tv_pipeline.working_dir, exist_ok=True)
    
    tv_output = await tv_pipeline(
        premise="A detective in a world where memories can be traded as currency.",
        genre="Cyberpunk Noir",
        num_episodes=3,
        max_episodes_to_generate=0
    )
    
    # Custom Evaluation for TV Series
    tv_eval_content = f"""SERIES SYNOPSIS:\n{tv_output['synopsis']}\n\nEPISODES SUMMARY:\n{json.dumps(tv_output['episodes'], indent=2)}"""
    tv_rating = await evaluator.evaluate(
        script_content=tv_eval_content,
        pipeline_name="TVSeriesPipeline",
        metadata={
            "field": "Narrative Entertainment",
            "audience": "Adult Sci-Fi Fans",
            "rating_bar": "The Peak TV Standard: Rating depends on structural tension, subtextual depth, and character DNA complexity."
        }
    )
    test_results["tv_series"] = tv_rating.model_dump()

    # --- CATEGORY 4: WEEKLY CONTENT ---
    logger.info("\n" + "="*80)
    logger.info("ANALYZING CATEGORY: WEEKLY CONTENT (Trend-Driven / Multi-Platform)")
    logger.info("="*80)
    
    # Mock behavior for audit
    weekly_pipeline = WeeklySeriesPipeline.init_from_config(config_path, flavor="techx")
    weekly_pipeline.working_dir = ".working_dir/testing/series_audit/weekly"
    os.makedirs(weekly_pipeline.working_dir, exist_ok=True)
    
    # Weekly pipeline generation without video calls
    # We'll just run the planning part
    google_trends, youtube_items, newsapi_items, reddit_items = await weekly_pipeline.fetch_data()
    plan = weekly_pipeline.content_planner.plan_weekly_content(
        google_trends=google_trends,
        youtube_items=youtube_items,
        newsapi_items=newsapi_items,
        reddit_items=reddit_items,
        top_n=5
    )
    
    # Custom Evaluation for Weekly Content
    weekly_eval_content = f"""WEEKLY PLAN:\n{json.dumps(plan, indent=2)}"""
    weekly_rating = await evaluator.evaluate(
        script_content=weekly_eval_content,
        pipeline_name="WeeklySeriesPipeline",
        metadata={
            "field": "Social Media Marketing",
            "audience": "Tech Enthusiasts",
            "rating_bar": "Viral Velocity: Rating depends on trend relevance, short/long-form synergy, and channel flavor consistency."
        }
    )
    test_results["weekly_content"] = weekly_rating.model_dump()

    # Final Summary
    report_path = ".working_dir/testing/series_audit/series_analysis_report.json"
    with open(report_path, "w") as f:
        json.dump(test_results, f, indent=2)
        
    print("\n" + "="*80)
    print("DETAILED SERIES RATING ANALYSIS SUMMARY")
    print("="*80)
    print(f"{'Category':<20} | {'Score':<8} | {'Creativity':<10} | {'Focus Field'}")
    print("-" * 80)
    for cat, res in test_results.items():
        print(f"{cat:<20} | {res['overall_rating']:<8} | {res['creativity']:<10} | {res['content_type_identified']}")
    print("-" * 80)
    print(f"Full report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(run_series_rating_analysis())
