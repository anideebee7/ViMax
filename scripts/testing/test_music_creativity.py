#!/usr/bin/env python3
"""
Music Creativity Test Script - Phased Testing.
Tests lyrics generation and music video directing (shot list) without triggering generation.
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

from pipelines.music.lyrics import LyricsPipeline
from pipelines.music.video import MusicVideoPipeline
from agents.producers.analysis.evaluator import ScriptEvaluator
from utils.pipeline.entity_resolver import resolve_s3_entities
from langchain.chat_models import init_chat_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_music_audit(idea: str = "A futuristic cyberpunk anthem about digital freedom"):
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
    
    # 2. Test Lyrics Generation
    logger.info("\n" + "="*60)
    logger.info(f"PHASE 1: Song Lyrics for: {idea}")
    logger.info("="*60)
    
    lyrics_pipeline = LyricsPipeline.init_from_config(config_path)
    lyrics_pipeline.working_dir = f".working_dir/testing/music_audit/lyrics"
    os.makedirs(lyrics_pipeline.working_dir, exist_ok=True)
    
    # Run only lyrics generation
    lyrics_draft = await lyrics_pipeline.lyricist.generate_lyrics(
        idea=idea,
        user_requirement="Futuristic, rebellious, high-energy electronic style.",
        style="Cyberpunk / Industrial Rock",
        audience="General music listeners"
    )
    
    # Evaluate Lyrics
    lyrics_content = f"TITLE: {lyrics_draft.title}\nGENRE: {lyrics_draft.genre}\nMOOD: {lyrics_draft.mood}\n\n{lyrics_draft.lyrics}"
    lyrics_rating = await evaluator.evaluate(
        script_content=lyrics_content,
        pipeline_name="Idea2Lyrics (Songwriting)",
        metadata={"idea": idea, "style": "Cyberpunk"}
    )
    
    logger.info(f"\n⭐ LYRICS RATING: {lyrics_rating.overall_rating}/10")
    logger.info(f"   Creativity: {lyrics_rating.creativity}")
    logger.info(f"   Comments: {lyrics_rating.review_comments}")
    
    # 3. Test Music Video Directing (Shot List)
    logger.info("\n" + "="*60)
    logger.info(f"PHASE 2: Music Video Directing for: {lyrics_draft.title}")
    logger.info("="*60)
    
    video_pipeline = MusicVideoPipeline.init_from_config(config_path)
    video_pipeline.working_dir = f".working_dir/testing/music_audit/video"
    os.makedirs(video_pipeline.working_dir, exist_ok=True)
    
    # Run only directing
    concept = await video_pipeline.music_video_director.direct_music_video(
        song_title=lyrics_draft.title,
        lyrics=lyrics_draft.lyrics,
        genre=lyrics_draft.genre or "Electronic",
        mood=lyrics_draft.mood or "Intense",
        song_structure="Duration: 180s (3:00)",
        style="Futuristic Neo-Tokyo aesthetic",
        audience="General music fans"
    )
    
    # Evaluate Music Video Concept
    concept_content = json.dumps(concept.model_dump(), indent=2)
    concept_rating = await evaluator.evaluate(
        script_content=concept_content,
        pipeline_name="Idea2MusicVideo (Directing)",
        metadata={"song": lyrics_draft.title, "genre": lyrics_draft.genre}
    )
    
    logger.info(f"\n⭐ MUSIC VIDEO CONCEPT RATING: {concept_rating.overall_rating}/10")
    logger.info(f"   Creativity: {concept_rating.creativity}")
    logger.info(f"   Comments: {concept_rating.review_comments}")
    
    # Save audit report
    audit_report = {
        "idea": idea,
        "lyrics": lyrics_draft.model_dump(),
        "lyrics_rating": lyrics_rating.model_dump(),
        "video_concept": concept.model_dump(),
        "video_concept_rating": concept_rating.model_dump()
    }
    
    report_path = f"{lyrics_pipeline.working_dir}/audit_report.json"
    with open(report_path, "w") as f:
        json.dump(audit_report, f, indent=2)
    
    logger.info("\n" + "="*60)
    logger.info(f"AUDIT COMPLETE. Report saved to: {report_path}")
    logger.info("="*60)

if __name__ == "__main__":
    asyncio.run(run_music_audit())
