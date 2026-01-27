"""
Audio generation helper for pipelines.
Provides reusable functions for generating and adding audio to videos.
"""
import os
import logging
from typing import List, Optional
from moviepy import VideoFileClip, AudioFileClip, concatenate_audioclips

logger = logging.getLogger(__name__)


async def generate_audio_for_video(
    video_duration: float,
    audio_descriptions: Optional[List[str]] = None,
    output_path: str = "final_audio.mp3",
    force_regenerate: bool = False,
) -> Optional[str]:
    """
    Generate audio track for a video using ElevenLabs, with fallback to Udio via PiAPI.
    
    Args:
        video_duration: Duration of the video in seconds
        audio_descriptions: List of audio descriptions from shots/scenes
        output_path: Path to save the audio file
        force_regenerate: Whether to regenerate even if file exists
    
    Returns:
        Path to generated audio file, or None if generation failed
    """
    if os.path.exists(output_path) and not force_regenerate:
        logger.info(f"Audio file already exists: {output_path}")
        return output_path
    
    # Create prompt from audio descriptions or use default
    if audio_descriptions:
        audio_prompt = " ".join(audio_descriptions)[:500]  # Limit prompt length
    else:
        audio_prompt = "energetic, upbeat background music for video content"
    
    # Try ElevenLabs first
    try:
        from tools.audio_generator_elevenlabs import AudioGeneratorElevenLabs
        
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        if elevenlabs_key:
            logger.info("Attempting audio generation with ElevenLabs...")
            audio_gen = AudioGeneratorElevenLabs(api_key=elevenlabs_key)
            
            total_duration_ms = int(video_duration * 1000)
            
            await audio_gen.compose_music(
                prompt=audio_prompt,
                music_length_ms=total_duration_ms,
                output_path=output_path,
                force_instrumental=not audio_descriptions or len(audio_descriptions) == 0,
            )
            
            if os.path.exists(output_path):
                logger.info(f"Generated audio track with ElevenLabs: {output_path}")
                return output_path
            else:
                logger.warning("ElevenLabs generation completed but file not found, trying fallback...")
        else:
            logger.info("ELEVENLABS_API_KEY not set, trying PiAPI/Udio fallback...")
    except Exception as e:
        logger.warning(f"ElevenLabs audio generation failed: {e}. Trying PiAPI/Udio fallback...")
    
    # Fallback to Udio via PiAPI
    try:
        from tools.generators.audio.piapi import PiAPIAudioGenerator
        from utils.core.rate_limiter import RateLimiter
        
        piapi_key = os.getenv("PIAPI_API_KEY")
        if not piapi_key:
            logger.warning("PIAPI_API_KEY not set, cannot use Udio fallback")
            return None
        
        logger.info("Attempting audio generation with Udio via PiAPI...")
        
        # Use Udio model (music-u) via PiAPI
        music_model = os.getenv("PIAPI_MUSIC_MODEL") or "music-u"
        rate_limiter = RateLimiter(max_calls=10, time_window=60)  # Reasonable rate limit
        
        audio_gen = PiAPIAudioGenerator(
            api_key=piapi_key,
            music_model=music_model,
            rate_limiter=rate_limiter,
        )
        
        # Generate and save music
        result_path = await audio_gen.generate_music_and_save(
            prompt=audio_prompt,
            output_path=output_path,
            style="instrumental background music" if not audio_descriptions or len(audio_descriptions) == 0 else None,
            duration_seconds=video_duration,  # Note: Udio may have fixed durations, but we pass it anyway
        )
        
        if result_path and os.path.exists(result_path):
            logger.info(f"Generated audio track with Udio via PiAPI: {result_path}")
            return result_path
        else:
            logger.warning("Udio via PiAPI generation completed but file not found")
            return None
    except Exception as e:
        logger.error(f"Failed to generate audio with Udio via PiAPI: {e}")
        return None


def add_audio_to_video(
    video_clip: VideoFileClip,
    audio_path: str,
    output_path: str,
    codec: str = "libx264",
    audio_codec: str = "aac",
    preset: str = "medium",
) -> bool:
    """
    Add audio track to a video clip and save.
    
    Args:
        video_clip: The video clip to add audio to
        audio_path: Path to the audio file
        output_path: Path to save the final video
        codec: Video codec
        audio_codec: Audio codec
        preset: FFmpeg preset
    
    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(audio_path):
        logger.warning(f"Audio file not found: {audio_path}")
        return False
    
    try:
        audio_clip = AudioFileClip(audio_path)
        
        # Match audio duration to video
        if audio_clip.duration > video_clip.duration:
            audio_clip = audio_clip.subclip(0, video_clip.duration)
        elif audio_clip.duration < video_clip.duration:
            # Loop audio if shorter than video
            loops_needed = int(video_clip.duration / audio_clip.duration) + 1
            audio_clips = [audio_clip] * loops_needed
            audio_clip = concatenate_audioclips(audio_clips).subclip(0, video_clip.duration)
        
        video_with_audio = video_clip.set_audio(audio_clip)
        video_with_audio.write_videofile(output_path, codec=codec, audio_codec=audio_codec, preset=preset)
        audio_clip.close()
        video_with_audio.close()
        
        logger.info(f"Added audio to video: {output_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to add audio to video: {e}")
        return False


async def ensure_video_has_audio(
    video_path: str,
    audio_descriptions: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    force_regenerate: bool = False,
) -> bool:
    """
    Check if a video has audio, and if not, generate and add audio.
    
    Args:
        video_path: Path to the video file
        audio_descriptions: Optional list of audio descriptions for generation
        working_dir: Working directory for audio file (defaults to video's directory)
        force_regenerate: Whether to regenerate audio even if video has audio
    
    Returns:
        True if video now has audio, False otherwise
    """
    if not os.path.exists(video_path):
        logger.warning(f"Video file not found: {video_path}")
        return False
    
    try:
        clip = VideoFileClip(video_path)
        has_audio = clip.audio is not None
        video_duration = clip.duration
        clip.close()
        
        if has_audio and not force_regenerate:
            logger.info(f"Video already has audio: {video_path}")
            return True
        
        # Generate and add audio
        if working_dir is None:
            working_dir = os.path.dirname(video_path)
        audio_path = os.path.join(working_dir, "final_audio.mp3")
        
        generated_audio = await generate_audio_for_video(
            video_duration=video_duration,
            audio_descriptions=audio_descriptions,
            output_path=audio_path,
            force_regenerate=force_regenerate,
        )
        
        if generated_audio and os.path.exists(generated_audio):
            clip = VideoFileClip(video_path)
            if add_audio_to_video(clip, generated_audio, video_path, codec="libx264", audio_codec="aac", preset="medium"):
                clip.close()
                return True
            clip.close()
        
        return False
    except Exception as e:
        logger.warning(f"Failed to ensure video has audio: {e}")
        return False
