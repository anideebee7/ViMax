"""
Kling Elements Video Generator

Uses PiAPI's Kling Elements API for character-consistent video generation.
Supports 1-4 character images that are preserved throughout the video.
"""
import logging
import os
import asyncio
from typing import List, Optional, Dict, Any

from interfaces.output.video_output import VideoOutput
from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter


class KlingVideoGenerator:
    """
    Kling Elements video generator for character-consistent videos.
    
    Unlike generic image-to-video models, Kling Elements treats each
    provided image as a distinct "element" that is preserved in the video.
    
    Supports 1-4 character images per video.
    """
    
    def __init__(
        self,
        api_key: str,
        version: str = "1.6",
        mode: str = "std",
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize Kling Elements video generator.
        
        Args:
            api_key: PiAPI API key
            version: Kling version (must be "1.6" for elements support)
            mode: Generation mode ("std" or "pro")
            duration_seconds: Video duration (5 or 10 seconds)
            aspect_ratio: Video aspect ratio ("16:9", "9:16", or "1:1")
            rate_limiter: Optional rate limiter
        """
        self.api_key = api_key
        self.client = PiAPIClient(api_key=api_key)
        self.version = version
        self.mode = mode
        self.duration_seconds = duration_seconds
        self.aspect_ratio = aspect_ratio
        self.rate_limiter = rate_limiter
        self.logger = logging.getLogger(__name__)
    
    def _is_url(self, path: str) -> bool:
        """Check if a path is a URL"""
        return path.startswith("http://") or path.startswith("https://")
    
    async def _get_image_url(self, path_or_url: str) -> str:
        """
        Get image URL - returns directly if already URL,
        otherwise attempts upload (requires PiAPI Creator plan)
        """
        if self._is_url(path_or_url):
            return path_or_url
        
        # Try to upload local file
        try:
            return await self.client.upload_file(path_or_url)
        except Exception as e:
            self.logger.warning(f"Failed to upload file {path_or_url}: {e}")
            raise
    
    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        duration: Optional[int] = None,
        mode: Optional[str] = None,
        negative_prompt: str = "",
        **kwargs,
    ) -> VideoOutput:
        """
        Generate a video using Kling Elements.
        
        The provided images are treated as "elements" - the model will
        preserve these characters/objects throughout the video.
        
        Args:
            prompt: Description of desired video (actions, interactions)
            reference_image_paths: List of 1-4 image paths or URLs (character images)
            aspect_ratio: Video aspect ratio (default: 16:9)
            duration: Video duration in seconds (5 or 10)
            mode: Generation mode (std or pro)
            negative_prompt: What to avoid in the video
        
        Returns:
            VideoOutput with video URL
        """
        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        # Build elements array from reference images
        elements = []
        if reference_image_paths:
            for img_path in reference_image_paths[:4]:  # Max 4 elements
                try:
                    img_url = await self._get_image_url(img_path)
                    elements.append({"image_url": img_url})
                    self.logger.info(f"Added element: {img_url[:80]}...")
                except Exception as e:
                    self.logger.warning(f"Could not add element {img_path}: {e}")
        
        if not elements:
            self.logger.warning("No elements provided, using text-to-video mode")
        
        # Build input data
        input_data: Dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": duration or self.duration_seconds,
            "aspect_ratio": aspect_ratio or self.aspect_ratio,
            "mode": mode or self.mode,
            "version": self.version,
        }
        
        # Add elements if we have them
        if elements:
            input_data["elements"] = elements
        
        self.logger.info(f"Creating Kling Elements video task")
        self.logger.info(f"  Elements: {len(elements)}")
        self.logger.info(f"  Duration: {input_data['duration']}s")
        self.logger.info(f"  Prompt: {prompt[:100]}...")
        
        # Create task
        response = await self.client.create_task(
            model="kling",
            task_type="video_generation",
            input_data=input_data,
        )
        
        data = response.get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            error_msg = response.get("message", str(response))
            raise RuntimeError(f"Kling Elements task creation failed: {error_msg}")
        
        self.logger.info(f"Task created: {task_id}")
        
        # Wait for completion (Kling videos can take 2-5 minutes)
        result = await self.client.wait_for_task(task_id, timeout_seconds=600)
        
        # Extract video URL
        data = result.get("data", {})
        status = data.get("status", "").lower()
        
        if status in ("failed", "error"):
            error = data.get("error", {})
            error_msg = error.get("message") or error.get("raw_message") or str(result)
            raise RuntimeError(f"Kling Elements task failed: {error_msg}")
        
        output = data.get("output", {}) or {}
        video_url = output.get("video_url") or output.get("video")
        
        if not video_url:
            # Try alternative output structures (Kling specific)
            works = output.get("works", [])
            if works and isinstance(works, list) and len(works) > 0:
                work = works[0]
                if isinstance(work, dict):
                    # Try video.resource_without_watermark first (cleaner)
                    video_obj = work.get("video", {})
                    if video_obj:
                        video_url = video_obj.get("resource_without_watermark") or video_obj.get("resource")
                    # Fallback to direct resource
                    if not video_url:
                        video_url = work.get("resource", {}).get("resource")
        
        if not video_url:
            raise RuntimeError(f"Kling Elements task returned no video: {result}")
        
        self.logger.info(f"Video generated: {video_url}")
        return VideoOutput(fmt="url", ext="mp4", data=video_url)
    
    async def generate_multi_character_video(
        self,
        prompt: str,
        character_images: Dict[str, str],
        aspect_ratio: Optional[str] = None,
        duration: Optional[int] = None,
        **kwargs,
    ) -> VideoOutput:
        """
        Convenience method for generating videos with named characters.
        
        Args:
            prompt: Description including character names and actions
            character_images: Dict of character_name -> image_url/path
            aspect_ratio: Video aspect ratio
            duration: Video duration
        
        Example:
            await generator.generate_multi_character_video(
                prompt="AUTOcurio and DotDot are talking together, then Gloop joins them",
                character_images={
                    "AUTOcurio": "https://..../autocurio.png",
                    "DotDot": "https://..../dotdot.png",
                    "Gloop": "https://..../gloop.png",
                }
            )
        """
        # Get images in order
        image_paths = list(character_images.values())[:4]
        
        # Enhance prompt with character order info
        char_names = list(character_images.keys())[:4]
        enhanced_prompt = f"{prompt}\n\nCharacters (in element order): {', '.join(char_names)}"
        
        return await self.generate_single_video(
            prompt=enhanced_prompt,
            reference_image_paths=image_paths,
            aspect_ratio=aspect_ratio,
            duration=duration,
            **kwargs,
        )
