#!/usr/bin/env python3
"""
Generate a 40-second viral short movie optimized for maximum engagement.
Uses the ViralShortsPipeline with auto-ideation in viral mode.
"""
import asyncio
import logging
from pipelines.social.shorts import ViralShortsPipeline
from dotenv import load_dotenv
import os
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"viral_40s_short_{timestamp}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

load_dotenv()

async def main():
    print(f"🚀 Running Viral 40-Second Short Pipeline...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    pipeline = ViralShortsPipeline.init_from_config('configs/pipelines/video.yaml')
    
    # Configure shorts mode for 40 seconds
    # Update the video_pipeline's shorts_mode to target 40 seconds
    shorts_config = {
        "enabled": True,
        "format": "youtube_shorts",
        "max_shots": 6,  # Allow more shots for 40 seconds
        "target_duration_seconds": 40,
        "min_shot_seconds": 5,
        "max_shot_seconds": 10,
        "user_requirement_suffix": "Create a VIRAL 40-second video optimized for maximum engagement. Use MAXIMUM 6 shots. Keep it fast-paced with pattern interrupts every 3-5 seconds. This is for YouTube Shorts in vertical 9:16 format. The video must be exactly 40 seconds and designed to go viral with strong hooks, visual interest, and engagement bait."
    }
    
    # Apply shorts configuration to video pipeline
    pipeline.video_pipeline.shorts_mode = shorts_config
    
    # Also update the screenwriter and director shorts_mode if they have it
    if hasattr(pipeline.screenwriter, 'shorts_mode'):
        pipeline.screenwriter.shorts_mode = shorts_config
    if hasattr(pipeline.director, 'shorts_mode'):
        pipeline.director.shorts_mode = shorts_config
    
    print(f"\n📋 Configuration:")
    print(f"   - Target duration: 40 seconds")
    print(f"   - Max shots: 6")
    print(f"   - Platform: YouTube Shorts")
    print(f"   - Auto-ideation: Enabled (viral mode)")
    print(f"   - Format: Vertical 9:16")
    print(f"\n🎬 Starting pipeline with auto-ideation...\n")
    
    # Run with auto-ideation in viral mode
    result = await pipeline(
        idea=None,  # Will be auto-generated
        platform="YouTube Shorts",
        audience="Gen Z / Alpha",
        auto_ideate=True,
        ideation_mode="viral",  # Use viral mode for maximum engagement potential
        trendy=True,  # Fetch trends to inform ideation
        generate_video=True,
    )
    
    print(f"\n✅ Viral Short Pipeline Complete!")
    print(f"📂 Run ID: {pipeline.run_id}")
    print(f"📁 Working Directory: {pipeline.working_dir}")
    
    if "script" in result:
        script = result["script"]
        print(f"\n🎬 Generated Viral Script:")
        print(f"   Title: {script.get('title', 'N/A')}")
        print(f"   Hook (Visual): {script.get('hook_visual', 'N/A')}")
        print(f"   Hook (Verbal): {script.get('hook_verbal', 'N/A')}")
        print(f"   Loop Strategy: {script.get('loop_strategy', 'N/A')}")
        print(f"   Engagement Bait: {script.get('engagement_bait', 'N/A')}")
    
    if "video_production" in result:
        video_prod = result["video_production"]
        print(f"\n🎥 Video Production:")
        if "final_video_path" in video_prod:
            print(f"   Final Video: {video_prod['final_video_path']}")
        if "scenes" in video_prod:
            print(f"   Scenes: {len(video_prod['scenes'])}")
            for i, scene in enumerate(video_prod.get('scenes', []), 1):
                shots = scene.get('storyboard_frames', [])
                print(f"   Scene {i}: {len(shots)} shots")

if __name__ == "__main__":
    asyncio.run(main())
