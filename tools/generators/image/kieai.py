import logging
import os
import asyncio
import aiohttp
import json
from typing import List, Optional
from interfaces.output.image_output import ImageOutput
from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter
from .piapi import PiAPIImageGenerator


class KieAIImageGenerator:
    def __init__(
        self,
        api_key: str,
        model: str = "nano-banana-pro",
        piapi_api_key: Optional[str] = None,
        enable_piapi_fallback: bool = True,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.base_url = "https://api.kie.ai/api/v1"
        self.api_key = api_key
        self.model = model
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.enable_piapi_fallback = enable_piapi_fallback
        self.piapi_client = PiAPIClient(api_key=self.piapi_api_key) if self.piapi_api_key else None
        self.rate_limiter = rate_limiter

    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        aspect_ratio: str = "1:1",
        **kwargs,
    ) -> ImageOutput:
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        logging.info(f"Calling KieAI {self.model} to generate image...")

        # Normalize aspect ratio for KieAI
        # Options: 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9, auto
        if aspect_ratio == "16:9":
            kie_aspect_ratio = "16:9"
        elif aspect_ratio == "9:16":
            kie_aspect_ratio = "9:16"
        else:
            kie_aspect_ratio = aspect_ratio if ":" in aspect_ratio else "1:1"

        payload_input = {
            "prompt": prompt,
            "aspect_ratio": kie_aspect_ratio,
            "resolution": "1K",
            "output_format": "png"
        }

        if reference_image_paths:
            if not self.piapi_client:
                raise RuntimeError("KieAI requires image URLs for image-to-image, but no PiAPI key provided for upload fallback.")
            
            image_urls = []
            for path in reference_image_paths:
                if path.startswith("http"):
                    image_urls.append(path)
                else:
                    logging.info(f"Uploading reference image to ephemeral storage: {path}")
                    url = await self.piapi_client.upload_file(path)
                    image_urls.append(url)
            payload_input["image_input"] = image_urls

        payload = {
            "model": self.model,
            "input": payload_input
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/jobs/createTask", headers=headers, json=payload) as response:
                    res_json = await response.json()
                    if res_json.get("code") != 200:
                        raise RuntimeError(f"KieAI task creation failed: {res_json}")
                    task_id = res_json["data"]["taskId"]
                    logging.info(f"KieAI image task created: {task_id}")

            # Polling for result
            start_time = asyncio.get_event_loop().time()
            timeout = kwargs.get("timeout", 300)

            while (asyncio.get_event_loop().time() - start_time) < timeout:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}/jobs/queryTask?taskId={task_id}", headers=headers) as response:
                        res_json = await response.json()
                        if res_json.get("code") == 200:
                            state = res_json["data"].get("state")
                            if state == "success":
                                result_json_str = res_json["data"].get("resultJson")
                                result_json = json.loads(result_json_str)
                                urls = result_json.get("resultUrls", [])
                                if urls:
                                    return ImageOutput(fmt="url", ext="png", data=urls[0])
                            elif state == "fail":
                                raise RuntimeError(f"KieAI task failed: {res_json}")
                        
                        logging.info(f"KieAI image generation status: {res_json.get('msg', 'pending')}, waiting...")
                        await asyncio.sleep(2)
            
            raise TimeoutError(f"KieAI task {task_id} timed out.")

        except Exception as e:
            if self.enable_piapi_fallback and self.piapi_api_key:
                logging.warning(f"KieAI generation failed, falling back to PiAPI: {e}")
                piapi = PiAPIImageGenerator(api_key=self.piapi_api_key)
                return await piapi.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            raise
