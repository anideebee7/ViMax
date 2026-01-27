import asyncio
import logging
from pipelines.movies.short_video import ShortMovieVideoPipeline
from dotenv import load_dotenv
import os
from datetime import datetime

# Set up logging to both console and file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"short_movie_limited_{timestamp}.log"
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
    print(f"🚀 Running Short Movie Pipeline (Limited: 1 scene, 2 shots)...")
    print(f"📝 Logs are being saved to: {os.path.abspath(log_file)}")
    
    # Initialize pipeline with standard configuration
    pipeline = ShortMovieVideoPipeline.init_from_config('configs/pipelines/short_video.yaml')
    
    # Force regenerate to ensure fresh generation
    pipeline.force_regenerate = True
    
    # Monkey patch to limit shots to 2 per scene
    # Patch the storyboard_artist to return max 2 shots
    original_design_storyboard = pipeline.storyboard_artist.design_storyboard
    
    async def limited_design_storyboard(*args, **kwargs):
        shots = await original_design_storyboard(*args, **kwargs)
        # Limit to 2 shots
        limited_shots = (shots or [])[:2]
        print(f"   Limited storyboard to {len(limited_shots)} shots (from {len(shots or [])})")
        return limited_shots
    
    pipeline.storyboard_artist.design_storyboard = limited_design_storyboard
    
    # Patch the pipeline's __call__ method to also limit shots after they're loaded from cache
    # This ensures that even if shots are loaded from existing storyboard_design.json, they're limited to 2
    original_call = pipeline.__call__
    
    async def patched_call(*args, **kwargs):
        # Call the original method but intercept shots loading
        import json
        import os
        
        # Store original method references
        original_json_load = json.load
        
        def patched_json_load(fp):
            data = original_json_load(fp)
            # If this is a shots list (list of dicts with visual_desc or similar), limit it
            if isinstance(data, list) and len(data) > 0:
                # Check if it looks like shot data (has visual_desc, visual_description, etc.)
                first_item = data[0] if data else {}
                if isinstance(first_item, dict) and any(key in first_item for key in ['visual_desc', 'visual_description', 'visual_desc']):
                    if len(data) > 2:
                        print(f"   Limiting cached shots from {len(data)} to 2")
                        return data[:2]
            return data
        
        # Temporarily patch json.load during pipeline execution
        json.load = patched_json_load
        try:
            result = await original_call(*args, **kwargs)
        finally:
            json.load = original_json_load
        
        return result
    
    pipeline.__call__ = patched_call
    
    print(f"\n📋 Configuration:")
    print(f"   - Max scenes: 1")
    print(f"   - Max shots per scene: 2")
    print(f"   - Force regenerate: True")
    print(f"\n🎬 Starting pipeline...\n")
    
    result = await pipeline(
        premise="A young artist discovers that their paintings come to life at midnight, but only for one hour. They must decide whether to keep this secret or share it with the world.",
        genre="fantasy drama",
        target_duration_minutes=5,
        audience="general audience, fantasy lovers",
        style="cinematic, magical realism, warm lighting",
        trendy=False,
        content_format="animated",
        generate_storyboard_images=True,
        generate_videos=True,
        max_scenes=1,  # Limit to 1 scene
    )
    
    print(f"\n✅ Short Movie Pipeline Complete!")
    print(f"📂 Run ID: {result.get('run_id', 'N/A')}")
    print(f"📁 Working Directory: {pipeline.working_dir}")
    print(f"🎬 Scenes processed: {len(result.get('scenes', []))}")
    
    # Count shots in the first scene
    if result.get('scenes'):
        first_scene = result['scenes'][0]
        shots_count = len(first_scene.get('storyboard_frames', []))
        print(f"📸 Shots in scene 1: {shots_count}")

if __name__ == "__main__":
    asyncio.run(main())
