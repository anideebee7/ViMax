import asyncio
from pipelines.base.idea import VideoPipeline


# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
    """
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
user_requirement = \
    """
Create a short educational video featuring Autocurio, DotDot, and Tinker on a hilltop at sunset.
The video should show the characters having a conversation about why the sky is blue.
Use the provided character images for consistency. Keep it kid-friendly and educational.
The scene should capture the beautiful sunset atmosphere with warm lighting.
"""
style = "3D animated cartoon style, vibrant colors, kid-friendly, warm sunset lighting, educational and playful tone"


async def main():
    pipeline = VideoPipeline.init_from_config(
        config_path="configs/pipelines/video.yaml")
    await pipeline(idea=idea, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
