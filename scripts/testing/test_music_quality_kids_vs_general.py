#!/usr/bin/env python3
"""
Music Pipeline Quality Test - Kids vs General Audience.
Tests lyrics generation and music video directing (picturization) using self-ideation.
Evaluates results for both "Kids" and "General" audiences to verify specialized logic.
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

from pipelines.music.lyrics import LyricsPipeline
from pipelines.music.video import MusicVideoPipeline
from agents.producers.analysis.evaluator import ScriptEvaluator
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_quality_test():
    # 1. Setup
    config_path = "configs/pipelines/video.yaml"
    if not os.path.exists(config_path):
        logger.error(f"Config not found at {config_path}")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Initialize chat model for evaluator
    def _resolve_env(v):
        if not isinstance(v, str): return v
        if v.startswith("${") and v.endswith("}"): return os.getenv(v[2:-1], "")
        return v

    chat_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
    chat_model = init_chat_model(**chat_args)
    
    evaluator = ScriptEvaluator(chat_model=chat_model)
    
    test_results = {
        "general": {},
        "kids": {}
    }

    audiences = ["general", "kids"]
    
    for aud in audiences:
        logger.info("\n" + "="*80)
        logger.info(f"TESTING AUDIENCE: {aud.upper()}")
        logger.info("="*80)
        
        # --- PHASE 1: SELF-IDEATION & LYRICS ---
        logger.info(f"--- Phase 1: Self-Ideation & Lyrics ({aud}) ---")
        lyrics_pipeline = LyricsPipeline.init_from_config(config_path)
        lyrics_pipeline.working_dir = f".working_dir/testing/music_quality_test/{aud}/lyrics"
        os.makedirs(lyrics_pipeline.working_dir, exist_ok=True)
        
        # Test self-ideation + lyrics
        # We'll use "creativity" mode for general and "creativity" for kids too but with audience flag
        lyrics_output = await lyrics_pipeline(
            auto_ideate=True,
            ideation_mode="creativity",
            audience=aud,
            style="cinematic pop" if aud == "general" else "whimsical orchestral pop"
        )
        
        lyrics_draft = lyrics_output["lyrics"]
        lyrics_content = f"TITLE: {lyrics_draft['title']}\nGENRE: {lyrics_draft.get('genre')}\nMOOD: {lyrics_draft.get('mood')}\n\n{lyrics_draft['lyrics']}"
        
        # Evaluate Lyrics
        lyrics_rating = await evaluator.evaluate(
            script_content=lyrics_content,
            pipeline_name=f"Idea2Lyrics ({aud})",
            metadata={"audience": aud, "auto_ideated": True}
        )
        
        logger.info(f"⭐ LYRICS RATING ({aud}): {lyrics_rating.overall_rating}/10")
        logger.info(f"   Creativity: {lyrics_rating.creativity}")
        logger.info(f"   Review: {lyrics_rating.review_comments[:200]}...")
        
        test_results[aud]["lyrics"] = {
            "output": lyrics_output,
            "rating": lyrics_rating.model_dump()
        }
        
        # --- PHASE 2: PICTURIZATION (SHOT LIST) ---
        logger.info(f"--- Phase 2: Picturization / Music Video Concept ({aud}) ---")
        video_pipeline = MusicVideoPipeline.init_from_config(config_path)
        video_pipeline.working_dir = f".working_dir/testing/music_quality_test/{aud}/video"
        os.makedirs(video_pipeline.working_dir, exist_ok=True)
        
        # Run only directing agent part
        is_kids = (aud == "kids")
        kids_context = "KIDS ANIMATED MUSIC VIDEO: G-rated, colorful, safe." if is_kids else ""
        
        concept = await video_pipeline.music_video_director.direct_music_video(
            song_title=lyrics_draft["title"],
            lyrics=lyrics_draft["lyrics"],
            genre=lyrics_draft.get("genre") or "Pop",
            mood=lyrics_draft.get("mood") or "Dynamic",
            song_structure="Duration: 120s (2:00)",
            style="colorful 3D kids animation" if is_kids else "cinematic music video",
            audience=aud,
            additional_context=kids_context
        )
        
        # Evaluate Music Video Concept
        concept_content = json.dumps(concept.model_dump(), indent=2)
        concept_rating = await evaluator.evaluate(
            script_content=concept_content,
            pipeline_name=f"Idea2MusicVideo Picturization ({aud})",
            metadata={"audience": aud, "song": lyrics_draft["title"]}
        )
        
        logger.info(f"⭐ PICTURIZATION RATING ({aud}): {concept_rating.overall_rating}/10")
        logger.info(f"   Creativity: {concept_rating.creativity}")
        logger.info(f"   Review: {concept_rating.review_comments[:200]}...")
        
        test_results[aud]["picturization"] = {
            "concept": concept.model_dump(),
            "rating": concept_rating.model_dump()
        }

    # Save final report
    report_dir = ".working_dir/testing/music_quality_test"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "comparison_report.json")
    with open(report_path, "w") as f:
        json.dump(test_results, f, indent=2)
    
    logger.info("\n" + "="*80)
    logger.info(f"QUALITY TEST COMPLETE. Comparison report saved to: {report_path}")
    logger.info("="*80)
    
    # Print summary table
    print("\nSUMMARY TABLE")
    print("-" * 60)
    print(f"{'Audience':<10} | {'Phase':<15} | {'Rating':<10} | {'Creativity':<10}")
    print("-" * 60)
    for aud in audiences:
        lr = test_results[aud]["lyrics"]["rating"]
        pr = test_results[aud]["picturization"]["rating"]
        print(f"{aud:<10} | {'Lyrics':<15} | {lr['overall_rating']:<10} | {lr['creativity']:<10}")
        print(f"{aud:<10} | {'Picturization':<15} | {pr['overall_rating']:<10} | {pr['creativity']:<10}")
    print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run_quality_test())
