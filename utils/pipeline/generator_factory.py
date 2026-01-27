"""
Pipeline Generator Factory

Centralized factory for creating image and video generators with
the correct fallback chain. All pipelines should use this to ensure
consistent generator configuration across the entire codebase.

IMAGE GENERATION PRIORITY (nano-banana-pro model - NEVER CHANGE):
1. GoogleImageGenerator (Gemini API) - Primary
2. PiAPIImageGenerator (nano-banana-pro) - Fallback
3. KieAIImageGenerator (nano-banana-pro) - Last resort

VIDEO GENERATION PRIORITY (Veo 3.1 - NEVER CHANGE):
1. KieAIVideoGenerator (veo3_fast) - Primary
2. PiAPIVideoGenerator (veo3.1) - Fallback
3. VeoGoogleVideoGenerator (veo-3.1-generate-preview) - Last resort
"""
import logging
import os
from typing import Optional, Tuple, Any

from utils.core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def create_generators(
    image_rate_limiter: Optional[RateLimiter] = None,
    video_rate_limiter: Optional[RateLimiter] = None,
    gemini_api_key: Optional[str] = None,
    piapi_api_key: Optional[str] = None,
    kieai_api_key: Optional[str] = None,
) -> Tuple[Any, Any]:
    """
    Create unified image and video generators with the correct fallback chain.
    
    This is the PREFERRED way to create generators for all pipelines.
    
    Args:
        image_rate_limiter: Rate limiter for image generation
        video_rate_limiter: Rate limiter for video generation
        gemini_api_key: Gemini/Google API key (optional, uses env if not provided)
        piapi_api_key: PiAPI API key (optional, uses env if not provided)
        kieai_api_key: KieAI API key (optional, uses env if not provided)
    
    Returns:
        Tuple of (image_generator, video_generator)
    
    Image Generator Priority (nano-banana-pro - NEVER CHANGE):
        1. Gemini API (GoogleImageGenerator)
        2. PiAPI nano-banana-pro
        3. KieAI nano-banana-pro
    
    Video Generator Priority (Veo 3.1 - NEVER CHANGE):
        1. KieAI veo3_fast
        2. PiAPI veo3.1
        3. Google veo-3.1-generate-preview
    """
    from tools.generators.factory import (
        UnifiedImageGenerator,
        UnifiedVideoGenerator,
    )
    
    # Resolve API keys from environment if not provided
    gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
    kieai_api_key = kieai_api_key or os.getenv("KIEAI_API_KEY")
    
    logger.info("Creating unified generators with fallback chains...")
    logger.info(f"  Gemini API: {'✓' if gemini_api_key else '✗'}")
    logger.info(f"  PiAPI: {'✓' if piapi_api_key else '✗'}")
    logger.info(f"  KieAI: {'✓' if kieai_api_key else '✗'}")
    
    image_generator = UnifiedImageGenerator(
        gemini_api_key=gemini_api_key,
        piapi_api_key=piapi_api_key,
        kieai_api_key=kieai_api_key,
        rate_limiter=image_rate_limiter,
    )
    
    video_generator = UnifiedVideoGenerator(
        kieai_api_key=kieai_api_key,
        piapi_api_key=piapi_api_key,
        gemini_api_key=gemini_api_key,
        rate_limiter=video_rate_limiter,
    )
    
    return image_generator, video_generator


def create_image_generator(
    rate_limiter: Optional[RateLimiter] = None,
    gemini_api_key: Optional[str] = None,
    piapi_api_key: Optional[str] = None,
    kieai_api_key: Optional[str] = None,
) -> Any:
    """
    Create a unified image generator with the correct fallback chain.
    
    Priority (nano-banana-pro model - NEVER CHANGE):
        1. Gemini API (GoogleImageGenerator)
        2. PiAPI nano-banana-pro
        3. KieAI nano-banana-pro
    """
    from tools.generators.factory import UnifiedImageGenerator
    
    return UnifiedImageGenerator(
        gemini_api_key=gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        piapi_api_key=piapi_api_key or os.getenv("PIAPI_API_KEY"),
        kieai_api_key=kieai_api_key or os.getenv("KIEAI_API_KEY"),
        rate_limiter=rate_limiter,
    )


