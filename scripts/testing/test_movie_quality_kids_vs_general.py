#!/usr/bin/env python3
"""
Movie Pipeline Quality Test - Kids vs General Audience.
Tests screenwriting and movie directing (shot list/picturization) using self-ideation.
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

from pipelines.movies.standard import MoviePipeline
from pipelines.movies.kids import KidsMoviePipeline
from agents.producers.analysis.evaluator import ScriptEvaluator
from agents.producers.analysis.viral_finder import ViralFinder
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_movie_quality_test():
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
    viral_finder = ViralFinder(chat_model=chat_model)
    
    test_results = {
        "general": {},
        "kids": {}
    }

    # --- TEST 1: GENERAL MOVIE ---
    logger.info("\n" + "="*80)
    logger.info("TESTING AUDIENCE: GENERAL (Feature Film)")
    logger.info("="*80)
    
    movie_pipeline = MoviePipeline.init_from_config(config_path)
    movie_pipeline.working_dir = ".working_dir/testing/movie_quality_test/general"
    os.makedirs(movie_pipeline.working_dir, exist_ok=True)
    
    # Run self-ideation + screenwriting (Phase 1)
    logger.info("--- Phase 1: Self-Ideation & Screenwriting (General) ---")
    movie_output = await movie_pipeline(
        auto_ideate=True,
        ideation_mode="creativity",
        target_runtime_minutes=60, # 1 hour movie for test
        max_scenes_to_generate=0, # Stop before visual generation
        generate_scene_frames=False,
        generate_videos=False
    )
    
    script_content = f"STORY:\n{movie_output['story']}\n\nFULL SCRIPT:\n{json.dumps(movie_output['script'], indent=2)}"
    
    # Evaluate Script
    movie_rating = await evaluator.evaluate(
        script_content=script_content,
        pipeline_name="Idea2Movie (General)",
        metadata={"audience": "general", "auto_ideated": True}
    )
    
    logger.info(f"⭐ MOVIE SCRIPT RATING: {movie_rating.overall_rating}/10")
    logger.info(f"   Creativity: {movie_rating.creativity}")
    
    # Analyze Viral Potential
    logger.info("--- Phase 2: Viral Potential (General) ---")
    viral_analysis = await viral_finder.find_viral_segments(
        script_content=script_content,
        total_duration_seconds=3600.0,
        content_type="movie"
    )
    
    viral_rating = await evaluator.evaluate(
        script_content=json.dumps(viral_analysis.model_dump(), indent=2),
        pipeline_name="Movie Viral Extraction (General)",
        metadata={"audience": "general"}
    )
    
    test_results["general"] = {
        "script_rating": movie_rating.model_dump(),
        "viral_rating": viral_rating.model_dump(),
        "viral_segments": viral_analysis.model_dump()
    }

    # --- TEST 2: KIDS MOVIE ---
    logger.info("\n" + "="*80)
    logger.info("TESTING AUDIENCE: KIDS (Animated Film)")
    logger.info("="*80)
    
    kids_pipeline = KidsMoviePipeline.init_from_config(config_path)
    kids_pipeline.working_dir = ".working_dir/testing/movie_quality_test/kids"
    os.makedirs(kids_pipeline.working_dir, exist_ok=True)
    
    # Run self-ideation + kids screenwriting
    logger.info("--- Phase 1: Self-Ideation & Screenwriting (Kids) ---")
    kids_output = await kids_pipeline(
        auto_ideate=True,
        ideation_mode="creativity",
        age_group="6-8",
        target_duration_minutes=15, # 15 min kids short/movie
        generate_scene_frames=False,
        generate_videos=False
    )
    
    kids_script_content = f"SYNOPSIS:\n{kids_output['script']['synopsis']}\nVISION:\n{kids_output['script'].get('director_vision', 'N/A')}\nMORAL:\n{kids_output['script']['moral_lesson']}\n\nSCRIPT:\n{json.dumps(kids_output['script']['scenes'], indent=2)}"
    
    # Evaluate Kids Script
    kids_rating = await evaluator.evaluate(
        script_content=kids_script_content,
        pipeline_name="Idea2KidsMovie",
        metadata={"audience": "kids", "auto_ideated": True}
    )
    
    logger.info(f"⭐ KIDS MOVIE RATING: {kids_rating.overall_rating}/10")
    logger.info(f"   Creativity: {kids_rating.creativity}")
    
    # Analyze Viral Potential (Kids)
    logger.info("--- Phase 2: Viral Potential (Kids) ---")
    kids_viral_analysis = await viral_finder.find_viral_segments(
        script_content=kids_script_content,
        total_duration_seconds=900.0,
        content_type="kids_movie"
    )
    
    kids_viral_rating = await evaluator.evaluate(
        script_content=json.dumps(kids_viral_analysis.model_dump(), indent=2),
        pipeline_name="Movie Viral Extraction (Kids)",
        metadata={"audience": "kids"}
    )
    
    test_results["kids"] = {
        "script_rating": kids_rating.model_dump(),
        "viral_rating": kids_viral_rating.model_dump(),
        "viral_segments": kids_viral_analysis.model_dump()
    }

    # Final Summary
    report_path = ".working_dir/testing/movie_quality_test/movie_comparison_report.json"
    with open(report_path, "w") as f:
        json.dump(test_results, f, indent=2)
        
    print("\n" + "="*60)
    print("MOVIE PIPELINES QUALITY SUMMARY")
    print("="*60)
    print(f"{'Audience':<10} | {'Script Rating':<15} | {'Viral Rating':<15}")
    print("-" * 60)
    for aud in ["general", "kids"]:
        sr = test_results[aud]["script_rating"]["overall_rating"]
        vr = test_results[aud]["viral_rating"]["overall_rating"]
        print(f"{aud:<10} | {sr:<15} | {vr:<15}")
    print("-" * 60)
    print(f"Full report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(run_movie_quality_test())
