"""
Shorts Mode - Generate crisp, short-form videos (15-30 seconds)
Optimized for social media shorts with vertical aspect ratio (9:16)
"""
import asyncio
from pipelines import VideoPipeline


async def main():
    pipeline = VideoPipeline.init_from_config(
        config_path="configs/pipelines/video_shorts.yaml")

    # Your idea/story here
    idea = """
    Setting: Hilltop, sunset.
    Characters: Autocurio, DotDot, Tinker.

    Script:
    Autocurio scans the sky, blue glow reflecting in his eyes.
    Autocurio: "DotDot, why is the sky… blue?"
    DotDot: (smirking) "Because it's shy about being pink?"
    Tinker giggles, holding up a prism.
    Tinker: "It's about how light scatters, Curio. Blue travels further!"
    Autocurio: (processing) "So… curiosity reveals hidden colors. Data logged!"
    Curio's chest glows with a rainbow emoji.
    Closing line:
    Autocurio: "The world is a prism. Stay curious, see more!"
    """

    # User requirements for the video
    user_requirement = """
    Target audience: Kids (5-12 years old)
    Style: Fun, educational, colorful
    Tone: Playful and curious
    """

    # Visual style
    style = "3D animated, Pixar-style, vibrant colors, warm sunset lighting"

    final_video_path = await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
    )

    print(f"\n✅ Shorts video generated: {final_video_path}")


if __name__ == "__main__":
    asyncio.run(main())
