"""Helper utilities for adding checkpoint support to pipelines.

This module provides reusable functions to add checkpoint/resume functionality
to any pipeline without duplicating code.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from utils.pipeline.checkpoint import CheckpointManager
from utils.pipeline.run_memory import RunMemory

logger = logging.getLogger(__name__)


def initialize_pipeline_checkpoint(
    pipeline_instance,
    pipeline_type: str,
    working_dir: str,
    run_id: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> CheckpointManager:
    """Initialize checkpoint manager for a pipeline.
    
    Args:
        pipeline_instance: The pipeline instance (needs working_dir, run_id, memory attributes)
        pipeline_type: Type of pipeline (e.g., "movie", "music_video")
        working_dir: Working directory path
        run_id: Run ID
        metadata: Optional metadata to store in checkpoint
        
    Returns:
        CheckpointManager instance
    """
    checkpoint = CheckpointManager(
        working_dir=working_dir,
        run_id=run_id or "unknown",
        pipeline_type=pipeline_type
    )
    
    # Try to sync from S3 if local folder is missing
    if hasattr(pipeline_instance, 'memory') and isinstance(pipeline_instance.memory, RunMemory):
        if not os.path.exists(working_dir):
            logger.info(f"Attempting to sync run state from S3 for run_id: {run_id}")
            if pipeline_instance.memory.sync_from_s3():
                logger.info("✅ Synced run state from S3")
                # Restore ContinuityMemory if available
                if hasattr(pipeline_instance, 'continuity_memory'):
                    pipeline_instance.continuity_memory.load()
                    pipeline_instance.continuity_memory.load_series_state()
            else:
                logger.info("No existing run found in S3, starting fresh")
    
    # Load existing checkpoint or initialize new one
    existing_checkpoint = checkpoint.load()
    if not existing_checkpoint:
        checkpoint.initialize(metadata=metadata)
    elif not pipeline_instance.force_regenerate if hasattr(pipeline_instance, 'force_regenerate') else False:
        resume_info = checkpoint.get_resume_info()
        logger.info(f"🔄 Resuming incomplete run (status: {resume_info['status']})")
        if resume_info.get('completed_phases'):
            logger.info(f"   Completed phases: {resume_info['completed_phases']}")
        if resume_info.get('completed_episodes'):
            logger.info(f"   Completed episodes: {resume_info['completed_episodes']}")
        if resume_info.get('completed_scenes'):
            logger.info(f"   Completed scenes: {resume_info['completed_scenes']}")
        if resume_info.get('errors'):
            logger.warning(f"   Previous errors: {resume_info['errors']}")
    
    return checkpoint


def should_skip_generation(
    checkpoint: CheckpointManager,
    file_path: str,
    scene_number: Optional[int] = None,
    shot_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    force_regenerate: bool = False,
) -> bool:
    """Check if generation should be skipped based on checkpoint and file existence.
    
    Args:
        checkpoint: CheckpointManager instance
        file_path: Path to expected output file
        scene_number: Optional scene number for scene-level checking
        shot_number: Optional shot number for shot-level checking
        episode_number: Optional episode number for episode-level checking
        force_regenerate: Whether to force regeneration
        
    Returns:
        True if generation should be skipped (file exists and checkpointed)
    """
    if force_regenerate:
        return False
    
    # Check file existence
    if not os.path.exists(file_path):
        return False
    
    # Check checkpoint if available
    if scene_number is not None and shot_number is not None:
        return checkpoint.is_shot_completed(scene_number, shot_number)
    elif scene_number is not None:
        return checkpoint.is_scene_completed(scene_number)
    elif episode_number is not None:
        return checkpoint.is_episode_completed(episode_number)
    
    # If no checkpoint info, rely on file existence
    return True


def mark_generation_complete(
    checkpoint: CheckpointManager,
    scene_number: Optional[int] = None,
    shot_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    image_path: Optional[str] = None,
    video_path: Optional[str] = None,
    raw_image_path: Optional[str] = None,
    output_files: Optional[List[str]] = None,
):
    """Mark a generation task as complete in checkpoint.
    
    Args:
        checkpoint: CheckpointManager instance
        scene_number: Optional scene number
        shot_number: Optional shot number
        episode_number: Optional episode number
        image_path: Optional path to generated image
        video_path: Optional path to generated video
        raw_image_path: Optional path to raw/gelled image
        output_files: Optional list of all output files
    """
    if scene_number is not None and shot_number is not None:
        checkpoint.complete_shot(
            scene_number, shot_number,
            image_path=image_path,
            video_path=video_path,
            raw_image_path=raw_image_path,
        )
    elif scene_number is not None:
        checkpoint.complete_scene(scene_number, output_files=output_files or [])
    elif episode_number is not None:
        checkpoint.complete_episode(episode_number, output_files=output_files or [])


def mark_generation_failed(
    checkpoint: CheckpointManager,
    error: str,
    scene_number: Optional[int] = None,
    shot_number: Optional[int] = None,
    episode_number: Optional[int] = None,
):
    """Mark a generation task as failed in checkpoint.
    
    Args:
        checkpoint: CheckpointManager instance
        error: Error message
        scene_number: Optional scene number
        shot_number: Optional shot number
        episode_number: Optional episode number
    """
    if scene_number is not None and shot_number is not None:
        checkpoint.fail_shot(scene_number, shot_number, error)
    elif scene_number is not None:
        checkpoint.fail_scene(scene_number, error)
    elif episode_number is not None:
        checkpoint.fail_episode(episode_number, error)
