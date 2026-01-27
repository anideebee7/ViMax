import asyncio
import logging
from pipelines.movies.short_video import ShortMovieVideoPipeline
from dotenv import load_dotenv
import os
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"short_movie_48s_{timestamp}.log"
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
    print(f"🚀 Running Short Movie Pipeline (48 seconds)...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    pipeline = ShortMovieVideoPipeline.init_from_config('configs/pipelines/short_video.yaml')
    
    # Override image generator to use Gemini directly
    from utils.pipeline.generator_factory import create_generators
    from utils.core.rate_limiter import RateLimiter
    
    # Create unified generators with Gemini as primary image generator
    image_generator, video_generator = create_generators(
        image_rate_limiter=RateLimiter(max_requests_per_minute=200) if os.getenv("GEMINI_API_KEY") else None,
        video_rate_limiter=None,
    )
    
    # Replace the image generator with Gemini-based unified generator
    pipeline.image_generator = image_generator
    if video_generator:
        pipeline.video_generator = video_generator
    
    # Force regenerate to ensure fresh generation
    pipeline.force_regenerate = True
    
    print(f"\n📋 Configuration:")
    print(f"   - Target duration: 48 seconds (0.8 minutes)")
    print(f"   - Force regenerate: True")
    print(f"\n🎬 Starting pipeline...\n")
    
    result = await pipeline(
        premise="A young artist discovers that their paintings come to life at midnight, but only for one hour. They must decide whether to keep this secret or share it with the world.",
        genre="fantasy drama",
        target_duration_minutes=0.8,  # 48 seconds = 0.8 minutes
        audience="general audience, fantasy lovers",
        style="cinematic, magical realism, warm lighting",
        trendy=False,
        content_format="animated",
        generate_storyboard_images=True,
        generate_videos=True,
    )
    
    print(f"\n✅ Short Movie Pipeline Complete!")
    print(f"📂 Run ID: {result.get('run_id', 'N/A')}")
    print(f"📁 Working Directory: {pipeline.working_dir}")
    print(f"🎬 Scenes processed: {len(result.get('scenes', []))}")
    
    # Count total shots
    total_shots = 0
    if result.get('scenes'):
        for scene in result['scenes']:
            shots_count = len(scene.get('storyboard_frames', []))
            total_shots += shots_count
            print(f"📸 Shots in scene {scene.get('scene_number', '?')}: {shots_count}")
    print(f"📸 Total shots: {total_shots}")

if __name__ == "__main__":
    asyncio.run(main())
