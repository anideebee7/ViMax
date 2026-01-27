import logging
import os
from typing import List, Optional

from interfaces.output.image_output import ImageOutput
from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter


class PiAPIImageGenerator:
    """
    PiAPI Image Generator supporting multiple models:
    - Flux (text to image)
    - Gemini (gemini-2.5-flash-image)
    - Qwen (qwen-image)
    """
    
    # Model configurations
    MODEL_CONFIGS = {
        "flux": {
            "model": "Qubico/flux1-dev",
            "task_type": "txt2img",
        },
        "gemini": {
            "model": "gemini",
            "task_type": "gemini-2.5-flash-image",
        },
        "nano-banana-pro": {
            "model": "gemini",
            "task_type": "nano-banana-pro",
        },
        "qwen": {
            "model": "qwen-image",
            "task_type": "txt2img",
        },
    }
    
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        task_type: Optional[str] = None,
        output_format: str = "png",
        aspect_ratio: str = "16:9",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.client = PiAPIClient(api_key=api_key)
        self.rate_limiter = rate_limiter
        self.logger = logging.getLogger(__name__)
        
        # Parse model configuration
        model_key = (model or os.getenv("PIAPI_IMAGE_MODEL") or "flux").lower()
        if model_key in self.MODEL_CONFIGS:
            self.model_config = self.MODEL_CONFIGS[model_key]
        else:
            self.model_config = {
                "model": model or "Qubico/flux1-dev",
                "task_type": task_type or "txt2img",
            }
        
        self.output_format = output_format
        self.aspect_ratio = aspect_ratio

    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        aspect_ratio: Optional[str] = None,
        strength: float = 0.55,
        **kwargs,
    ) -> ImageOutput:
        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        task_type = self.model_config["task_type"]
        input_data = {
            "prompt": prompt,
            "output_format": self.output_format,
            "aspect_ratio": aspect_ratio or self.aspect_ratio,
        }

        if reference_image_paths:
            # If we have reference images, we try to use img2img if supported
            # or pass them as images to multimodal models like Gemini/Qwen
            ref_path = reference_image_paths[0]
            if os.path.exists(ref_path):
                self.logger.info(f"Uploading reference image: {ref_path}")
                ref_url = await self.client.upload_file(ref_path)
                
                if task_type == "txt2img":
                    # Upgrade to img2img for Flux/Stable Diffusion models
                    task_type = "img2img"
                    input_data["image"] = ref_url
                    input_data["strength"] = strength
                    self.logger.info(f"Using img2img with strength {strength}")
                elif "gemini" in task_type or "qwen" in task_type:
                    # Multimodal models usually take images in the input
                    input_data["image"] = ref_url
                    self.logger.info(f"Passing reference image to multimodal model {task_type}")
                else:
                    self.logger.warning(f"Model {task_type} might not support reference images. Passing anyway.")
                    input_data["image"] = ref_url
            else:
                self.logger.warning(f"Reference image path not found: {ref_path}")

        self.logger.info(f"Creating image task with model: {self.model_config['model']} and task_type: {task_type}")
        
        response = await self.client.create_task(
            model=self.model_config["model"],
            task_type=task_type,
            input_data=input_data,
        )

        data = response.get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            error_msg = response.get("message", str(response))
            raise RuntimeError(f"PiAPI image task creation failed: {error_msg}")
        
        self.logger.info(f"Image task created: {task_id}")

        result = await self.client.wait_for_task(task_id)
        
        # Extract image URL from various possible output structures
        data = result.get("data", {})
        output = data.get("output", {}) or {}
        
        image_urls = output.get("image_urls") or output.get("images") or []
        if not image_urls:
            # Try alternative structure
            image_url = output.get("image_url") or output.get("image")
            if image_url:
                image_urls = [image_url]
        
        if not image_urls:
            raise RuntimeError(f"PiAPI image task returned no images: {result}")

        self.logger.info(f"Image generated: {image_urls[0][:100]}...")
        return ImageOutput(fmt="url", ext=self.output_format, data=image_urls[0])
