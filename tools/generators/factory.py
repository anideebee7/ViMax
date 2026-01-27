"""
Unified Generator Factory

Provides factory functions to create image and video generators with 
the correct fallback chain. Never change the model priority order.

IMAGE GENERATION PRIORITY (nano-banana-pro model):
1. GoogleImageGenerator (Gemini API) - Primary
2. PiAPIImageGenerator (nano-banana-pro) - Fallback
3. KieAIImageGenerator (nano-banana-pro) - Last resort

VIDEO GENERATION PRIORITY (Veo 3.1):
1. KieAIVideoGenerator (veo3_fast) - Primary  
2. PiAPIVideoGenerator (veo3.1) - Fallback
3. VeoGoogleVideoGenerator (veo-3.1-generate-preview) - Last resort
"""
import logging
import os
from typing import Optional

from utils.core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# ============================================================================
# IMAGE GENERATOR MODELS - DO NOT CHANGE
# ============================================================================
IMAGE_MODEL = "nano-banana-pro"  # NEVER CHANGE THIS


# ============================================================================
# VIDEO GENERATOR MODELS - DO NOT CHANGE
# ============================================================================
VIDEO_MODEL_KIEAI = "veo3_fast"  # Veo 3.1 on KieAI
VIDEO_MODEL_PIAPI = "veo3.1"  # Veo 3.1 on PiAPI
VIDEO_MODEL_GOOGLE = "veo-3.1-generate-preview"  # Veo 3.1 on Google


class UnifiedImageGenerator:
    """
    Unified image generator with automatic fallback chain.
    
    Priority:
    1. GoogleImageGenerator (Gemini API)
    2. PiAPIImageGenerator (nano-banana-pro)
    3. KieAIImageGenerator (nano-banana-pro)
    
    NEVER change the model - always use nano-banana-pro.
    """
    
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        piapi_api_key: Optional[str] = None,
        kieai_api_key: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.kieai_api_key = kieai_api_key or os.getenv("KIEAI_API_KEY")
        self.rate_limiter = rate_limiter
        
        # Initialize generators lazily
        self._gemini_generator = None
        self._piapi_generator = None
        self._kieai_generator = None
        
        logger.info(f"UnifiedImageGenerator initialized with model={IMAGE_MODEL}")
        logger.info(f"  Gemini API: {'✓' if self.gemini_api_key else '✗'}")
        logger.info(f"  PiAPI: {'✓' if self.piapi_api_key else '✗'}")
        logger.info(f"  KieAI: {'✓' if self.kieai_api_key else '✗'}")
    
    def _get_gemini_generator(self):
        if self._gemini_generator is None and self.gemini_api_key:
            from tools.generators.image.google import GoogleImageGenerator
            self._gemini_generator = GoogleImageGenerator(
                api_key=self.gemini_api_key,
                rate_limiter=self.rate_limiter,
                piapi_api_key=self.piapi_api_key,
                enable_piapi_fallback=False,  # We handle fallback manually
            )
        return self._gemini_generator
    
    def _get_piapi_generator(self):
        if self._piapi_generator is None and self.piapi_api_key:
            from tools.generators.image.piapi import PiAPIImageGenerator
            self._piapi_generator = PiAPIImageGenerator(
                api_key=self.piapi_api_key,
                model=IMAGE_MODEL,  # ALWAYS nano-banana-pro
                rate_limiter=self.rate_limiter,
            )
        return self._piapi_generator
    
    def _get_kieai_generator(self):
        if self._kieai_generator is None and self.kieai_api_key:
            from tools.generators.image.kieai import KieAIImageGenerator
            self._kieai_generator = KieAIImageGenerator(
                api_key=self.kieai_api_key,
                model=IMAGE_MODEL,  # ALWAYS nano-banana-pro
                piapi_api_key=self.piapi_api_key,
                enable_piapi_fallback=False,  # We handle fallback manually
                rate_limiter=self.rate_limiter,
            )
        return self._kieai_generator
    
    async def generate_single_image(self, prompt: str, reference_image_paths=None, aspect_ratio="16:9", **kwargs):
        """
        Generate image with automatic fallback chain.
        
        Priority:
        1. Gemini API (GoogleImageGenerator)
        2. PiAPI nano-banana-pro
        3. KieAI nano-banana-pro
        """
        reference_image_paths = reference_image_paths or []
        errors = []
        
        # PRIORITY 1: Gemini API
        gemini = self._get_gemini_generator()
        if gemini:
            try:
                logger.info(f"[Image Gen] Trying Gemini API (priority 1)...")
                return await gemini.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Image Gen] Gemini API failed: {e}")
                errors.append(f"Gemini: {e}")
        
        # PRIORITY 2: PiAPI nano-banana-pro
        piapi = self._get_piapi_generator()
        if piapi:
            try:
                logger.info(f"[Image Gen] Trying PiAPI nano-banana-pro (priority 2)...")
                return await piapi.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Image Gen] PiAPI failed: {e}")
                errors.append(f"PiAPI: {e}")
        
        # PRIORITY 3: KieAI nano-banana-pro
        kieai = self._get_kieai_generator()
        if kieai:
            try:
                logger.info(f"[Image Gen] Trying KieAI nano-banana-pro (priority 3)...")
                return await kieai.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Image Gen] KieAI failed: {e}")
                errors.append(f"KieAI: {e}")
        
        # All generators failed
        raise RuntimeError(f"All image generators failed. Errors: {errors}")


