import asyncio
from pipelines.music.song import SongPipeline


idea = """
Theme: Curiosity meets art in a futuristic world.
Characters: Autocurio, Nana Nova, Tinker.
"""

user_requirement = """
Create an uplifting, memorable short song for a kids-friendly audience.
Include a hook and a hopeful ending.
"""

style = "Upbeat 3D animated cartoon vibe, colorful and playful"


async def main():
    pipeline = SongPipeline.init_from_config("configs/pipelines/song.yaml")
    await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
        audience="kids",
        trendy=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
