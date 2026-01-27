#!/usr/bin/env python
"""
Test Music Video Pipeline Character Fix

This script tests the character rendering fix by running two scenarios:
1. WITH Autocurio S3 characters (brand_id='intelli-verse-x')
2. WITHOUT S3 characters (fresh AI-generated characters)

Both are kids songs to verify character consistency in the raw frames.

Usage:
    # Run with Autocurio characters
    uv run python test_music_video_character_fix.py --autocurio

    # Run with fresh characters (no S3)
    uv run python test_music_video_character_fix.py --fresh

    # Run both sequentially
    uv run python test_music_video_character_fix.py --both
"""
import asyncio
import argparse
import logging
import os
from datetime import datetime
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv

# Set up logging
def setup_logging(test_name: str):
    log_file = f"test_musicvideo_{test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

load_dotenv()


async def run_autocurio_test():
    """Run music video pipeline with Autocurio S3 characters."""
    log_file = setup_logging("autocurio")
    print(f"\n{'='*80}")
    print("🤖 TEST 1: Music Video with AUTOCURIO S3 Characters")
    print(f"{'='*80}")
    print(f"📝 Logs: {os.path.abspath(log_file)}")
    
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    pipeline.force_regenerate = True  # Fresh generation to test fix
    
    result = await pipeline(
        idea='Autocurio the curious robot learns about colors and shapes with his friend DotDot - a fun educational song for toddlers',
        style='colorful 3D kids animation pop',
        audience='kids ages 2-5, toddlers, preschoolers',
        brand_id='intelli-verse-x',  # S3 brand with Autocurio characters
        character_names=['autocurio', 'DotDot'],  # Specific S3 characters
        trendy=False
    )
    
    print(f"\n✅ Autocurio Test Complete!")
    print(f"🎬 Video Path: {result.get('video_path')}")
    print(f"🎵 Audio Path: {result.get('audio_path')}")
    print(f"📂 Working Dir: {pipeline.working_dir}")
    print(f"🔑 Run ID: {result.get('run_id')}")
    
    # Verify raw frames exist and have character content
    shots_dir = os.path.join(pipeline.working_dir, "shots")
    if os.path.exists(shots_dir):
        for shot_dir in sorted(os.listdir(shots_dir)):
            shot_path = os.path.join(shots_dir, shot_dir)
            if os.path.isdir(shot_path):
                raw_frame = os.path.join(shot_path, "first_frame_raw.png")
                frame = os.path.join(shot_path, "first_frame.png")
                print(f"  📸 {shot_dir}: raw={os.path.exists(raw_frame)}, composited={os.path.exists(frame)}")
    
    return result


async def run_fresh_characters_test():
    """Run music video pipeline with fresh AI-generated characters (no S3)."""
    log_file = setup_logging("fresh_chars")
    print(f"\n{'='*80}")
    print("🌟 TEST 2: Music Video with FRESH AI-Generated Characters (No S3)")
    print(f"{'='*80}")
    print(f"📝 Logs: {os.path.abspath(log_file)}")
    
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    pipeline.force_regenerate = True  # Fresh generation
    
    result = await pipeline(
        idea='A magical unicorn named Sparkle and a friendly dragon named Blaze teach kids about counting from 1 to 10 - upbeat nursery rhyme',
        style='colorful 2D cartoon animation, bright and cheerful',
        audience='kids ages 3-6, preschoolers',
        # NO brand_id or character_names - fresh characters
        trendy=False
    )
    
    print(f"\n✅ Fresh Characters Test Complete!")
    print(f"🎬 Video Path: {result.get('video_path')}")
    print(f"🎵 Audio Path: {result.get('audio_path')}")
    print(f"📂 Working Dir: {pipeline.working_dir}")
    print(f"🔑 Run ID: {result.get('run_id')}")
    
    # Verify raw frames exist
    shots_dir = os.path.join(pipeline.working_dir, "shots")
    if os.path.exists(shots_dir):
        for shot_dir in sorted(os.listdir(shots_dir)):
            shot_path = os.path.join(shots_dir, shot_dir)
            if os.path.isdir(shot_path):
                raw_frame = os.path.join(shot_path, "first_frame_raw.png")
                frame = os.path.join(shot_path, "first_frame.png")
                print(f"  📸 {shot_dir}: raw={os.path.exists(raw_frame)}, composited={os.path.exists(frame)}")
    
    return result


async def main():
    parser = argparse.ArgumentParser(description="Test Music Video Character Fix")
    parser.add_argument("--autocurio", action="store_true", help="Run with Autocurio S3 characters")
    parser.add_argument("--fresh", action="store_true", help="Run with fresh AI-generated characters")
    parser.add_argument("--both", action="store_true", help="Run both tests sequentially")
    
    args = parser.parse_args()
    
    if not any([args.autocurio, args.fresh, args.both]):
        print("❌ Please specify a test to run: --autocurio, --fresh, or --both")
        parser.print_help()
        return
    
    results = {}
    
    if args.autocurio or args.both:
        results['autocurio'] = await run_autocurio_test()
    
    if args.fresh or args.both:
        results['fresh'] = await run_fresh_characters_test()
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 TEST SUMMARY")
    print(f"{'='*80}")
    for test_name, result in results.items():
        print(f"\n{test_name.upper()}:")
        print(f"  Video: {result.get('video_path', 'N/A')}")
        print(f"  Run ID: {result.get('run_id', 'N/A')}")
    
    print(f"\n✨ Check the raw frames in each shots/ directory to verify character rendering!")
    print("The raw frame (first_frame_raw.png) should now contain the character in the scene.")


if __name__ == "__main__":
    asyncio.run(main())
