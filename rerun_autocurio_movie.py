#!/usr/bin/env python3
"""
Generate a 5-minute kids movie featuring Autocurio and Intelli-verse-x characters.
Resuming with all character consistency and background removal fixes.
"""
import asyncio
import logging
from dotenv import load_dotenv

from pipelines.movies.short_video import ShortMovieVideoPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PREMISE = """
"Autocurio's Cosmic Question Quest"

In the floating laboratory of Intelli-Verse-X, Autocurio - the hyper-curious robot with glowing blue eyes - discovers a mysterious portal that leads to the "Question Dimension" where all unanswered questions float as colorful bubbles.

When Autocurio accidentally pops the "Why is the sky blue?" bubble, it causes a chain reaction that starts popping ALL the question bubbles! Without questions, curiosity itself starts to fade from the world.

Autocurio must team up with his friends:
- DotDot: The witty spherical drone with an emoji face who can fly fast
- NanaNova: The holographic knowledge keeper who knows facts about everything
- Tinker: The inventive robot who can build gadgets from anything
- Whispurr: The gentle sound-manipulating cat-bot who speaks in whispers
- Gloop: The transparent gelatinous alien who can stretch and bounce

Together, they embark on a quest through the Question Dimension to catch and restore all the escaped questions before curiosity disappears forever!
"""

async def main():
    load_dotenv()
    
    logger.info("=" * 60)
    logger.info("Rerunning Autocurio's Cosmic Question Quest with full fixes")
    logger.info("=" * 60)
    
    # Initialize the end-to-end video pipeline
    pipeline = ShortMovieVideoPipeline.init_from_config("configs/pipelines/short_video.yaml")
    
    # Ensure we force regenerate to use the new prompt sanitization and background fixes
    pipeline.force_regenerate = True
    
    result = await pipeline(
        premise=PREMISE,
        genre="animated kids adventure comedy",
        target_duration_minutes=5,
        audience="kids (ages 4-10) and families",
        style="vibrant 3D animation, Pixar-inspired, colorful, playful, educational",
        trendy=False,
        content_format="animated",
        generate_storyboard_images=True,
        generate_videos=True,
        # S3 Character Integration
        brand_id="intelli-verse-x",
        character_names=["autocurio", "DotDot", "NanaNova", "Tinker", "Whispurr", "Gloop"],
    )
    
    logger.info("=" * 60)
    logger.info("Movie generation complete!")
    logger.info("=" * 60)
    logger.info(f"Run ID: {result.get('run_id')}")
    logger.info(f"Final Video Path: {result.get('final_video_path')}")
    
    return result

if __name__ == "__main__":
    asyncio.run(main())
