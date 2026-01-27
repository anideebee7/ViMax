#!/usr/bin/env python3
"""
Example script for generating a multi-flavor weekly content series.
Orchestrates Content Planner + Idea2Video for a 7-day calendar.
Supports flavors: playx, luxe, techx, autocurio, health.
"""
import asyncio
import logging
import os
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.series.weekly import WeeklySeriesPipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Generate a weekly video series for a specific brand flavor.")
    parser.add_argument("--flavor", type=str, default="playx", 
                        choices=["playx", "luxe", "techx", "autocurio", "health"],
                        help="The brand flavor to generate content for")
    parser.add_argument("--days", type=int, default=1, help="Number of days to generate")
    parser.add_argument("--shorts", type=int, default=1, help="Max shorts per day")
    parser.add_argument("--long-form", action="store_true", help="Include long-form videos")
    parser.add_argument("--config", type=str, default="configs/pipelines/video.yaml", 
                        help="Path to pipeline configuration")
    
    args = parser.parse_args()

    # 1. Configuration path
    if not os.path.exists(args.config):
        logger.error(f"Config not found: {args.config}")
        return

    logger.info(f"🚀 Initializing Weekly Content Series Pipeline for flavor: {args.flavor}...")
    
    # 2. Initialize pipeline
    pipeline = WeeklySeriesPipeline.init_from_config(args.config, flavor=args.flavor)
    
    # Configure data sources
    pipeline.fetcher_config = {
        "google_trends": {"enabled": True},
        "reddit": {"enabled": True, "subreddits": [], "limit": 15}, # subreddits empty = use flavor defaults
        "youtube": {"enabled": False}, # Set to True if API key is in config
        "newsapi": {"enabled": False}  # Set to True if API key is in config
    }

    # 3. Run Pipeline
    logger.info(f"🎬 Generating {args.flavor} series for {args.days} days...")
    
    result = await pipeline(
        num_days=args.days,
        max_shorts_per_day=args.shorts,
        include_long_form=args.long_form,
        push_to_s3=True # Permanent profiling on S3
    )

    logger.info("\n" + "=" * 60)
    logger.info(f"WEEKLY {args.flavor.upper()} SERIES GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Run ID: {result['run_id']}")
    logger.info(f"Channel: {result['plan']['channel']}")
    logger.info(f"Working Directory: {result['working_dir']}")
    
    for vid in result.get('generated_videos', []):
        logger.info(f"Generated {vid['type']}: {vid['topic']} -> {vid['video_path']}")
    
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
