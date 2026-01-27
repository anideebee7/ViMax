#!/usr/bin/env python3
"""
Resume a 30-second viral short video pipeline from an existing run_id.
Skips already generated content (character portraits, etc.) and continues from where it left off.
"""
import asyncio
import logging
from pipelines.social.shorts import ViralShortsPipeline
from dotenv import load_dotenv
import os
import json
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"resume_viral_30s_short_{timestamp}.log"
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
    # Existing run_id to resume from
    existing_run_id = "viral_shorts_20260126_222626_fc38fd78"
    
    print(f"🔄 Resuming Viral 30-Second Short Pipeline...")
    print(f"📝 Run ID: {existing_run_id}")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Load existing ideation and script
    # Use absolute path to ensure we're using the exact existing directory
    # Try both possible locations (viral_shorts and video directories)
    base_working_dir = os.path.abspath(".working_dir/social/viral_shorts")
    working_dir = os.path.join(base_working_dir, existing_run_id)
    
    # If not found, try the video directory (for older runs)
    if not os.path.exists(working_dir):
        alt_working_dir = os.path.abspath(f".working_dir/video/{existing_run_id}")
        if os.path.exists(alt_working_dir):
            working_dir = alt_working_dir
            base_working_dir = os.path.dirname(alt_working_dir)
            print(f"✅ Found run directory in video folder: {working_dir}")
    
    if not os.path.exists(working_dir):
        print(f"⚠️  Warning: Run directory not found at {working_dir}")
        print(f"   Attempting to create/use: {working_dir}")
        os.makedirs(working_dir, exist_ok=True)
    else:
        print(f"✅ Found existing run directory: {working_dir}")
    ideation_path = os.path.join(working_dir, "ideation.json")
    script_path = os.path.join(working_dir, "viral_script.json")
    
    idea = None
    if os.path.exists(ideation_path):
        with open(ideation_path, "r") as f:
            ideation_data = json.load(f)
            idea = ideation_data.get("idea")
            print(f"✅ Loaded existing ideation: {ideation_data.get('title', 'N/A')}")
    
    if not idea and os.path.exists(script_path):
        with open(script_path, "r") as f:
            script_data = json.load(f)
            # Reconstruct idea from script
            idea = script_data.get("title", "")
            print(f"✅ Loaded existing script: {script_data.get('title', 'N/A')}")
    
    if not idea:
        print("❌ Error: Could not find existing ideation or script. Cannot resume.")
        return
    
    # Initialize pipeline with existing run_id and working_dir
    # This ensures no new run_id or folder is created
    # Pass the full working_dir path (including run_id) so it uses it directly
    pipeline = ViralShortsPipeline.init_from_config(
        'configs/pipelines/video.yaml',
        run_id=existing_run_id,  # Pass run_id to prevent new one from being created
        working_dir=working_dir,  # Pass full path to existing run directory
    )
    
    # Verify the pipeline is using the correct working_dir
    print(f"✅ Pipeline initialized with working_dir: {pipeline.working_dir}")
    print(f"✅ Pipeline run_id: {pipeline.run_id}")
    
    if pipeline.working_dir != working_dir:
        print(f"⚠️  Warning: Pipeline working_dir ({pipeline.working_dir}) doesn't match expected ({working_dir})")
        print(f"   Pipeline will use: {pipeline.working_dir}")
        working_dir = pipeline.working_dir
    
    # Ensure nested video_pipeline also uses the correct working_dir
    # (it should already be set, but verify)
    if pipeline.video_pipeline.working_dir != os.path.join(working_dir, "production"):
        pipeline.video_pipeline.working_dir = os.path.join(working_dir, "production")
    
    # IMPORTANT: Set force_regenerate=False to skip already generated content
    pipeline.force_regenerate = False
    pipeline.video_pipeline.force_regenerate = False
    
    # Ensure all components use the unified generator
    if hasattr(pipeline.video_pipeline, 'character_portraits_generator'):
        pipeline.video_pipeline.character_portraits_generator.image_generator = pipeline.video_pipeline.image_generator
    
    # Configure shorts mode for 30 seconds
    shorts_config = {
        "enabled": True,
        "format": "youtube_shorts",
        "max_shots": 5,
        "target_duration_seconds": 30,
        "min_shot_seconds": 4,
        "max_shot_seconds": 8,
        "user_requirement_suffix": "Create a VIRAL 30-second video optimized for maximum engagement. Use MAXIMUM 5 shots. Keep it fast-paced with pattern interrupts every 3-5 seconds. This is for YouTube Shorts in vertical 9:16 format. The video must be exactly 30 seconds and designed to go viral with strong hooks, visual interest, and engagement bait."
    }
    
    # Apply shorts configuration
    pipeline.video_pipeline.shorts_mode = shorts_config
    if hasattr(pipeline.screenwriter, 'shorts_mode'):
        pipeline.screenwriter.shorts_mode = shorts_config
    if hasattr(pipeline.director, 'shorts_mode'):
        pipeline.director.shorts_mode = shorts_config
    
    print(f"\n📋 Resume Configuration:")
    print(f"   - Run ID: {existing_run_id}")
    print(f"   - Working Directory: {working_dir}")
    print(f"   - Force Regenerate: False (will skip existing content)")
    print(f"   - Target duration: 30 seconds")
    print(f"   - Max shots: 5")
    print(f"   - Platform: YouTube Shorts")
    print(f"   - Image Generator: Unified (Gemini -> PiAPI -> KieAI)")
    print(f"\n🎬 Resuming pipeline...\n")
    
    # Resume with existing idea (skip ideation)
    result = await pipeline(
        idea=idea,  # Use existing idea
        platform="YouTube Shorts",
        audience="Gen Z / Alpha",
        auto_ideate=False,  # Don't re-ideate
        ideation_mode="viral",
        trendy=False,  # Don't re-fetch trends
        generate_video=True,
    )
    
    print(f"\n✅ Viral Short Pipeline Complete!")
    print(f"📂 Run ID: {pipeline.run_id}")
    print(f"📁 Working Directory: {pipeline.working_dir}")
    
    if "script" in result:
        script = result["script"]
        print(f"\n🎬 Generated Viral Script:")
        print(f"   Title: {script.get('title', 'N/A')}")
    
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
