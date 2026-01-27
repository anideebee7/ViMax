import logging
import os
import aiohttp
from typing import List, Optional, Union

from interfaces.output.video_output import VideoOutput
from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter


class PiAPIVideoGenerator:
    """
    PiAPI Video Generator supporting multiple models:
    - Wan2.6 (wan26-txt2video, wan26-img2video)
    - Kling (kling-video)
    - Hailuo (hailuo-video)
    - Hunyuan (hunyuan-video)
    - Veo3/3.1 (veo3.1-video)
    """
    
    # Model configurations
    MODEL_CONFIGS = {
        "wan26": {
            "model": "Wan",
            "txt2video": "wan26-txt2video",
            "img2video": "wan26-img2video",
            "image_param": "image",  # Accepts direct URL
        },
        "kling": {
            "model": "kling",
            "txt2video": "m2v_img2video_hq",
            "img2video": "m2v_img2video_hq",
            "image_param": "input_image",
        },
        "hailuo": {
            "model": "hailuo",
            "txt2video": "video-01-live2d",
            "img2video": "video-01-live2d",
            "image_param": "image_url",
        },
        "hunyuan": {
            "model": "Hunyuan",
            "txt2video": "hunyuan-txt2video",
            "img2video": "hunyuan-txt2video",  # Hunyuan uses same task_type
            "image_param": "image",
        },
        "veo31": {
            "model": "veo3.1",
            "txt2video": "veo3.1-video",
            "img2video": "veo3.1-video",  # Same task_type, just add image_url
            "image_param": "image_url",
            "duration_format": "string",  # e.g., "8s"
        },
        "veo3.1": {
            "model": "veo3.1",
            "txt2video": "veo3.1-video",
            "img2video": "veo3.1-video",  # Same task_type, just add image_url
            "image_param": "image_url",
            "duration_format": "string",  # e.g., "8s"
        },
        "veo3.1-fast": {
            "model": "veo3.1",
            "txt2video": "veo3.1-video-fast",
            "img2video": "veo3.1-video-fast",  # Same task_type
            "image_param": "image_url",
            "duration_format": "string",
        },
    }
    
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        task_type: Optional[str] = None,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        duration_seconds: int = 5,
        generate_audio: bool = False,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.client = PiAPIClient(api_key=api_key)
        
        # Parse model configuration
        model_key = (model or os.getenv("PIAPI_VIDEO_MODEL") or "wan26").lower()
        if model_key in self.MODEL_CONFIGS:
            self.model_config = self.MODEL_CONFIGS[model_key]
        else:
            # Custom model/task_type
            self.model_config = {
                "model": model or "Wan",
                "txt2video": task_type or "wan26-txt2video",
                "img2video": task_type or "wan26-img2video",
                "image_param": "image",
            }
        
        self.resolution = resolution
        self.aspect_ratio = aspect_ratio
        self.duration_seconds = duration_seconds
        self.generate_audio = generate_audio
        self.rate_limiter = rate_limiter
        self.logger = logging.getLogger(__name__)
    
    def _is_url(self, path: str) -> bool:
        """Check if a path is a URL"""
        return path.startswith("http://") or path.startswith("https://")
    
    async def _get_image_url(self, path_or_url: str) -> Optional[str]:
        """
        Get image URL - returns directly if already URL,
        otherwise uploads to PiAPI (requires Creator plan)
        Returns None if upload fails (caller should fall back to txt2video)
        """
        if self._is_url(path_or_url):
            return path_or_url
        
        # Try to upload local file
        try:
            return await self.client.upload_file(path_or_url)
        except Exception as e:
            self.logger.warning(f"Failed to upload file {path_or_url}: {e}")
            self.logger.warning("Falling back to text-to-video mode (no reference image)")
            return None

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: Optional[Union[List[str], None]] = None,
        aspect_ratio: Optional[str] = None,
        duration: Optional[int] = None,
        resolution: Optional[str] = None,
        generate_audio: Optional[bool] = None,
        **kwargs,
    ) -> VideoOutput:
        """
        Generate a video using PiAPI.
        
        Args:
            prompt: Text prompt describing the video
            reference_image_paths: List of image paths or URLs (first one used)
            aspect_ratio: Video aspect ratio (default: 16:9)
            duration: Video duration in seconds (default: 5)
            resolution: Video resolution (default: 720p)
            generate_audio: Whether to generate audio (default: False)
        """
        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        # Determine if we're doing txt2video or img2video
        has_image = reference_image_paths and len(reference_image_paths) > 0
        task_type = self.model_config["img2video"] if has_image else self.model_config["txt2video"]
        
        # Build input data
        dur = duration or self.duration_seconds
        
        # Handle duration format - some models need string like "8s"
        if self.model_config.get("duration_format") == "string":
            dur = f"{dur}s" if isinstance(dur, int) else dur
        
        input_data = {
            "prompt": prompt,
            "resolution": resolution or self.resolution,
            "duration": dur,
        }
        
        # Model-specific parameters
        model_key = self.model_config["model"].lower()
        if model_key == "wan":
            input_data["prompt_extend"] = True
            input_data["audio"] = self.generate_audio if generate_audio is None else generate_audio
            input_data["watermark"] = False
        elif model_key == "veo3.1":
            # Veo 3.1 specific parameters
            input_data["aspect_ratio"] = aspect_ratio or self.aspect_ratio
            input_data["generate_audio"] = generate_audio if generate_audio is not None else self.generate_audio
            # Don't include watermark param for Veo 3.1
        else:
            # Generic parameters
            input_data["aspect_ratio"] = aspect_ratio or self.aspect_ratio
            input_data["watermark"] = False
            if generate_audio is not None:
                input_data["generate_audio"] = generate_audio
        
        # Add reference image if provided
        if has_image:
            image_url = await self._get_image_url(reference_image_paths[0])
            if image_url:
                image_param = self.model_config["image_param"]
                input_data[image_param] = image_url
                self.logger.info(f"Using reference image: {image_url[:100]}...")
            else:
                # Fall back to txt2video if image upload failed
                has_image = False
                task_type = self.model_config["txt2video"]
                self.logger.info("Using text-to-video mode (image upload failed)")
        
        self.logger.info(f"Creating {self.model_config['model']} video task ({task_type})")
        self.logger.info(f"Prompt: {prompt[:100]}...")
        
        # Create task
        response = await self.client.create_task(
            model=self.model_config["model"],
            task_type=task_type,
            input_data=input_data,
        )

        data = response.get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            error_msg = response.get("message", str(response))
            raise RuntimeError(f"PiAPI video task creation failed: {error_msg}")
        
        self.logger.info(f"Task created: {task_id}")

        # Wait for completion
        result = await self.client.wait_for_task(task_id, timeout_seconds=600)
        
        # Extract video URL
        data = result.get("data", {})
        status = data.get("status", "").lower()
        
        if status in ("failed", "error"):
            error = data.get("error", {})
            error_msg = error.get("message") or error.get("raw_message") or str(result)
            raise RuntimeError(f"PiAPI video task failed: {error_msg}")
        
        output = data.get("output", {}) or {}
        video_url = output.get("video") or output.get("video_url") or output.get("video_link")
        
        if not video_url:
            # Try alternative output structures
            works = output.get("works", [])
            if works and isinstance(works, list):
                video_url = works[0].get("video", {}).get("url") if isinstance(works[0], dict) else None
        
        if not video_url:
            raise RuntimeError(f"PiAPI video task returned no video: {result}")
        
        self.logger.info(f"Video generated: {video_url}")
        return VideoOutput(fmt="url", ext="mp4", data=video_url, metadata={"task_id": task_id})