class UnifiedVideoGenerator:
    """
    Unified video generator with automatic fallback chain.
    
    Priority:
    1. KieAIVideoGenerator (veo3_fast / Veo 3.1)
    2. PiAPIVideoGenerator (veo3.1)
    3. VeoGoogleVideoGenerator (veo-3.1-generate-preview)
    
    NEVER change the model - always use Veo 3.1.
    """
    
    def __init__(
        self,
        kieai_api_key: Optional[str] = None,
        piapi_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.kieai_api_key = kieai_api_key or os.getenv("KIEAI_API_KEY")
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.rate_limiter = rate_limiter
        
        # Initialize generators lazily
        self._kieai_generator = None
        self._piapi_generator = None
        self._google_generator = None
        
        logger.info(f"UnifiedVideoGenerator initialized")
        logger.info(f"  KieAI (veo3_fast): {'✓' if self.kieai_api_key else '✗'}")
        logger.info(f"  PiAPI (veo3.1): {'✓' if self.piapi_api_key else '✗'}")
        logger.info(f"  Google (veo-3.1): {'✓' if self.gemini_api_key else '✗'}")
    
    def _get_kieai_generator(self):
        if self._kieai_generator is None and self.kieai_api_key:
            from tools.generators.video.kieai import KieAIVideoGenerator
            self._kieai_generator = KieAIVideoGenerator(
                api_key=self.kieai_api_key,
                t2v_model=VIDEO_MODEL_KIEAI,
                ff2v_model=VIDEO_MODEL_KIEAI,
                piapi_api_key=self.piapi_api_key,
                enable_piapi_fallback=False,  # We handle fallback manually
                rate_limiter=self.rate_limiter,
            )
        return self._kieai_generator
    
    def _get_piapi_generator(self):
        if self._piapi_generator is None and self.piapi_api_key:
            from tools.generators.video.piapi import PiAPIVideoGenerator
            self._piapi_generator = PiAPIVideoGenerator(
                api_key=self.piapi_api_key,
                model=VIDEO_MODEL_PIAPI,
                rate_limiter=self.rate_limiter,
            )
        return self._piapi_generator
    
    def _get_google_generator(self):
        if self._google_generator is None and self.gemini_api_key:
            from tools.generators.video.veo_google import VeoGoogleVideoGenerator
            self._google_generator = VeoGoogleVideoGenerator(
                api_key=self.gemini_api_key,
                t2v_model=VIDEO_MODEL_GOOGLE,
                ff2v_model=VIDEO_MODEL_GOOGLE,
                flf2v_model=VIDEO_MODEL_GOOGLE,
                piapi_api_key=self.piapi_api_key,
                enable_piapi_fallback=False,  # We handle fallback manually
                rate_limiter=self.rate_limiter,
            )
        return self._google_generator
    
    async def generate_single_video(self, prompt: str, reference_image_paths=None, aspect_ratio="16:9", duration=8, **kwargs):
        """
        Generate video with automatic fallback chain.
        
        Priority:
        1. KieAI veo3_fast (Veo 3.1)
        2. PiAPI veo3.1
        3. Google veo-3.1-generate-preview
        """
        reference_image_paths = reference_image_paths or []
        errors = []
        
        # PRIORITY 1: KieAI veo3_fast
        kieai = self._get_kieai_generator()
        if kieai:
            try:
                logger.info(f"[Video Gen] Trying KieAI veo3_fast (priority 1)...")
                return await kieai.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Video Gen] KieAI failed: {e}")
                errors.append(f"KieAI: {e}")
        
        # PRIORITY 2: PiAPI veo3.1
        piapi = self._get_piapi_generator()
        if piapi:
            try:
                logger.info(f"[Video Gen] Trying PiAPI veo3.1 (priority 2)...")
                return await piapi.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Video Gen] PiAPI failed: {e}")
                errors.append(f"PiAPI: {e}")
        
        # PRIORITY 3: Google Veo 3.1
        google = self._get_google_generator()
        if google:
            try:
                logger.info(f"[Video Gen] Trying Google veo-3.1 (priority 3)...")
                return await google.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"[Video Gen] Google Veo failed: {e}")
                errors.append(f"Google: {e}")
        
        # All generators failed
        raise RuntimeError(f"All video generators failed. Errors: {errors}")
    
    async def extend_video(self, task_id: str, prompt: str, **kwargs):
        """
        Extend an existing video (KieAI only supports this).
        Falls through to KieAI only since extension is KieAI-specific.
        """
        kieai = self._get_kieai_generator()
        if kieai:
            return await kieai.extend_video(task_id=task_id, prompt=prompt, **kwargs)
        raise RuntimeError("Video extension requires KieAI API key")


def get_image_generator(
    gemini_api_key: Optional[str] = None,
    piapi_api_key: Optional[str] = None,
    kieai_api_key: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> UnifiedImageGenerator:
    """
    Get a unified image generator with automatic fallback.
    
    Priority:
    1. Gemini API (GoogleImageGenerator)
    2. PiAPI nano-banana-pro
    3. KieAI nano-banana-pro
    
    NEVER change the image model - always use nano-banana-pro.
    """
    return UnifiedImageGenerator(
        gemini_api_key=gemini_api_key,
        piapi_api_key=piapi_api_key,
        kieai_api_key=kieai_api_key,
        rate_limiter=rate_limiter,
    )


def get_video_generator(
    kieai_api_key: Optional[str] = None,
    piapi_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> UnifiedVideoGenerator:
    """
    Get a unified video generator with automatic fallback.
    
    Priority:
    1. KieAI veo3_fast (Veo 3.1)
    2. PiAPI veo3.1
    3. Google veo-3.1-generate-preview
    
    NEVER change the video model - always use Veo 3.1.
    """
    return UnifiedVideoGenerator(
        kieai_api_key=kieai_api_key,
        piapi_api_key=piapi_api_key,
        gemini_api_key=gemini_api_key,
        rate_limiter=rate_limiter,
    )


# Convenience aliases
ImageGenerator = UnifiedImageGenerator
VideoGenerator = UnifiedVideoGenerator
