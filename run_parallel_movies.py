import asyncio
import logging
from dotenv import load_dotenv
from pipelines.movies.short_video import ShortMovieVideoPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PREMISE_AUTOCURIO = """
"Autocurio's Cosmic Question Quest"
In the floating laboratory of Intelli-Verse-X, Autocurio - the hyper-curious robot with glowing blue eyes - discovers a mysterious portal.
Together with DotDot, NanaNova, Tinker, Whispurr, and Gloop, they embark on a quest through the Question Dimension.
"""

PREMISE_FRESH = """
"The Midnight Clockmaker"
In a steampunk city where time is literal currency, a young girl named Lyra discovers a broken pocket watch that can pause time for five seconds.
She is hunted by the 'Chronos Enforcers' - robotic guards with brass armor and ticking hearts.
Lyra must find the legendary Midnight Clockmaker to fix the watch and free the city from time-debt.
"""

async def run_pipeline(name, premise, brand_id=None, character_names=None):
    logger.info(f"STARTING PIPELINE: {name}")
    pipeline = ShortMovieVideoPipeline.init_from_config("configs/pipelines/short_video.yaml")
    pipeline.force_regenerate = True
    
    result = await pipeline(
        premise=premise,
        genre="animated adventure",
        target_duration_minutes=4,
        style="vibrant 3D animation, Pixar-inspired",
        content_format="animated",
        generate_storyboard_images=True,
        generate_videos=True,
        brand_id=brand_id,
        character_names=character_names,
    )
    logger.info(f"COMPLETED PIPELINE: {name}. Run ID: {result.get('run_id')}")

async def main():
    load_dotenv()
    # Run both in parallel
    await asyncio.gather(
        run_pipeline("AUTOCURIO_VERSION", PREMISE_AUTOCURIO, "intelli-verse-x", ["autocurio", "DotDot", "NanaNova", "Tinker", "Whispurr", "Gloop"]),
        run_pipeline("FRESH_VERSION", PREMISE_FRESH)
    )

if __name__ == "__main__":
    asyncio.run(main())
