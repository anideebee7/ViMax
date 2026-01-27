import asyncio
import logging
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv
import os

# Set up logging to both console and file
log_file = "retry_music_video_20260126_041236_a88dd977.log"
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
    run_id = "music_video_20260126_041236_a88dd977"
    print(f"🚀 Retrying Music Video Pipeline for run: {run_id}...")
    
    # Initialize pipeline
    pipeline = MusicVideoPipeline.init_from_config('configs/pipelines/song2musicvideo.yaml')
    
    # Set the run_id to resume
    pipeline.run_id = run_id
    pipeline.working_dir = os.path.join(pipeline.base_working_dir, run_id)
    pipeline.force_regenerate = False
    
    # Read the original idea from the run metadata if needed, 
    # but here we can just use the same parameters as run_music_video_kids.py
    # as the user wants to retry that specific run.
    result = await pipeline(
        idea='Autocurio and friends learn about the magic of friendship and helping each other - a fun, catchy song about teamwork and kindness',
        style='colorful 3D kids animation pop',
        audience='kids ages 3-8',
        brand_id='intelli-verse-x',
        trendy=False
    )
    
    print(f"\n✅ Retry Complete!")
    print(f"🎬 Video Path: {result.get('video_path', 'N/A')}")
    print(f"🎵 Audio Path: {result.get('audio_path', 'N/A')}")
    print(f"📂 Run ID: {result.get('run_id', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(main())
