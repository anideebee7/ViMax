import logging
import os
from typing import Optional, Dict, Any

import aiohttp

from utils.core.rate_limiter import RateLimiter


class ElevenLabsAudioGenerator:
    def __init__(
        self,
        api_key: str,
        model_id: Optional[str] = None,
        output_format: Optional[str] = None,
        base_url: str = "https://api.elevenlabs.io/v1",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.model_id = model_id or os.getenv("ELEVENLABS_MODEL") or "music_v1"
        self.output_format = output_format or os.getenv("ELEVENLABS_OUTPUT_FORMAT") or "mp3_44100_128"
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.logger = logging.getLogger(__name__)

    async def compose_music(
        self,
        prompt: Optional[str],
        composition_plan: Optional[Dict[str, Any]] = None,
        music_length_ms: Optional[int] = None,
        force_instrumental: bool = False,
        output_path: Optional[str] = None,
    ) -> str:
        if not prompt and not composition_plan:
            raise ValueError("Either prompt or composition_plan must be provided.")

        if self.rate_limiter:
            await self.rate_limiter.acquire()

        payload: Dict[str, Any] = {
            "model_id": self.model_id,
            "force_instrumental": force_instrumental,
        }
        
        if composition_plan:
            # When using composition_plan, do NOT include prompt or music_length_ms (API requirement)
            payload["composition_plan"] = composition_plan
            if prompt:
                self.logger.debug("Prompt provided with composition_plan; ignoring prompt per API requirements.")
            if music_length_ms is not None:
                self.logger.debug("music_length_ms provided with composition_plan; ignoring per API requirements.")
        else:
            payload["prompt"] = prompt
            # music_length_ms is only used with prompt
            if music_length_ms is not None:
                payload["music_length_ms"] = int(music_length_ms)

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {}
        if self.output_format:
            params["output_format"] = self.output_format

        # Use detailed endpoint if composition_plan is provided
        endpoint = "music/detailed" if composition_plan else "music"
        url = f"{self.base_url}/{endpoint}"
        
        self.logger.info(f"Requesting ElevenLabs music compose ({endpoint}).")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"ElevenLabs API error ({response.status}): {error_text}")
                    response.raise_for_status()
                audio_bytes = await response.read()

        if not output_path:
            raise ValueError("output_path is required to save the audio file.")

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        self.logger.info("Saved ElevenLabs audio to %s", output_path)
        return output_path
