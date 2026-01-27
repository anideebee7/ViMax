#!/usr/bin/env python3
"""
Generate a 30-second viral short video optimized for maximum engagement.
Uses the ViralShortsPipeline with auto-ideation in viral mode.
Uses Gemini for image generation.
"""
import asyncio
import logging
from pipelines.social.shorts import ViralShortsPipeline
from dotenv import load_dotenv
import os
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"viral_30s_short_{timestamp}.log"
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
    print(f"🚀 Running Viral 30-Second Short Pipeline...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    # This now uses unified generators automatically (Gemini -> PiAPI -> KieAI)
    pipeline = ViralShortsPipeline.init_from_config('configs/pipelines/video.yaml')
    
    # Ensure all components use the unified generator
    # The init_from_config should already set this, but we verify
    if hasattr(pipeline.video_pipeline, 'character_portraits_generator'):
        pipeline.video_pipeline.character_portraits_generator.image_generator = pipeline.video_pipeline.image_generator
    
    # Configure shorts mode for 30 seconds
    shorts_config = {
        "enabled": True,
        "format": "youtube_shorts",
        "max_shots": 5,  # Optimized for 30 seconds (6 seconds per shot average)
        "target_duration_seconds": 30,
        "min_shot_seconds": 4,
        "max_shot_seconds": 8,
        "user_requirement_suffix": "Create a VIRAL 30-second video optimized for maximum engagement. Use MAXIMUM 5 shots. Keep it fast-paced with pattern interrupts every 3-5 seconds. This is for YouTube Shorts in vertical 9:16 format. The video must be exactly 30 seconds and designed to go viral with strong hooks, visual interest, and engagement bait."
    }
    
    # Apply shorts configuration to video pipeline
    pipeline.video_pipeline.shorts_mode = shorts_config
    
    # Also update the screenwriter and director shorts_mode if they have it
    if hasattr(pipeline.screenwriter, 'shorts_mode'):
        pipeline.screenwriter.shorts_mode = shorts_config
    if hasattr(pipeline.director, 'shorts_mode'):
        pipeline.director.shorts_mode = shorts_config
    
    # Force regenerate for fresh run
    pipeline.force_regenerate = True
    pipeline.video_pipeline.force_regenerate = True
    
    print(f"\n📋 Configuration:")
    print(f"   - Target duration: 30 seconds")
    print(f"   - Max shots: 5")
    print(f"   - Platform: YouTube Shorts")
    print(f"   - Auto-ideation: Enabled (viral mode)")
    print(f"   - Format: Vertical 9:16")
    print(f"   - Image Generator: Gemini (unified with fallback)")
    print(f"   - Force regenerate: True")
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
