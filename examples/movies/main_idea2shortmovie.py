"""Entry point for Idea to Short Movie pipeline."""

import asyncio
from pipelines.movies.short import ShortMoviePipeline


# Example usage
premise = """
"The Last Call"
A burned-out emergency dispatcher receives a call that will change
everything - it's from her younger self, 10 years in the past,
calling about the night that set her life on its current path.
She has 15 minutes to decide: change the past or accept the present.
"""


async def main():
    pipeline = ShortMoviePipeline.init_from_config("configs/pipelines/short_movie.yaml")
    result = await pipeline(
        premise=premise,
        genre="drama/sci-fi",
        target_duration_minutes=15,  # 5-20 minutes
        audience="film festival audiences, indie film lovers",
        style="intimate, dialogue-driven, single location",
        trendy=True,  # Include trending themes
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Story preview: {result['story'][:500]}...")
    print(f"Characters: {[c['identifier_in_scene'] for c in result['characters']]}")
    print(f"Total scenes: {len(result['script'])}")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")
    print(f"Virality score: {result['monetization_plan']['virality_score']}")


if __name__ == "__main__":
    asyncio.run(main())
