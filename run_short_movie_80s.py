import asyncio
import logging
from pipelines import VideoPipeline
from dotenv import load_dotenv
import os

# Set up logging
log_file = "short_movie_80s.log"
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
    print(f"🚀 Running 80-second Short Movie Pipeline...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")

    # Initialize pipeline from video_shorts config
    pipeline = VideoPipeline.init_from_config(config_path='configs/pipelines/video_shorts.yaml')

    # Override shorts mode for 80 seconds
    pipeline.shorts_mode['target_duration_seconds'] = 80
    pipeline.shorts_mode['max_shots'] = 10
    pipeline.shorts_mode['user_requirement_suffix'] = (
        "Create a SHORT movie with exactly 10 shots. Keep it cinematic and expressive. "
        "Total duration must be 80 seconds (8 seconds per shot). "
        "This is for a high-quality cinematic short format."
    )
    
    # We want a fresh run
    pipeline.force_regenerate = True

    idea = (
        "A lonely robot on a deserted island discovers an old solar-powered record player. "
        "As it listens to jazz, it begins to dance, and its movements accidentally trigger hidden "
        "mechanisms that revive the island's dormant flora, turning the gray landscape into a neon paradise."
    )
    
    user_requirement = (
        "Target audience: Cinematic enthusiasts. "
        "Focus on the robot's emotional evolution from loneliness to joy. "
        "The island's transformation should be visually spectacular."
    )
    
    style = "High-end 3D animation, expressive robotic eyes, vibrant bioluminescent plants, warm cinematic lighting."

    result = await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
        trendy=True
    )

    print(f"\n✅ 80-second Short Movie Generation Complete!")
    print(f"🎬 Video Path: {result['video_path']}")
    print(f"📂 Run ID: {result['run_id']}")

if __name__ == "__main__":
    asyncio.run(main())
