import asyncio
import logging
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv
import os

# Set up logging to both console and file
log_file = "fresh_kids_music_video.log"
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
    print(f"🚀 Running FRESH Music Video Pipeline for Kids...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    
    # Force regenerate to ensure fresh characters and song
    pipeline.force_regenerate = True
    
    result = await pipeline(
        idea='A group of colorful space explorers visit a candy planet and meet a friendly marshmallow giant - a catchy song about sharing, discovery, and friendship',
        style='colorful 3D kids animation pop',
        audience='kids ages 3-8',
        brand_id=None, # Ensure fresh characters are extracted and generated
        trendy=True
    )
    
    print(f"\n✅ Fresh Music Video Generation Complete!")
    print(f"🎬 Video Path: {result['video_path']}")
    print(f"🎵 Audio Path: {result['audio_path']}")
    print(f"📂 Run ID: {result['run_id']}")

if __name__ == "__main__":
    asyncio.run(main())
