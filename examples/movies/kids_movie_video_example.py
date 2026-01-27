import asyncio
import logging
from pipelines.movies.short_video import ShortMovieVideoPipeline
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PREMISE = """
"The Adventures of Sparky and the Rainbow Bridge"

In the floating island city of Sky-High, everything is powered by the magical Rainbow Bridge. One morning, Sparky—a small, energetic robot with glowing green eyes and a bright orange body—wakes up to find the bridge has turned gray! Without its colors, the city's flying cars and floating gardens are starting to sink.

Sparky and his best friend Pip—a witty floating blue drone with an emoji face—must embark on a quest to find the three Lost Crystals of Color. Their journey takes them to:
1. The Crystal Cave: Where they find the Red Ruby of Energy.
2. The Whispering Forest: Where they find the Green Emerald of Growth.
3. The Cloud Castle: Where they find the Blue Sapphire of Calm.

With the help of Elder Bot, a wise old robot with a wire beard, Sparky and Pip return the crystals just in time to restore the Rainbow Bridge. They learn that even the smallest robots can do big things when they work together and stay positive.
"""

async def main():
    load_dotenv()
    
    logger.info("Initializing Idea2ShortMovieVideo Pipeline for Kids Movie...")
    # Use the end-to-end video pipeline
    pipeline = ShortMovieVideoPipeline.init_from_config("configs/pipelines/short_video.yaml")
    
    # Set to regenerate to ensure we get fresh visuals with the latest fixes
    pipeline.force_regenerate = True
    
    logger.info("Generating 5-minute animated kids movie: 'The Adventures of Sparky and the Rainbow Bridge'")
    
    result = await pipeline(
        premise=PREMISE,
        genre="animated kids adventure",
        target_duration_minutes=5,
        audience="kids (ages 4-8)",
        style="vibrant 3D animation, cute, colorful, Pixar-inspired",
        trendy=True,
        content_format="animated",
        generate_storyboard_images=True,
        generate_videos=True,
        # S3 Character Integration if we had them, but we'll let it generate new ones
        # and maintain consistency via the new compositing logic.
    )
    
    logger.info(f"Movie generation complete! Run ID: {result.get('run_id')}")
    logger.info(f"Final Video Path: {result.get('final_video_path')}")
    logger.info(f"Output directory: {pipeline.working_dir}")

if __name__ == "__main__":
    asyncio.run(main())
