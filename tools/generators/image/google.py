# https://ai.google.dev/gemini-api/docs/image-generation

import logging
import asyncio
import os
from PIL import Image
from typing import List, Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt
from interfaces.output.image_output import ImageOutput
from utils.core.retry import after_func
from utils.core.rate_limiter import RateLimiter
from .piapi import PiAPIImageGenerator


class GoogleImageGenerator:
    def __init__(
        self,
        api_key: str,
        rate_limiter: Optional[RateLimiter] = None,
        piapi_api_key: Optional[str] = None,
        enable_piapi_fallback: bool = True,
    ):
        self.model = "gemini-2.5-flash-image"
        self.rate_limiter = rate_limiter
        self.client = genai.Client(
            api_key=api_key,
        )
        self.piapi_api_key = piapi_api_key or os.getenv("PIAPI_API_KEY")
        self.enable_piapi_fallback = enable_piapi_fallback

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        aspect_ratio: Optional[str] = "16:9",
        **kwargs,
    ) -> ImageOutput:

        """
            aspect_ratio: The aspect ratio of the image.
        """

        logging.info(f"Calling {self.model} to generate image...")

        # Apply rate limiting if configured
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        reference_images = [Image.open(path) for path in reference_image_paths]

        # Retry logic for rate limit errors
        max_retries = 3
        retry_delay = 5

        try:
            for attempt in range(max_retries):
                try:
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=reference_images + [prompt],
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            image_config=types.ImageConfig(
                                aspect_ratio=aspect_ratio,
                            ),
                        ),
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
                logging.warning(f"Primary image generation failed, falling back to PiAPI: {e}")
                piapi = PiAPIImageGenerator(api_key=self.piapi_api_key, aspect_ratio=aspect_ratio)
                return await piapi.generate_single_image(
                    prompt=prompt,
                    reference_image_paths=reference_image_paths,
                    aspect_ratio=aspect_ratio,
                )
            raise

        image = None
        text = ""
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                text += part.text
            elif part.inline_data is not None:
                image = part.as_image()

        if image is None:
            logging.error(f"No image generated. The response text is: {text}")
            raise ValueError("No image generated")

        return ImageOutput(fmt="pil", ext="png", data=image)

