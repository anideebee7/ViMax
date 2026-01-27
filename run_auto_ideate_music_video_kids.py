import asyncio
import logging
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv
import os
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"auto_ideate_kids_music_video_{timestamp}.log"
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
    print(f"🚀 Running AUTO-IDEATE Music Video Pipeline for Kids...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    
    # Force regenerate to ensure fresh characters and song
    pipeline.force_regenerate = True
    
    print(f"\n📋 Configuration:")
    print(f"   - Auto-ideate: True")
    print(f"   - Audience: kids ages 3-8")
    print(f"   - Style: colorful 3D kids animation pop")
    print(f"   - Trends: Enabled")
    print(f"   - Fresh characters: Yes (no S3 brand/game IDs)")
    print(f"   - Force regenerate: True")
    print(f"\n🎬 Starting pipeline...\n")
    
    result = await pipeline(
        auto_ideate=True,
        ideation_mode="creativity",  # Use creativity mode for kids content
        style='colorful 3D kids animation pop',
        audience='kids ages 3-8',
        brand_id=None,  # Ensure fresh characters are extracted and generated
        trendy=True
    )
    
    print(f"\n✅ Auto-Ideate Music Video Generation Complete!")
    print(f"🎬 Video Path: {result.get('video_path', 'N/A')}")
    print(f"🎵 Audio Path: {result.get('audio_path', 'N/A')}")
    print(f"📂 Run ID: {result.get('run_id', 'N/A')}")
    print(f"📁 Working Directory: {pipeline.working_dir}")

if __name__ == "__main__":
    asyncio.run(main())
