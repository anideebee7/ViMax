#!/usr/bin/env python3
"""
Generate videos from existing storyboard frames for run: video_20260126_064410_7b9abfac

Uses unified video generator with fallback chain:
1. KieAI veo3_fast (primary)
2. PiAPI veo3.1 (fallback)
3. Google veo-3.1-generate-preview (last resort)
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from utils.pipeline.generator_factory import create_video_generator
from utils.media.video import concat_videos

# Set up logging
run_id = "video_20260126_064410_7b9abfac"
log_file = f"generate_videos_{run_id}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Working directory
WORKING_DIR = f".working_dir/video_shorts/{run_id}"
SCENES_DIR = os.path.join(WORKING_DIR, "scenes")


async def main():
    print(f"🎬 Generating Videos from Frames for run: {run_id}")
    print("=" * 60)
    print("\nUsing unified video generator with fallback chain:")
    print("  1. KieAI veo3_fast (primary)")
    print("  2. PiAPI veo3.1 (fallback)")
    print("  3. Google veo-3.1-generate-preview (last resort)")
    print("=" * 60)
    
    # Load script for prompts
    script_path = os.path.join(WORKING_DIR, "script.json")
    with open(script_path, "r") as f:
        script_scenes = json.load(f)
    
    print(f"\n📜 Loaded {len(script_scenes)} scene scripts")
    
    # Create video generator
    video_generator = create_video_generator()
    
    # Process each scene
    all_scene_videos = []
    
    for i in range(1, 11):  # 10 scenes
        scene_dir = os.path.join(SCENES_DIR, f"scene_{i:02d}")
        frame_path = os.path.join(scene_dir, "frame_01.png")
        video_path = os.path.join(scene_dir, "shot_01.mp4")
        scene_video_path = os.path.join(scene_dir, "scene_video.mp4")
        
        if not os.path.exists(frame_path):
            logger.warning(f"  Scene {i}: Frame not found, skipping")
            continue
        
        # Check if video already exists
        if os.path.exists(video_path):
            logger.info(f"  Scene {i}: Video already exists, skipping generation")
            all_scene_videos.append(video_path)
            continue
        
        print(f"\n🎥 Processing Scene {i}/10...")
        
        # Get scene script for prompt
        scene_script = script_scenes[i-1] if i <= len(script_scenes) else ""
        if isinstance(scene_script, str):
            scene_desc = scene_script[:400]
        else:
            scene_desc = str(scene_script)[:400]
        
        # Create video prompt
        video_prompt = f"{scene_desc}. High-end 3D animation style, cinematic motion, smooth camera movement. Expressive robot character dancing, vibrant bioluminescent environment."
        
        logger.info(f"  Frame: {frame_path}")
        logger.info(f"  Prompt: {video_prompt[:100]}...")
        
        try:
            # Generate video (8 seconds per shot)
            video_output = await video_generator.generate_single_video(
                prompt=video_prompt,
                reference_image_paths=[frame_path],
                aspect_ratio="16:9",
                duration=8,
            )
            
            if video_output:
                video_output.save(video_path)
                logger.info(f"  ✅ Generated video: {video_path}")
                
                # Copy to scene_video.mp4 (single shot = scene video)
                import shutil
                shutil.copy(video_path, scene_video_path)
                all_scene_videos.append(scene_video_path)
            else:
                logger.warning(f"  ❌ No video output for scene {i}")
                
        except Exception as e:
            logger.error(f"  ❌ Video generation failed for scene {i}: {e}")
    
    # Concatenate all scene videos into final video
    if all_scene_videos:
        final_video_path = os.path.join(WORKING_DIR, "final_video.mp4")
        print(f"\n🎬 Concatenating {len(all_scene_videos)} scene videos...")
        
        try:
            concat_videos(all_scene_videos, final_video_path)
            print(f"\n✅ Final video created: {final_video_path}")
        except Exception as e:
            logger.error(f"Failed to concatenate videos: {e}")
            # Use first video as fallback
            if all_scene_videos:
                import shutil
                shutil.copy(all_scene_videos[0], final_video_path)
                print(f"\n⚠️ Concatenation failed, using first scene as final: {final_video_path}")
    else:
        print("\n❌ No videos were generated")
    
    print("\n" + "=" * 60)
    print("🏁 Video generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
