import asyncio
import logging
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv
import os

# Set up logging to both console and file
log_file = "music_video_v5_resumed.log"
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
    print(f"🚀 Resuming ENHANCED Music Video Pipeline for Autocurio Kids...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with enhanced configuration
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    
    # Set force_regenerate to False to resume from existing assets (fixed frames, audio, props)
    pipeline.force_regenerate = False
    
    result = await pipeline(
        idea='Autocurio and friends learn about the magic of friendship and helping each other - a fun, catchy song about teamwork and kindness',
        style='colorful 3D kids animation pop',
        audience='kids ages 3-8',
        brand_id='intelli-verse-x',
        trendy=False
    )
    
    print(f"\n✅ Enhanced Music Video Generation Complete!")
    print(f"🎬 Video Path: {result['video_path']}")
    print(f"🎵 Audio Path: {result['audio_path']}")
    print(f"📂 Run ID: {result['run_id']}")

if __name__ == "__main__":
    asyncio.run(main())
