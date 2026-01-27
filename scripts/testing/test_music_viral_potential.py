#!/usr/bin/env python3
"""
Viral Potential Test Script for Music Pipelines.
Takes the generated music concepts and lyrics from the quality test,
uses ViralFinder to identify segments, and ScriptEvaluator to rate their virality.
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

from agents.producers.analysis.viral_finder import ViralFinder
from agents.producers.analysis.evaluator import ScriptEvaluator
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_viral_rating():
    # 1. Setup
    config_path = "configs/pipelines/video.yaml"
    report_path = ".working_dir/testing/music_quality_test/comparison_report.json"
    
    if not os.path.exists(report_path):
        logger.error(f"Quality test report not found at {report_path}")
        return

    if not os.path.exists(config_path):
        logger.error(f"Config not found at {config_path}")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    with open(report_path, "r") as f:
        comparison_report = json.load(f)

    # Initialize chat model
    def _resolve_env(v):
        if not isinstance(v, str): return v
        if v.startswith("${") and v.endswith("}"): return os.getenv(v[2:-1], "")
        return v

    chat_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
    chat_model = init_chat_model(**chat_args)
    
    viral_finder = ViralFinder(chat_model=chat_model)
    evaluator = ScriptEvaluator(chat_model=chat_model)
    
    viral_test_results = {}

    for audience in ["general", "kids"]:
        logger.info("\n" + "="*80)
        logger.info(f"ANALYZING VIRAL POTENTIAL: {audience.upper()}")
        logger.info("="*80)
        
        aud_data = comparison_report.get(audience)
        if not aud_data:
            continue
            
        lyrics_text = aud_data["lyrics"]["output"]["lyrics"]["lyrics"]
        shot_list = aud_data["picturization"]["concept"]["shots"]
        
        # Combine lyrics and shots for full context
        full_content = f"LYRICS:\n{lyrics_text}\n\nPICTURIZATION SHOTS:\n{json.dumps(shot_list, indent=2)}"
        
        # 2. Find Viral Segments
        logger.info(f"🔍 Finding viral segments for {audience} music video...")
        viral_analysis = await viral_finder.find_viral_segments(
            script_content=full_content,
            total_duration_seconds=120.0, # Test used 2:00 duration
            content_type="music_video"
        )
        
        logger.info(f"✅ Found {len(viral_analysis.segments)} viral segments.")
        for seg in viral_analysis.segments:
            logger.info(f"   - Segment {seg.segment_id}: {seg.title} ({seg.recommended_platform})")
            logger.info(f"     Rationale: {seg.rationale}")
        
        # 3. Evaluate Virality
        logger.info(f"⭐ Rating viral potential for {audience}...")
        viral_content_for_rating = f"VIRAL ANALYSIS REPORT:\n{json.dumps(viral_analysis.model_dump(), indent=2)}\n\nFULL SCRIPT CONTEXT:\n{full_content[:5000]}"
        
        viral_rating = await evaluator.evaluate(
            script_content=viral_content_for_rating,
            pipeline_name=f"Viral Extraction ({audience})",
            metadata={"audience": audience, "source": "music_video"}
        )
        
        logger.info(f"\n⭐ VIRAL RATING ({audience}): {viral_rating.overall_rating}/10")
        logger.info(f"   Creativity: {viral_rating.creativity}")
        logger.info(f"   Review: {viral_rating.review_comments[:200]}...")
        
        viral_test_results[audience] = {
            "analysis": viral_analysis.model_dump(),
            "rating": viral_rating.model_dump()
        }

    # 4. Save Results
    output_dir = ".working_dir/testing/music_quality_test"
    output_path = os.path.join(output_dir, "viral_rating_report.json")
    with open(output_path, "w") as f:
        json.dump(viral_test_results, f, indent=2)
        
    logger.info("\n" + "="*80)
    logger.info(f"VIRAL RATING COMPLETE. Report saved to: {output_path}")
    logger.info("="*80)
    
    # Print summary table
    print("\nVIRAL SUMMARY TABLE")
    print("-" * 60)
    print(f"{'Audience':<10} | {'Segments':<10} | {'Rating':<10} | {'Creativity':<10}")
    print("-" * 60)
    for aud in ["general", "kids"]:
        if aud in viral_test_results:
            res = viral_test_results[aud]
            print(f"{aud:<10} | {len(res['analysis']['segments']):<10} | {res['rating']['overall_rating']:<10} | {res['rating']['creativity']:<10}")
    print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run_viral_rating())