def create_video_generator(
    rate_limiter: Optional[RateLimiter] = None,
    kieai_api_key: Optional[str] = None,
    piapi_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
) -> Any:
    """
    Create a unified video generator with the correct fallback chain.
    
    Priority (Veo 3.1 - NEVER CHANGE):
        1. KieAI veo3_fast
        2. PiAPI veo3.1
        3. Google veo-3.1-generate-preview
    """
    from tools.generators.factory import UnifiedVideoGenerator
    
    return UnifiedVideoGenerator(
        kieai_api_key=kieai_api_key or os.getenv("KIEAI_API_KEY"),
        piapi_api_key=piapi_api_key or os.getenv("PIAPI_API_KEY"),
        gemini_api_key=gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        rate_limiter=rate_limiter,
    )


def create_generators_from_config(config: dict) -> Tuple[Any, Any]:
    """
    Create unified generators from a pipeline config dictionary.
    
    This is a drop-in replacement for the dynamic class loading approach.
    Instead of loading specific generator classes, it creates unified
    generators with the correct fallback chain.
    
    Args:
        config: Pipeline configuration dictionary (from YAML)
    
    Returns:
        Tuple of (image_generator, video_generator)
    """
    def _resolve_env(value):
        if not isinstance(value, str):
            return value
        if value.startswith("${") and value.endswith("}"):
            return os.getenv(value[2:-1], "")
        if value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value
    
    # Extract rate limiting config
    image_generator_rpm = config.get("image_generator", {}).get("max_requests_per_minute")
    image_generator_rpd = config.get("image_generator", {}).get("max_requests_per_day")
    video_generator_rpm = config.get("video_generator", {}).get("max_requests_per_minute")
    video_generator_rpd = config.get("video_generator", {}).get("max_requests_per_day")
    
    image_rate_limiter = RateLimiter(
        max_requests_per_minute=image_generator_rpm,
        max_requests_per_day=image_generator_rpd
    ) if (image_generator_rpm or image_generator_rpd) else None
    
    video_rate_limiter = RateLimiter(
        max_requests_per_minute=video_generator_rpm,
        max_requests_per_day=video_generator_rpd
    ) if (video_generator_rpm or video_generator_rpd) else None
    
    # Extract API keys from config init_args (if provided)
    image_config = config.get("image_generator", {}).get("init_args", {})
    video_config = config.get("video_generator", {}).get("init_args", {})
    
    gemini_api_key = (
        _resolve_env(image_config.get("api_key")) or
        _resolve_env(video_config.get("api_key")) or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("GOOGLE_API_KEY")
    )
    piapi_api_key = (
        _resolve_env(image_config.get("piapi_api_key")) or
        _resolve_env(video_config.get("piapi_api_key")) or
        os.getenv("PIAPI_API_KEY")
    )
    kieai_api_key = (
        _resolve_env(image_config.get("kieai_api_key")) or
        _resolve_env(video_config.get("kieai_api_key")) or
        os.getenv("KIEAI_API_KEY")
    )
    
    # Display rate limiting configuration
    if image_rate_limiter:
        limits = []
        if image_generator_rpm:
            limits.append(f"{image_generator_rpm} req/min")
        if image_generator_rpd:
            limits.append(f"{image_generator_rpd} req/day")
        logger.info(f"Image generator rate limiting: {', '.join(limits)}")
    
    if video_rate_limiter:
        limits = []
        if video_generator_rpm:
            limits.append(f"{video_generator_rpm} req/min")
        if video_generator_rpd:
            limits.append(f"{video_generator_rpd} req/day")
        logger.info(f"Video generator rate limiting: {', '.join(limits)}")
    
    return create_generators(
        image_rate_limiter=image_rate_limiter,
        video_rate_limiter=video_rate_limiter,
        gemini_api_key=gemini_api_key,
        piapi_api_key=piapi_api_key,
        kieai_api_key=kieai_api_key,
    )
