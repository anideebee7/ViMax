import logging
import os
import asyncio
import aiohttp
from typing import List, Optional, Dict, Any
from PIL import Image
from interfaces.output.video_output import VideoOutput
from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter
from .piapi import PiAPIVideoGenerator


class KieAIVideoGenerator:
    def __init__(
        self,
        api_key: str,
        t2v_model: str = "veo3_fast",
        ff2v_model: str = "veo3_fast",
        piapi_api_key: Optional[str] = None,
        enable_piapi_fallback: bool = True,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.base_url = "https://api.kie.ai/api/v1"
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.ff2v_model = ff2v_model
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.enable_piapi_fallback = enable_piapi_fallback
        self.piapi_client = PiAPIClient(api_key=self.piapi_api_key) if self.piapi_api_key else None
        self.rate_limiter = rate_limiter

    async def _poll_task(self, task_id: str, headers: Dict[str, str], timeout: int = 600) -> VideoOutput:
        """Poll for task completion using /veo/record-info."""
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/veo/record-info?taskId={task_id}", headers=headers) as response:
                    res_json = await response.json()
                    if res_json.get("code") == 200:
                        data = res_json.get("data", {})
                        success_flag = data.get("successFlag")
                        
                        # successFlag: 0=Generating, 1=Success, 2=Failed, 3=Generation Failed
                        if success_flag == 1:
                            video_url = data.get("response", {}).get("resultUrls", [None])[0]
                            if video_url:
                                return VideoOutput(fmt="url", ext="mp4", data=video_url, metadata={"task_id": task_id})
                        elif success_flag in [2, 3]:
                            error_msg = data.get("errorMessage") or res_json.get("msg", "Unknown error")
                            raise RuntimeError(f"KieAI task failed (flag {success_flag}): {error_msg}")
                    
                    logging.info(f"KieAI task {task_id} status: {res_json.get('msg', 'pending')}, waiting...")
                    await asyncio.sleep(10)
        
        raise TimeoutError(f"KieAI task {task_id} timed out.")

    async def extend_video(
        self,
        task_id: str,
        prompt: str,
        **kwargs,
    ) -> VideoOutput:
        """Extend an existing KieAI video by 7 seconds."""
        if self.rate_limiter:
            await self.rate_limiter.acquire()
            
        logging.info(f"Calling KieAI extend for task {task_id}...")
        
        payload = {
            "taskId": task_id,
            "prompt": prompt
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/veo/extend", headers=headers, json=payload) as response:
                    res_json = await response.json()
                    if res_json.get("code") != 200:
                        raise RuntimeError(f"KieAI extension failed to create: {res_json}")
                    
                    new_task_id = res_json["data"]["taskId"]
                    logging.info(f"KieAI extension task created: {new_task_id}")
                    
            return await self._poll_task(new_task_id, headers, timeout=kwargs.get("timeout", 600))
            
        except Exception as e:
            logging.error(f"KieAI video extension failed: {e}")
            raise

    async def generate_single_video(
        self,
        prompt: str = "",
        reference_image_paths: List[str] = [],
        aspect_ratio: str = "16:9",
        **kwargs,
    ) -> VideoOutput:
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        model = self.t2v_model if not reference_image_paths else self.ff2v_model
        
        logging.info(f"Calling KieAI {model} to generate video...")

        # Map aspect ratios to KieAI format (they seem to prefer 16:9 or 9:16)
        if aspect_ratio == "9:16":
            kie_aspect_ratio = "9:16"
        else:
            kie_aspect_ratio = "16:9"

        payload = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": kie_aspect_ratio,
            "generationType": "TEXT_2_VIDEO" if not reference_image_paths else "FIRST_AND_LAST_FRAMES_2_VIDEO"
        }
        
        if reference_image_paths:
            if not self.piapi_client:
                raise RuntimeError("KieAI requires image URLs for image-to-video, but no PiAPI key provided for upload fallback.")
            
            image_urls = []
            for path in reference_image_paths:
                if path.startswith("http"):
                    image_urls.append(path)
                else:
                    logging.info(f"Uploading reference image to ephemeral storage: {path}")
                    url = await self.piapi_client.upload_file(path)
                    image_urls.append(url)
            payload["imageUrls"] = image_urls

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/veo/generate", headers=headers, json=payload) as response:
                    res_json = await response.json()
                    if res_json.get("code") != 200:
                        # Check for specific "insufficient credits" error to potentially fallback
                        if res_json.get("code") == 402:
                            logging.warning("KieAI insufficient credits, will attempt fallback.")
                        raise RuntimeError(f"KieAI task creation failed: {res_json}")
                    task_id = res_json["data"]["taskId"]
                    logging.info(f"KieAI task created: {task_id}")

            return await self._poll_task(task_id, headers, timeout=kwargs.get("timeout", 600))
            
        except Exception as e:
            if self.enable_piapi_fallback and self.piapi_api_key:
                logging.warning(f"KieAI generation failed or error occurred, falling back to PiAPI: {e}")
                piapi = PiAPIVideoGenerator(api_key=self.piapi_api_key)
                return await piapi.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
            raise
