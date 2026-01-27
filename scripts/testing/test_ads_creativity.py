#!/usr/bin/env python3
"""
Ads Creativity Test Script - Phased Testing.
Tests ideation and scripting phases for Ad Banners and Ad Videos without triggering generation.
Evaluates results using ScriptEvaluator.
"""
import asyncio
import os
import sys
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.ads.banners import AdBannersPipeline
from pipelines.ads.video import AdPipeline
from agents.producers.analysis.evaluator import ScriptEvaluator
from utils.pipeline.entity_resolver import resolve_s3_entities
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_ads_audit(brand_id: str = "intelli-verse-x"):
    # 1. Setup
    config_path = "configs/pipelines/video.yaml"
    if not os.path.exists(config_path):
        logger.error(f"Config not found at {config_path}")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Initialize chat model
    def _resolve_env(v):
        if not isinstance(v, str): return v
        if v.startswith("${") and v.endswith("}"): return os.getenv(v[2:-1], "")
        return v

    chat_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
    chat_model = init_chat_model(**chat_args)
    
    evaluator = ScriptEvaluator(chat_model=chat_model)
    
    # 2. Resolve Brand Context
    logger.info(f"🔍 Resolving S3 entities for brand: {brand_id}")
    resolution = resolve_s3_entities(texts=[f"@brand:{brand_id}"], brand_hint=brand_id)
    brand_name = resolution.get("brand_data", {}).get("name", brand_id)
    
    # 3. Test Ad Banners Ideation
    logger.info("\n" + "="*60)
    logger.info(f"PHASE 1: Ad Banners Ideation for {brand_name}")
    logger.info("="*60)
    
    banner_pipeline = AdBannersPipeline.init_from_config(config_path)
    banner_pipeline.working_dir = f".working_dir/testing/ads_audit/banners_{brand_id}"
    os.makedirs(banner_pipeline.working_dir, exist_ok=True)
    
    # Run only ideation
    ideation = await banner_pipeline.ideator.ideate(
        brand_or_game=brand_name,
        entity_type="brand",
        entity_context=banner_pipeline._build_entity_context(resolution, brand_id, None),
        brief="Promote the IntelliVerse X ecosystem across all its flavors (Tech, Gaming, Luxury, Auto, Health).",
        audience="Curious professionals, gamers, and lifestyle enthusiasts.",
        campaign_goal="Brand awareness and ecosystem exploration.",
        platforms="Google Display, Meta Social",
        num_concepts=3
    )
    
    # Evaluate Banners
    banner_content = json.dumps(ideation.model_dump(), indent=2)
    banner_rating = await evaluator.evaluate(
        script_content=banner_content,
        pipeline_name="Idea2AdBanners (Ideation)",
        metadata={"brand": brand_name, "goal": "Brand Awareness"}
    )
    
    logger.info(f"\n⭐ BANNER IDEATION RATING: {banner_rating.overall_rating}/10")
    logger.info(f"   Creativity: {banner_rating.creativity}")
    logger.info(f"   Comments: {banner_rating.review_comments}")
    
    # 4. Test Ad Video Scripting
    logger.info("\n" + "="*60)
    logger.info(f"PHASE 2: Ad Video Scripting for {brand_name}")
    logger.info("="*60)
    
    video_pipeline = AdPipeline.init_from_config(config_path)
    video_pipeline.working_dir = f".working_dir/testing/ads_audit/video_{brand_id}"
    os.makedirs(video_pipeline.working_dir, exist_ok=True)
    
    # Run only scripting
    ad_script = await video_pipeline.ad_copywriter.write_ad_script(
        brand=brand_name,
        product="IntelliVerse X Content Ecosystem",
        campaign_goal="awareness",
        audience="General digital audience",
        ad_format="30s",
        additional_context=banner_pipeline._build_entity_context(resolution, brand_id, None)
    )
    
    # Evaluate Video Script
    video_content = json.dumps(ad_script.model_dump(), indent=2)
    video_rating = await evaluator.evaluate(
        script_content=video_content,
        pipeline_name="Idea2Ad (Scripting)",
        metadata={"brand": brand_name, "format": "30s Video"}
    )
    
    logger.info(f"\n⭐ VIDEO SCRIPT RATING: {video_rating.overall_rating}/10")
    logger.info(f"   Creativity: {video_rating.creativity}")
    logger.info(f"   Comments: {video_rating.review_comments}")
    
    # Save audit report
    audit_report = {
        "brand": brand_id,
        "banner_ideation": ideation.model_dump(),
        "banner_rating": banner_rating.model_dump(),
        "video_script": ad_script.model_dump(),
        "video_rating": video_rating.model_dump()
    }
    
    report_path = f"{banner_pipeline.working_dir}/audit_report.json"
    with open(report_path, "w") as f:
        json.dump(audit_report, f, indent=2)
    
    logger.info("\n" + "="*60)
    logger.info(f"AUDIT COMPLETE. Report saved to: {report_path}")
    logger.info("="*60)

if __name__ == "__main__":
    asyncio.run(run_ads_audit())
