"""Entry point for Idea to Documentary pipeline."""

import asyncio
from pipelines.content.documentary import DocumentaryPipeline


# Example usage
topic = """
The Rise of AI in Creative Industries:
How artificial intelligence is transforming art, music, writing, and film,
and what it means for human creativity.
"""


async def main():
    pipeline = DocumentaryPipeline.init_from_config("configs/pipelines/documentary.yaml")
    result = await pipeline(
        topic=topic,
        target_duration_minutes=30,  # 10-60 minutes
        research_depth="moderate",  # light, moderate, deep
        audience="tech enthusiasts and creatives",
        style="balanced and thought-provoking",
        trendy=True,  # Incorporate current AI news
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Title: {result['script']['title']}")
    print(f"Thesis: {result['script']['thesis']}")
    print(f"Total segments: {len(result['script']['segments'])}")
    print(f"Narration saved to: {result['narration_path']}")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")


if __name__ == "__main__":
    asyncio.run(main())
