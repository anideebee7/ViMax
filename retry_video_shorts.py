#!/usr/bin/env python3
"""
Retry video shorts pipeline for run: video_20260126_064410_7b9abfac

This script resumes the "Chromatic Bloom" video about a lonely robot 
discovering a record player on a deserted island.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pipelines.movies.short_video import ShortMovieVideoPipeline
from utils.pipeline.generator_factory import create_generators

# Set up logging to both console and file
run_id = "video_20260126_064410_7b9abfac"
log_file = f"retry_{run_id}.log"
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
    print(f"🚀 Retrying Video Shorts Pipeline for run: {run_id}...")
    print("=" * 60)
    print("Title: Chromatic Bloom")
    print("Story: A lonely robot discovers a record player and dances,")
    print("       awakening the island's dormant flora into a neon paradise.")
    print("=" * 60)
    
    # Initialize chat model
    chat_model = init_chat_model(
        model="gemini-2.0-flash",
        model_provider="google_genai",
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    # Use unified generators with correct fallback chain:
    # Image: Gemini API -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
    # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
    print("\nUsing unified generators:")
    print("  Image: Gemini API -> PiAPI nano-banana-pro -> KieAI nano-banana-pro")
    print("  Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1")
    print()
    
    image_generator, video_generator = create_generators()
    
    # Create pipeline manually
    pipeline = ShortMovieVideoPipeline(
        chat_model=chat_model,
        image_generator=image_generator,
        video_generator=video_generator,
        working_dir=".working_dir/video_shorts",
        force_regenerate=False,  # Resume from existing artifacts
    )
    
    # Set the run_id to resume from existing progress
    pipeline.run_id = run_id
    pipeline.working_dir = os.path.join(pipeline.base_working_dir, run_id)
    
    # Original premise from story_prompt.txt
    premise = """A lonely robot on a deserted island discovers an old solar-powered record player. 
As it listens to jazz, it begins to dance, and its movements accidentally trigger hidden mechanisms 
that revive the island's dormant flora, turning the gray landscape into a neon paradise."""
    
    result = await pipeline(
        premise=premise,
        genre="drama",
        target_duration_minutes=2,  # ~80 seconds = ~1.3 minutes, rounding to 2
        audience="cinematic enthusiasts",
        style="High-end 3D animation, expressive robotic eyes, vibrant bioluminescent plants, warm cinematic lighting",
        trendy=False,
        auto_ideate=False,
        content_format="animated",  # The story is about a robot, animated makes sense
        generate_storyboard_images=True,
        generate_videos=True,
    )
    
    print(f"\n✅ Retry Complete!")
    print(f"🎬 Final Video Path: {result.get('final_video_path', 'N/A')}")
    print(f"📂 Run ID: {result.get('run_id', run_id)}")
    
    # Print scene summary
    scenes = result.get('scenes', [])
    if scenes:
        print(f"\n📽️ Generated {len(scenes)} scenes:")
        for i, scene in enumerate(scenes):
            video_path = scene.get('video_path', 'Not generated')
            print(f"  Scene {i+1}: {video_path}")


if __name__ == "__main__":
    asyncio.run(main())
