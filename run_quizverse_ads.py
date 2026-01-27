"""
Run both Ad and Ad Banners pipelines for QuizVerse game with Autocurio character.

Generates:
1. Ad Banners - High-converting display/social ad banners (images)
2. Ad Video - Advertisement video with visuals and A/B variants
"""

import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_ad_banners():
    """Run the Ad Banners pipeline for QuizVerse."""
    from pipelines.ads.banners import AdBannersPipeline

    logger.info("=" * 70)
    logger.info("STARTING AD BANNERS PIPELINE")
    logger.info("=" * 70)

    pipeline = AdBannersPipeline.init_from_config("configs/pipelines/ad_banners.yaml")
    pipeline.force_regenerate = True  # Force fresh generation

    result = await pipeline(
        brand_or_game="QuizVerse",
        entity_type="game",
        brief="Promote QuizVerse - the ultimate trivia game app. Highlight daily challenges, multiplayer modes, brain-teasing questions, and compete with friends worldwide.",
        audience="Mobile gamers 18-35, trivia enthusiasts, casual players, knowledge seekers",
        campaign_goal="App installs and daily active users",
        platforms="Google Display, Meta (Facebook/Instagram), TikTok, Programmatic",
        trendy=True,
        game_id="quiz-verse",
        brand_id="intelli-verse-x",
        character_ids=["autocurio"],  # Feature Autocurio in banners
        feature_characters_in_banners=True,
        num_concepts=5,  # 5 different creative concepts
        sizes=[
            "medium_rectangle",    # 300x250 - IAB standard
            "leaderboard",         # 728x90 - Website headers
            "facebook_landscape",  # 1200x628 - Facebook/Instagram feed
            "square_social",       # 1080x1080 - Instagram/TikTok
            "portrait_story",      # 1080x1350 - Stories
            "mobile_banner",       # 320x50 - Mobile apps
        ],
        additional="Feature Autocurio (the cute black robot with blue glowing eyes) as the mascot. Make CTAs compelling for app installs. Use purple/blue color scheme matching QuizVerse branding.",
    )

    logger.info("=" * 70)
    logger.info("AD BANNERS COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Run ID: {result['run_id']}")
    logger.info(f"Entity: {result['entity_name']} ({result['entity_type']})")
    logger.info(f"Banners: {len(result['banners'])} images generated")
    logger.info(f"Sizes: {result['sizes_generated']}")
    logger.info(f"Characters featured: {result.get('characters_featured', [])}")
    
    return result


async def run_ad_video():
    """Run the Ad Video pipeline for QuizVerse."""
    from pipelines.ads.video import AdPipeline

    logger.info("=" * 70)
    logger.info("STARTING AD VIDEO PIPELINE")
    logger.info("=" * 70)

    pipeline = AdPipeline.init_from_config("configs/pipelines/ad.yaml")
    pipeline.force_regenerate = True  # Force fresh generation

    result = await pipeline(
        brand="IntelliVerse X",
        product="QuizVerse - Ultimate Trivia Game",
        campaign_goal="Drive app installs and engagement",
        audience="Mobile gamers 18-35, trivia and casual game enthusiasts",
        ad_format="30s",
        generate_visuals=True,
        generate_videos=True,
        trendy=True,
        auto_ideate=False,  # We provide the content directly
        brand_id="intelli-verse-x",
        game_id="quiz-verse",
        character_ids=["autocurio"],  # Feature Autocurio in the ad
        feature_characters=True,
    )

    logger.info("=" * 70)
    logger.info("AD VIDEO COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Run ID: {result['run_id']}")
    logger.info(f"Brand: {result['brand']}")
    logger.info(f"Product: {result['product']}")
    logger.info(f"Primary hook: {result['ad_script']['primary_variant']['hook'][:100]}...")
    logger.info(f"A/B variants: {len(result['ad_script']['ab_variants'])}")
    logger.info(f"Visuals generated: {len(result.get('variant_visuals', {}))}")
    logger.info(f"Videos generated: {len(result.get('variant_videos', {}))}")
    logger.info(f"Characters featured: {result.get('characters_featured', [])}")
    
    return result


async def main():
    """Run both pipelines."""
    start_time = datetime.now()
    
    logger.info("=" * 70)
    logger.info("QUIZVERSE AD CAMPAIGN GENERATION")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Running both Ad Banners and Ad Video pipelines for QuizVerse")
    logger.info("with Autocurio character for brand consistency")
    logger.info("")

    # Run both pipelines
    banners_result = await run_ad_banners()
    video_result = await run_ad_video()

    end_time = datetime.now()
    duration = end_time - start_time

    logger.info("")
    logger.info("=" * 70)
    logger.info("ALL PIPELINES COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Duration: {duration}")
    logger.info("")
    logger.info("Summary:")
    logger.info(f"  Ad Banners: {len(banners_result['banners'])} images")
    logger.info(f"  Ad Video: {len(video_result.get('variant_visuals', {}))} visuals, {len(video_result.get('variant_videos', {}))} videos")
    logger.info("")
    logger.info("Output directories:")
    logger.info(f"  Banners: .working_dir/adbanners/{banners_result['run_id']}/")
    logger.info(f"  Videos: .working_dir/ad/{video_result['run_id']}/")


if __name__ == "__main__":
    asyncio.run(main())
