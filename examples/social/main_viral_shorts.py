#!/usr/bin/env python3
"""
Example script for generating a viral-optimized short-form video.
"""
import asyncio
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.social.shorts import ViralShortsPipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="Generate a viral-optimized short-form video.")
    parser.add_argument("--idea", type=str, required=True, help="The core idea for the video")
    parser.add_argument("--platform", type=str, default="YouTube Shorts", 
                        choices=["YouTube Shorts", "Instagram Reels", "TikTok"],
                        help="Target platform")
    parser.add_argument("--brand", type=str, default="intelli-verse-x", help="S3 Brand ID")
    parser.add_argument("--config", type=str, default="configs/pipelines/video.yaml", help="Path to config")
    parser.add_argument("--no-video", action="store_true", help="Skip video generation (ideation only)")
    
    args = parser.parse_args()

    pipeline = ViralShortsPipeline.init_from_config(args.config)
    
    logger.info(f"🚀 Starting Viral Short Pipeline for platform: {args.platform}")
    logger.info(f"💡 Idea: {args.idea}")
    
    result = await pipeline(
        idea=args.idea,
        platform=args.platform,
        brand_id=args.brand,
        generate_video=not args.no_video
    )
    
    logger.info("\n" + "="*60)
    logger.info("VIRAL SCRIPT GENERATED:")
    logger.info(f"TITLE: {result['script']['title']}")
    logger.info(f"HOOK (VISUAL): {result['script']['hook_visual']}")
    logger.info(f"HOOK (VERBAL): {result['script']['hook_verbal']}")
    logger.info(f"LOOP STRATEGY: {result['script']['loop_strategy']}")
    logger.info(f"ENGAGEMENT BAIT: {result['script']['engagement_bait']}")
    logger.info("="*60)
    
    if "video_production" in result:
        logger.info(f"🎥 Video production initiated. Run ID: {pipeline.run_id}")
    else:
        logger.info("ℹ️ Video production skipped (--no-video)")

if __name__ == "__main__":
    asyncio.run(main())
