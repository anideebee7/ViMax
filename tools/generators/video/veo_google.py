import logging
import os
from typing import List, Optional
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from interfaces.output.video_output import VideoOutput
from utils.core.rate_limiter import RateLimiter
from .piapi import PiAPIVideoGenerator

# https://ai.google.dev/gemini-api/docs/video-generation?hl=zh-cn


class VeoGoogleVideoGenerator:
    def __init__(
        self,
        api_key: str,
        t2v_model: str = "veo-3.1-generate-preview",
        ff2v_model: str = "veo-3.1-generate-preview",
        flf2v_model: str = "veo-3.1-generate-preview",
        rate_limiter: Optional[RateLimiter] = None,
        piapi_api_key: Optional[str] = None,
        enable_piapi_fallback: bool = True,
        default_duration: int = 8,
        default_aspect_ratio: str = "16:9",
    ):
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.ff2v_model = ff2v_model
        self.flf2v_model = flf2v_model
        self.rate_limiter = rate_limiter
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.enable_piapi_fallback = enable_piapi_fallback
        self.default_duration = default_duration
        self.default_aspect_ratio = default_aspect_ratio

        self.client = genai.Client(
            api_key=api_key,
        )
    
    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str = "1080p",
        aspect_ratio: Optional[str] = None,
        duration: Optional[int] = None,
        allow_fallback_to_text: bool = True,
    ) -> VideoOutput:
        # Use instance defaults if not specified
        aspect_ratio = aspect_ratio or self.default_aspect_ratio
        duration = duration or self.default_duration

        params = {
            "prompt": prompt,
        }
        config_params = {
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration_seconds": float(duration),
        }
        
        logging.info(f"Veo request config_params: {config_params}")
        if len(reference_image_paths) == 0:
            params["model"] = self.t2v_model
        elif len(reference_image_paths) == 1:
            params["model"] = self.ff2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
        elif len(reference_image_paths) == 2:
            params["model"] = self.flf2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
            config_params["last_frame"] = types.Image.from_file(location=reference_image_paths[1])
        else:
            raise ValueError("The number of reference images must be no more than 2")

        logging.info(f"Calling {params['model']} to generate video...")

        # Apply rate limiting if configured
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # Retry logic for rate limit errors
        max_retries = 3
        retry_delay = 5

        try:
            for attempt in range(max_retries):
                try:
                    operation = self.client.models.generate_videos(
                        **params,
                        config=types.GenerateVideosConfig(**config_params),
                    )
                    break
                except ClientError as e:
                    # Check if it's a rate limit or quota error (429 or RESOURCE_EXHAUSTED)
                    error_str = str(e)
                    is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()
                    
                    if is_rate_limit and attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logging.warning(f"Rate limit/quota hit, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        raise
        except Exception as e:
            if self.enable_piapi_fallback and self.piapi_api_key:
                logging.warning(f"Primary video generation failed, falling back to PiAPI: {e}")
                piapi = PiAPIVideoGenerator(
                    api_key=self.piapi_api_key,
                    aspect_ratio=aspect_ratio,
                    duration_seconds=duration,
                    resolution="720p",
                    generate_audio=False,
                )
                return await piapi.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                )
            raise

        try:
            while not operation.done:
                await asyncio.sleep(2)
                operation = self.client.operations.get(operation)
                logging.info(f"Video generation not completed, waiting 2 seconds...")

            def _extract_generated_video(response):
                if not response:
                    return None
                if hasattr(response, "generated_videos") and response.generated_videos:
                    return response.generated_videos[0]
                if hasattr(response, "videos") and response.videos:
                    return response.videos[0]
                if hasattr(response, "video") and response.video:
                    return response.video
                return None

            # Check if operation completed successfully
            if operation.error:
                error_msg = f"Video generation failed: {operation.error}"
                logging.error(error_msg)
                raise RuntimeError(error_msg)

            if not operation.response:
                error_msg = "Video generation completed but no response received"
                logging.error(error_msg)
                raise RuntimeError(error_msg)

            generated_video = _extract_generated_video(operation.response)
            if not generated_video:
                response_repr = repr(operation.response)
                filtered_reasons = getattr(operation.response, "rai_media_filtered_reasons", None)
                if (
                    allow_fallback_to_text
                    and reference_image_paths
                    and filtered_reasons
                    and any("remove the reference" in reason.lower() for reason in filtered_reasons)
                ):
                    logging.warning(
                        "Video generation blocked by safety filters for reference images. "
                        "Retrying as text-only video generation."
                    )
                    return await self.generate_single_video(
                        prompt=prompt,
                        reference_image_paths=[],
                        resolution=resolution,
                        aspect_ratio=aspect_ratio,
                        duration=duration,
                        allow_fallback_to_text=False,
                    )

                error_msg = (
                    "Video generation completed but no videos were generated. "
                    f"Response: {response_repr}"
                )
                logging.error(error_msg)
                raise RuntimeError(error_msg)

            video_file = getattr(generated_video, "video", generated_video)
            self.client.files.download(file=video_file)

            video_output = VideoOutput(
                fmt="bytes",
                ext="mp4",
                data=video_file.video_bytes,
            )
            return video_output
        except Exception as e:
            if self.enable_piapi_fallback and self.piapi_api_key:
                logging.warning(f"Video generation failed after start, falling back to PiAPI: {e}")
                piapi = PiAPIVideoGenerator(
                    api_key=self.piapi_api_key,
                    aspect_ratio=aspect_ratio,
                    duration_seconds=duration,
                    resolution="720p",
                    generate_audio=False,
                )
                return await piapi.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                )
            raise
