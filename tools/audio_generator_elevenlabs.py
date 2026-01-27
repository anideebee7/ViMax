import logging
import os
from typing import Optional, Dict, Any

import aiohttp

from utils.core.rate_limiter import RateLimiter


class AudioGeneratorElevenLabs:
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
        voice_id: Optional[str] = None,
        voice_settings: Optional[Dict[str, float]] = None,
    ) -> str:
        if not prompt and not composition_plan:
            raise ValueError("Either prompt or composition_plan must be provided.")
        if prompt and composition_plan:
            raise ValueError("Provide only prompt or composition_plan, not both.")

        if self.rate_limiter:
            await self.rate_limiter.acquire()

        payload: Dict[str, Any] = {
            "model_id": self.model_id,
            "force_instrumental": force_instrumental,
        }
        
        if voice_id:
            payload["voice_id"] = voice_id
        if voice_settings:
            payload["voice_settings"] = voice_settings

        if music_length_ms is not None:
            payload["music_length_ms"] = int(music_length_ms)

        if composition_plan:
            payload["composition_plan"] = composition_plan
        else:
            payload["prompt"] = prompt

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {}
        if self.output_format:
            params["output_format"] = self.output_format

        url = f"{self.base_url}/music"
        self.logger.info("Requesting ElevenLabs music compose.")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as response:
                response.raise_for_status()
                audio_bytes = await response.read()

        if not output_path:
            raise ValueError("output_path is required to save the audio file.")

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        self.logger.info("Saved ElevenLabs audio to %s", output_path)
        return output_path
    
    async def text_to_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Default: Rachel
        model_id: str = "eleven_multilingual_v2",
        voice_settings: Optional[Dict[str, float]] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Convert text to speech using ElevenLabs TTS API.
        
        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID (default: Rachel)
            model_id: Model to use (eleven_multilingual_v2 or eleven_turbo_v2)
            voice_settings: Optional voice settings (stability, similarity_boost, etc.)
            output_path: Path to save the audio file
        
        Returns:
            Path to generated audio file
        """
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        if not output_path:
            raise ValueError("output_path is required to save the audio file.")
        
        url = f"{self.base_url}/text-to-speech/{voice_id}"
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings or {
                "stability": 0.5,
                "similarity_boost": 0.75,
            }
        }
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        
        params = {}
        if self.output_format:
            params["output_format"] = self.output_format
        
        self.logger.info(f"Requesting ElevenLabs TTS for {len(text)} characters...")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"ElevenLabs TTS API error ({response.status}): {error_text}")
                    response.raise_for_status()
                audio_bytes = await response.read()
        
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        
        self.logger.info("Saved ElevenLabs TTS audio to %s", output_path)
        return output_path
