"""Entry point for Idea to Kids Movie pipeline."""

import asyncio
from pipelines.movies.kids import KidsMoviePipeline


# Example usage
story_idea = """
Luna the Little Astronaut:
A curious 7-year-old girl named Luna dreams of becoming an astronaut.
When her telescope shows her a sad star that has lost its sparkle,
she embarks on an imaginative journey through the solar system
to help the star shine again, learning about friendship and believing
in yourself along the way.
"""

characters = """
- Luna: Curious, brave 7-year-old girl with big dreams
- Cosmo: Luna's friendly robot companion, a bit clumsy but loyal
- Stella: The sad star who needs help finding her sparkle
- Professor Zoom: Luna's wise grandfather who encourages her dreams
"""

moral_lesson = "Believe in yourself and help others shine"


async def main():
    pipeline = KidsMoviePipeline.init_from_config("configs/pipelines/kids_movie.yaml")
    result = await pipeline(
        story_idea=story_idea,
        age_group="6-8",  # 3-5, 6-8, or 9-12
        characters=characters,
        moral_lesson=moral_lesson,
        target_duration_minutes=22,  # Standard kids show length
        style="colorful 3D animation, Pixar-inspired",
        audience="children ages 6-8 and their families",
        generate_character_art=True,  # Generate character designs
        trendy=True,  # Include trending kids content themes
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Title: {result['script']['title']}")
    print(f"Content rating: {result['script']['content_rating']}")
    print(f"Characters: {[c['name'] for c in result['script']['characters']]}")
    print(f"Scenes: {len(result['script']['scenes'])}")
    print(f"Moral lesson: {result['script']['moral_lesson']}")
    print(f"Character art generated: {list(result['character_art'].keys())}")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")


if __name__ == "__main__":
    asyncio.run(main())
