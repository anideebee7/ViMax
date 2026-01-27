"""Entry point for Idea to Movie pipeline."""

import asyncio
from pipelines.movies.standard import MoviePipeline


# Example usage
premise = """
"Echoes of Tomorrow"
In 2045, a brilliant neuroscientist discovers she can access memories
of alternate timelines - versions of her life she never lived.
As she becomes obsessed with a timeline where her deceased daughter
is still alive, she must choose between the life she has and the
life she could have had, before the boundaries between realities
collapse entirely.
"""


async def main():
    pipeline = MoviePipeline.init_from_config("configs/pipelines/movie.yaml")
    result = await pipeline(
        premise=premise,
        genre="sci-fi drama",
        target_runtime_minutes=110,  # 60-180 minutes
        audience="PG-13, general audiences",
        style="visually ambitious, emotionally grounded, Nolan-esque",
        trendy=True,  # Include trending themes
    )
    print(f"Run ID: {result['run_id']}")
    print(f"\n=== STORY SYNOPSIS ===")
    print(result['story'][:1000])
    print("\n=== CHARACTERS ===")
    for c in result['characters'][:5]:
        print(f"  - {c['identifier_in_scene']}: {c.get('static_features', 'N/A')[:100]}...")
    print(f"\n=== ACT BREAKDOWN ===")
    for act_name, act_info in result['act_breakdown'].items():
        print(f"  {act_info['name']}: {act_info['duration_percent']}% ({len(act_info['scenes'])} scenes)")
    print(f"\n=== MONETIZATION ===")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")
    print(f"Marketing strategy: {result['monetization_plan']['marketing_strategy'][:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
