"""Viral Extractor Utility: orchestrates viral finder and editor for pipelines."""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from agents.producers.analysis.viral_finder import ViralFinder
from utils.media.viral_editor import process_viral_segments

logger = logging.getLogger(__name__)

async def extract_viral_shorts(
    chat_model,
    working_dir: str,
    final_video_path: str,
    script_content: str,
    total_duration_seconds: float,
    content_type: str = "movie"
) -> List[str]:
    """
    Automatically identifies and extracts viral clips from long-form content.
    """
    if not final_video_path or not os.path.exists(final_video_path):
        logger.warning(f"Final video not found at {final_video_path}. Skipping viral extraction.")
        return []

    shorts_dir = os.path.join(working_dir, "shorts_viral")
    os.makedirs(shorts_dir, exist_ok=True)

    # 1. Identify Viral Segments
    logger.info(f"🔍 Identifying viral segments for {content_type}...")
    viral_finder = ViralFinder(chat_model=chat_model)
    try:
        analysis = await viral_finder.find_viral_segments(
            script_content=script_content,
            total_duration_seconds=total_duration_seconds,
            content_type=content_type
        )
        
        # Save analysis for reference
        with open(os.path.join(shorts_dir, "viral_analysis.json"), "w") as f:
            json.dump(analysis.model_dump(), f, indent=2)
            
        # 2. Extract and Edit Clips
        logger.info(f"✂️ Extracting {len(analysis.segments)} viral clips...")
        segments_data = [s.model_dump() for s in analysis.segments]
        clip_paths = process_viral_segments(
            source_video_path=final_video_path,
            output_dir=shorts_dir,
            segments=segments_data
        )
        
        logger.info(f"✅ Viral extraction complete. Clips saved to: {shorts_dir}")
        return clip_paths
        
    except Exception as e:
        logger.error(f"❌ Viral extraction failed: {e}")
        return []
