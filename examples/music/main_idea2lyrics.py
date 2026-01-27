"""Entry point for Idea to Lyrics pipeline."""

import asyncio
from pipelines.music.lyrics import LyricsPipeline


# Example usage
idea = """
Theme: Finding hope in difficult times
Emotion: Uplifting, inspirational
Setting: Urban, modern
"""

user_requirement = """
Create lyrics for a pop song with a memorable chorus.
Include imagery of light breaking through darkness.
Suitable for radio play.
"""

style = "Contemporary pop with emotional depth"


async def main():
    pipeline = LyricsPipeline.init_from_config("configs/pipelines/lyrics.yaml")
    result = await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
        genre="Pop",
        mood="Hopeful",
        audience="young adults",
        trendy=True,  # Incorporate trending themes
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Title: {result['lyrics']['title']}")
    print(f"Lyrics saved to: {result['lyrics_path']}")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")


if __name__ == "__main__":
    asyncio.run(main())
