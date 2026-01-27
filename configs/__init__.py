"""
Configuration modules for ViMax pipelines.

This package contains:
- pipeline_profiles: Specialized agent profiles for each content type
"""

from configs.constants.pipeline_profiles import (
    PipelineProfile,
    VisualProfile,
    ContentGoals,
    PIPELINE_PROFILES,
    get_pipeline_profile,
    get_profile_context,
    # Individual profiles
    PODCAST_PROFILE,
    DOCUMENTARY_PROFILE,
    KIDS_MOVIE_PROFILE,
    AD_PROFILE,
    SHORT_MOVIE_PROFILE,
    MUSIC_VIDEO_PROFILE,
    LEARNING_SERIES_PROFILE,
    SHORTS_PROFILE,
)

__all__ = [
    "PipelineProfile",
    "VisualProfile",
    "ContentGoals",
    "PIPELINE_PROFILES",
    "get_pipeline_profile",
    "get_profile_context",
    "PODCAST_PROFILE",
    "DOCUMENTARY_PROFILE",
    "KIDS_MOVIE_PROFILE",
    "AD_PROFILE",
    "SHORT_MOVIE_PROFILE",
    "MUSIC_VIDEO_PROFILE",
    "LEARNING_SERIES_PROFILE",
    "SHORTS_PROFILE",
]
