import logging
import os
from typing import Optional

from utils.core.piapi_client import PiAPIClient
from utils.core.rate_limiter import RateLimiter


class PiAPIAudioGenerator:
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        task_type: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        music_model: Optional[str] = None,
        music_task_type: Optional[str] = None,
    ):
        self.client = PiAPIClient(api_key=api_key)
        self.model = model or os.getenv("PIAPI_AUDIO_MODEL") or "Qubico/mmaudio"
        self.task_type = task_type or os.getenv("PIAPI_AUDIO_TASK_TYPE") or "video2audio"
        self.music_model = music_model or os.getenv("PIAPI_MUSIC_MODEL") or "suno"
        
        # Auto-detect music task type if not provided
        if music_task_type:
            self.music_task_type = music_task_type
        elif os.getenv("PIAPI_MUSIC_TASK_TYPE"):
            self.music_task_type = os.getenv("PIAPI_MUSIC_TASK_TYPE")
        elif self.music_model == "music-u":
            self.music_task_type = "generate_music"
        else:
            self.music_task_type = "music"
            
        self.rate_limiter = rate_limiter

    async def generate_audio_from_video(
        self,
        video_url: str,
        prompt: str = "",
        negative_prompt: str = "",
        steps: int = 20,
        seed: Optional[int] = None,
        **kwargs,
    ) -> str:
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        input_data = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "video": video_url,
            "steps": steps,
        }
        if seed is not None:
            input_data["seed"] = seed

        response = await self.client.create_task(
            model=self.model,
            task_type=self.task_type,
            input_data=input_data,
        )

        data = response.get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"PiAPI audio task creation failed: {response}")

        result = await self.client.wait_for_task(task_id)
        output = result.get("data", {}).get("output", {}) or {}
        audio_url = output.get("audio") or output.get("audio_url")
        if not audio_url:
            logging.warning("PiAPI audio task completed without audio URL.")
        return audio_url or ""

    async def generate_music(
        self,
        prompt: str,
        lyrics: Optional[str] = None,
        style: Optional[str] = None,
        lyrics_type: Optional[str] = None,
        **kwargs,
    ) -> str:
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # Build input data based on model type
        if self.music_model.startswith("suno"):
            # Suno models on PiAPI
            # In Custom Mode: 'prompt' is lyrics, 'tags' is style
            # In Prompt Mode: 'gpt_description_prompt' is description
            if lyrics:
                input_data = {
                    "prompt": lyrics,
                    "tags": style or prompt,
                    "mv": "chirp-crow",
                }
            else:
                input_data = {
                    "gpt_description_prompt": prompt,
                    "tags": style or "",
                    "mv": "chirp-crow",
                }
        elif self.music_model == "music-u":
            # Udio model on PiAPI
            input_data = {
                "prompt": prompt,
                "lyrics": lyrics or "",
                "lyrics_type": "user" if lyrics else "generate",
            }
            if style:
                # Udio often takes style in prompt or tags, PiAPI docs for music-u 
                # show gpt_description_prompt or prompt.
                input_data["prompt"] = f"{prompt}. Style: {style}"
        else:
            # Other models (fallback to generic structure)
            input_data = {"prompt": prompt}
            if lyrics:
                input_data["lyrics"] = lyrics
            if style:
                input_data["style"] = style
            
            # Special handling for music-u if it's not explicitly caught above
            if self.music_model == "music-u":
                input_data["lyrics_type"] = "user" if lyrics else "generate"
        
        if kwargs:
            input_data.update(kwargs)

        response = await self.client.create_task(
            model=self.music_model,
            task_type=self.music_task_type,
            input_data=input_data,
        )

        data = response.get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"PiAPI music task creation failed: {response}")

        result = await self.client.wait_for_task(task_id)
        output = result.get("data", {}).get("output", {}) or {}
        # music-u returns songs array, others return audio/audio_url
        songs = output.get("songs")
        if songs and isinstance(songs, list) and len(songs) > 0:
            audio_url = songs[0].get("audio_url") or songs[0].get("song_path")
        else:
            audio_url = output.get("audio") or output.get("audio_url")
        if not audio_url:
            logging.warning("PiAPI music task completed without audio URL. Output: %s", output)
        return audio_url or ""
    
    async def generate_music_and_save(
        self,
        prompt: str,
        output_path: str,
        lyrics: Optional[str] = None,
        style: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Generate music and save to file.
        
        Args:
            prompt: Music generation prompt
            output_path: Path to save the audio file
            lyrics: Optional lyrics
            style: Optional style description
            duration_seconds: Optional duration in seconds (note: PiAPI/Udio may have fixed durations)
            **kwargs: Additional parameters
        
        Returns:
            Path to saved audio file, or None if generation failed
        """
        try:
            audio_url = await self.generate_music(
                prompt=prompt,
                lyrics=lyrics,
                style=style,
                **kwargs,
            )
            
            if not audio_url:
                logging.warning("PiAPI music generation returned no audio URL")
                return None
            
            # Download audio file
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as response:
                    response.raise_for_status()
                    audio_bytes = await response.read()
            
            # Save to file
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            
            logging.info(f"Saved PiAPI/Udio audio to {output_path}")
            return output_path
        except Exception as e:
            logging.error(f"Failed to generate and save music via PiAPI: {e}")
            return None
