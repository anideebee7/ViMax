"""Entry point for Idea to Ad Banners pipeline.

Generates high-converting ad banner images for brands and games.
Supports S3 references (brand_id, game_id), trends, and multiple
sizes (IAB, Google Display, Meta). Targets 25%+ CTR.
"""

import asyncio
import logging
from pipelines.ads.banners import AdBannersPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def main():
    pipeline = AdBannersPipeline.init_from_config("configs/pipelines/adbanners.yaml")

    print("🚀 Ad Banners Pipeline – High-converting display & social banners")
    print("   Entity: QuizVerse (game) from S3")
    print("   Variants: creative, trend, high_converting")
    print("   Sizes: medium_rectangle, facebook_landscape, square_social, etc.")
    print()

    # Example: game from S3
    result = await pipeline(
        brand_or_game="QuizVerse",
        entity_type="game",
        brief="Promote the trivia game for app installs. Highlight daily challenges and multiplayer.",
        audience="Mobile gamers 18–35, trivia and casual players",
        campaign_goal="App installs and in-app engagement",
        platforms="Google Display, Meta (Facebook/Instagram), TikTok",
        trendy=True,
        game_id="quiz-verse",
        brand_id="intelli-verse-x",
        num_concepts=4,
        sizes=["medium_rectangle", "leaderboard", "facebook_landscape", "square_social", "portrait_story"],
        additional="Use brand character Autocurio if it helps; keep CTA clear.",
    )

    print()
    print("=" * 60)
    print("📋 AD BANNERS COMPLETE")
    print("=" * 60)
    print(f"Run ID: {result['run_id']}")
    print(f"Entity: {result['entity_name']} ({result['entity_type']})")
    print(f"Banners: {len(result['banners'])} images")
    print(f"Sizes: {result['sizes_generated']}")
    print()
    print("Manifest (path, style, size, headline, CTA):")
    for m in result.get("manifest", [])[:12]:
        print(f"  {m['path']}")
        print(f"    {m['style']} | {m['size']} {m['width']}x{m['height']} | \"{m['headline']}\" | {m['cta']}")
    if len(result.get("manifest", [])) > 12:
        print(f"  ... and {len(result['manifest']) - 12} more")
    print()
    print(f"Output: {result.get('run_id', '')} in .working_dir/adbanners/")


if __name__ == "__main__":
    asyncio.run(main())
