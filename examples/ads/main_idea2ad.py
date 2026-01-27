"""Entry point for Idea to Ad pipeline."""

import asyncio
from pipelines.ads.video import AdPipeline


# Example usage
brand = "TechGlow"
product = "Smart LED Light Bulb with Voice Control"
campaign_goal = "Drive product awareness and website visits"
audience = "Tech-savvy millennials, homeowners interested in smart home automation"
ad_format = "30s"  # 6s, 15s, 30s, or 60s


async def main():
    pipeline = AdPipeline.init_from_config("configs/pipelines/ad.yaml")
    result = await pipeline(
        brand=brand,
        product=product,
        campaign_goal=campaign_goal,
        audience=audience,
        ad_format=ad_format,
        generate_visuals=True,  # Generate visual frames
        generate_videos=False,  # Skip video generation (faster)
        trendy=True,  # Incorporate trending ad styles
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Primary variant: {result['ad_script']['primary_variant']['hook']}")
    print(f"A/B variants: {len(result['ad_script']['ab_variants'])}")
    print(f"Recommended platforms: {result['ad_script']['platform_recommendations']}")
    print(f"Monetization strategy: {result['monetization_plan']['marketing_strategy'][:100]}...")


if __name__ == "__main__":
    asyncio.run(main())
