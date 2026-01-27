"""
Music and Song Generation Utilities

Generates standalone music segments and songs (with lyrics) for insertion into videos.
Supports musical numbers, montages, and song sequences.
"""
import os
import logging
from typing import Optional, Dict, Any, List
from interfaces.content.audio_plan import AudioRequirement, AudioType

logger = logging.getLogger(__name__)


async def generate_music_segment(
    music_style: str,
    duration_seconds: float,
    lyrics: Optional[str] = None,
    is_song: bool = False,
    output_path: str = "music_segment.mp3",
    force_regenerate: bool = False,
) -> Optional[str]:
    """
    Generate a standalone music segment or song.
    
    Args:
        music_style: Style/genre of music (e.g., 'upbeat pop', 'emotional ballad')
        duration_seconds: Duration of the music segment
        lyrics: Optional lyrics for song generation
        is_song: Whether this is a full song (with vocals) or instrumental
        output_path: Path to save the audio file
        force_regenerate: Whether to regenerate even if file exists
    
    Returns:
        Path to generated audio file, or None if generation failed
    """
    if os.path.exists(output_path) and not force_regenerate:
        logger.info(f"Music segment already exists: {output_path}")
        return output_path
    
    # Try ElevenLabs first (supports music composition)
    try:
        from tools.audio_generator_elevenlabs import AudioGeneratorElevenLabs
        
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        if elevenlabs_key:
            logger.info(f"Generating music segment with ElevenLabs: {music_style} ({duration_seconds}s)")
            audio_gen = AudioGeneratorElevenLabs(api_key=elevenlabs_key)
            
            # Build prompt for music generation
            if lyrics and is_song:
                # Full song with lyrics
                prompt = f"Song in {music_style} style. Lyrics: {lyrics}"
                force_instrumental = False
            elif lyrics:
                # Music with vocal elements but not full song
                prompt = f"Music in {music_style} style with vocal elements. Lyrics: {lyrics}"
                force_instrumental = False
            else:
                # Instrumental music
                prompt = f"Instrumental music in {music_style} style"
                force_instrumental = True
            
            total_duration_ms = int(duration_seconds * 1000)
            
            await audio_gen.compose_music(
                prompt=prompt[:500],  # Limit prompt length
                music_length_ms=total_duration_ms,
                output_path=output_path,
                force_instrumental=force_instrumental,
            )
            
            if os.path.exists(output_path):
                logger.info(f"Generated music segment: {output_path}")
                return output_path
            else:
                logger.warning("ElevenLabs generation completed but file not found, trying fallback...")
        else:
            logger.info("ELEVENLABS_API_KEY not set, trying PiAPI/Udio fallback...")
    except Exception as e:
        logger.warning(f"ElevenLabs music generation failed: {e}. Trying PiAPI/Udio fallback...")
    
    # Fallback to Udio via PiAPI
    try:
        from tools.generators.audio.piapi import PiAPIAudioGenerator
        from utils.core.rate_limiter import RateLimiter
        
        piapi_key = os.getenv("PIAPI_API_KEY")
        if not piapi_key:
            logger.warning("PIAPI_API_KEY not set, cannot use Udio fallback")
            return None
        
        logger.info(f"Generating music segment with Udio via PiAPI: {music_style} ({duration_seconds}s)")
        
        music_model = os.getenv("PIAPI_MUSIC_MODEL") or "music-u"
        rate_limiter = RateLimiter(max_calls=10, time_window=60)
        
        audio_gen = PiAPIAudioGenerator(
            api_key=piapi_key,
            music_model=music_model,
            rate_limiter=rate_limiter,
        )
        
        # Build prompt for Udio
        if lyrics and is_song:
            # Full song with lyrics
            prompt = f"{music_style} song"
            style_hint = music_style
        else:
            # Instrumental or music with minimal vocals
            prompt = f"{music_style} instrumental music"
            style_hint = music_style
        
        # Generate and save music
        result_path = await audio_gen.generate_music_and_save(
            prompt=prompt,
            lyrics=lyrics if lyrics and is_song else None,
            style=style_hint,
            output_path=output_path,
            duration_seconds=duration_seconds,
        )
        
        if result_path and os.path.exists(result_path):
            logger.info(f"Generated music segment with Udio via PiAPI: {result_path}")
            return result_path
        else:
            logger.warning("Udio via PiAPI generation completed but file not found")
            return None
    except Exception as e:
        logger.error(f"Failed to generate music with Udio via PiAPI: {e}")
        return None


async def generate_music_segments_from_plan(
    audio_plan: Any,  # AudioPlan
    working_dir: str = ".",
    force_regenerate: bool = False,
) -> Dict[int, Dict[str, Any]]:
    """
    Generate all music segments and songs from an AudioPlan.
    
    Args:
        audio_plan: Complete AudioPlan with scene and shot-level requirements
        working_dir: Working directory for output files
        force_regenerate: Whether to regenerate even if files exist
    
    Returns:
        Dict mapping (scene_idx, shot_idx) to music segment info:
        {
            (scene_idx, shot_idx): {
                "audio_path": str,
                "duration": float,
                "music_style": str,
                "is_song": bool,
            }
        }
    """
    music_segments = {}
    
    for scene_plan in audio_plan.scene_plans:
        for shot_plan in scene_plan.shot_plans:
            for req in shot_plan.requirements:
                if req.audio_type in [AudioType.MUSIC_SEGMENT, AudioType.SONG]:
                    # Generate music segment
                    music_path = os.path.join(
                        working_dir,
                        f"music_scene_{scene_plan.scene_idx}_shot_{shot_plan.shot_idx}.mp3"
                    )
                    
                    duration = req.music_duration or (shot_plan.estimated_duration or 30.0)
                    music_style = req.music_style or req.background_music_style or "cinematic"
                    is_song = req.audio_type == AudioType.SONG or req.is_musical_number
                    
                    generated_path = await generate_music_segment(
                        music_style=music_style,
                        duration_seconds=duration,
                        lyrics=req.lyrics,
                        is_song=is_song,
                        output_path=music_path,
                        force_regenerate=force_regenerate,
                    )
                    
                    if generated_path:
                        music_segments[(scene_plan.scene_idx, shot_plan.shot_idx)] = {
                            "audio_path": generated_path,
                            "duration": duration,
                            "music_style": music_style,
                            "is_song": is_song,
                            "lyrics": req.lyrics,
                        }
                        logger.info(
                            f"Generated music segment for scene {scene_plan.scene_idx}, "
                            f"shot {shot_plan.shot_idx}: {music_style} ({duration}s)"
                        )
    
    return music_segments
