"""
Voice generation utilities for dialogue, voice-over, and narration.
Uses AudioPlan to generate voice tracks with proper timing and character mapping.
"""
import os
import logging
from typing import List, Optional, Dict
from moviepy import AudioFileClip, concatenate_audioclips
from interfaces.content.audio_plan import AudioPlan, AudioRequirement, AudioType

logger = logging.getLogger(__name__)


async def generate_voice_from_text(
    text: str,
    character_id: Optional[str] = None,
    emotion: Optional[str] = None,
    voice_style: Optional[str] = None,
    output_path: str = "voice.mp3",
    voice_id: Optional[str] = None,
    voice_memory: Optional[Any] = None,  # VoiceMemory instance
) -> Optional[str]:
    """
    Generate voice audio from text using ElevenLabs TTS.
    
    Args:
        text: Text to convert to speech
        character_id: Character identifier (for voice consistency)
        emotion: Emotion/tone for delivery
        voice_style: Voice style description
        output_path: Path to save the audio file
        voice_id: Optional ElevenLabs voice ID (for character consistency)
    
    Returns:
        Path to generated audio file, or None if generation failed
    """
    try:
        from tools.audio_generator_elevenlabs import AudioGeneratorElevenLabs
        
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        if not elevenlabs_key:
            logger.warning("ELEVENLABS_API_KEY not set, cannot generate voice")
            return None
        
        audio_gen = AudioGeneratorElevenLabs(api_key=elevenlabs_key)
        
        # Build voice settings from emotion and style
        voice_settings = {}
        if emotion:
            # Map emotions to voice settings (stability, similarity_boost, etc.)
            emotion_map = {
                "happy": {"stability": 0.5, "similarity_boost": 0.75},
                "sad": {"stability": 0.7, "similarity_boost": 0.65},
                "angry": {"stability": 0.4, "similarity_boost": 0.8},
                "calm": {"stability": 0.8, "similarity_boost": 0.7},
                "urgent": {"stability": 0.3, "similarity_boost": 0.85},
            }
            if emotion.lower() in emotion_map:
                voice_settings.update(emotion_map[emotion.lower()])
        
        # Use ElevenLabs TTS API
        audio_gen = AudioGeneratorElevenLabs(api_key=elevenlabs_key)
        
        # Get voice ID from voice memory if available
        voice_settings_to_use = voice_settings
        if not voice_id and character_id and voice_memory:
            character_voice = voice_memory.get_character_voice(character_id)
            if character_voice:
                voice_id = character_voice.voice_id
                # Use voice settings from memory if not provided
                if not voice_settings_to_use:
                    voice_settings_to_use = character_voice.voice_settings
                logger.info(f"Using voice from memory for '{character_id}': {character_voice.voice_name} (ID: {voice_id})")
        
        # Get or create voice ID for character
        if not voice_id and character_id:
            # Try to get voice ID from character mapping or use default
            # For now, use a default voice - in production, maintain a voice_id mapping
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice (Rachel)
        
        if not voice_id:
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice
        
        # Generate TTS
        voice_path = await audio_gen.text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            voice_settings=voice_settings_to_use if voice_settings_to_use else None,
            output_path=output_path,
        )
        
        return voice_path
    except Exception as e:
        logger.error(f"Failed to generate voice: {e}")
        return None


async def generate_audio_track_from_plan(
    audio_plan: AudioPlan,
    video_duration: float,
    output_path: str = "final_audio_with_voice.mp3",
    working_dir: str = ".",
    force_regenerate: bool = False,
    voice_memory: Optional[Any] = None,  # VoiceMemory instance
) -> Optional[str]:
    """
    Generate complete audio track from AudioPlan including dialogue, voice-over, and background music.
    
    Args:
        audio_plan: Complete AudioPlan with scene and shot-level requirements
        video_duration: Total video duration in seconds
        output_path: Path to save the final mixed audio file
        working_dir: Working directory for temporary audio files
        force_regenerate: Whether to regenerate even if file exists
    
    Returns:
        Path to generated audio file, or None if generation failed
    """
    if os.path.exists(output_path) and not force_regenerate:
        logger.info(f"Audio track already exists: {output_path}")
        return output_path
    
    try:
        from utils.pipeline.audio_helper import generate_audio_for_video
        
        # Collect all audio requirements
        dialogue_tracks = []  # List of (start_time, end_time, audio_path)
        voice_over_tracks = []
        narration_tracks = []
        background_music_style = None
        sound_effects_list = []
        
        current_time = 0.0
        
        for scene_plan in audio_plan.scene_plans:
            for shot_plan in scene_plan.shot_plans:
                shot_start_time = current_time
                shot_duration = shot_plan.estimated_duration or 5.0  # Default 5 seconds
                
                for req in shot_plan.requirements:
                    if req.audio_type == AudioType.DIALOGUE and req.text:
                        # Generate dialogue voice
                        dialogue_path = os.path.join(working_dir, f"dialogue_shot_{shot_plan.shot_idx}_req_{req.character_id or 'unknown'}.mp3")
                        voice_path = await generate_voice_from_text(
                            text=req.text,
                            character_id=req.character_id,
                            emotion=req.emotion,
                            voice_style=req.voice_style,
                            output_path=dialogue_path,
                            voice_memory=voice_memory,
                        )
                        if voice_path:
                            req_start = req.timing_start if req.timing_start is not None else 0.0
                            req_end = req.timing_end if req.timing_end is not None else shot_duration
                            dialogue_tracks.append((shot_start_time + req_start, shot_start_time + req_end, voice_path))
                    
                    elif req.audio_type == AudioType.VOICE_OVER and req.text:
                        # Generate voice-over
                        vo_path = os.path.join(working_dir, f"voiceover_shot_{shot_plan.shot_idx}.mp3")
                        # Use voice-over memory for narrator consistency
                        narrator_voice_id = None
                        if voice_memory and voice_memory.get_voiceover_memory():
                            narrator_voice_id = voice_memory.get_voiceover_memory().narrator_voice_id
                        
                        voice_path = await generate_voice_from_text(
                            text=req.text,
                            character_id=req.character_id or "Narrator",
                            emotion=req.emotion,
                            voice_style=req.voice_style,
                            output_path=vo_path,
                            voice_id=narrator_voice_id,
                            voice_memory=voice_memory,
                        )
                        if voice_path:
                            req_start = req.timing_start if req.timing_start is not None else 0.0
                            req_end = req.timing_end if req.timing_end is not None else shot_duration
                            voice_over_tracks.append((shot_start_time + req_start, shot_start_time + req_end, voice_path))
                    
                    elif req.audio_type == AudioType.NARRATION and req.text:
                        # Generate narration
                        nar_path = os.path.join(working_dir, f"narration_shot_{shot_plan.shot_idx}.mp3")
                        # Use voice-over memory for narrator consistency
                        narrator_voice_id = None
                        if voice_memory and voice_memory.get_voiceover_memory():
                            narrator_voice_id = voice_memory.get_voiceover_memory().narrator_voice_id
                        
                        voice_path = await generate_voice_from_text(
                            text=req.text,
                            character_id="Narrator",
                            emotion=req.emotion,
                            voice_style=req.voice_style or "authoritative, clear",
                            output_path=nar_path,
                            voice_id=narrator_voice_id,
                            voice_memory=voice_memory,
                        )
                        if voice_path:
                            req_start = req.timing_start if req.timing_start is not None else 0.0
                            req_end = req.timing_end if req.timing_end is not None else shot_duration
                            narration_tracks.append((shot_start_time + req_start, shot_start_time + req_end, voice_path))
                    
                    elif req.audio_type == AudioType.BACKGROUND_MUSIC:
                        if req.background_music_style:
                            background_music_style = req.background_music_style
                    
                    elif req.audio_type == AudioType.SOUND_EFFECTS and req.sound_effects:
                        sound_effects_list.extend(req.sound_effects)
                
                current_time += shot_duration
        
        # Generate background music
        bg_music_path = os.path.join(working_dir, "background_music.mp3")
        audio_descriptions = []
        if background_music_style:
            audio_descriptions.append(background_music_style)
        if sound_effects_list:
            audio_descriptions.append(f"Sound effects: {', '.join(sound_effects_list)}")
        
        bg_music = await generate_audio_for_video(
            video_duration=video_duration,
            audio_descriptions=audio_descriptions if audio_descriptions else None,
            output_path=bg_music_path,
            force_regenerate=force_regenerate,
        )
        
        # Mix all audio tracks together
        if dialogue_tracks or voice_over_tracks or narration_tracks or bg_music:
            from moviepy import CompositeAudioClip
            
            # Load background music
            audio_clips = []
            if bg_music and os.path.exists(bg_music):
                bg_clip = AudioFileClip(bg_music)
                if bg_clip.duration < video_duration:
                    # Loop background music
                    loops_needed = int(video_duration / bg_clip.duration) + 1
                    bg_clips = [bg_clip] * loops_needed
                    bg_clip = concatenate_audioclips(bg_clips).subclip(0, video_duration)
                else:
                    bg_clip = bg_clip.subclip(0, video_duration)
                audio_clips.append(bg_clip.volumex(0.3))  # Lower volume for background
            
            # Add dialogue/voice-over/narration tracks at their timing
            # Build a timeline: create clips positioned at their start times
            from moviepy import CompositeAudioClip
            
            voice_tracks = []  # List of (start_time, clip) tuples
            for start_time, end_time, voice_path in dialogue_tracks + voice_over_tracks + narration_tracks:
                if os.path.exists(voice_path):
                    voice_clip = AudioFileClip(voice_path)
                    # Trim to duration if needed
                    clip_duration = min(voice_clip.duration, end_time - start_time)
                    voice_clip = voice_clip.subclip(0, clip_duration)
                    voice_clip = voice_clip.set_start(start_time).volumex(1.0)
                    voice_tracks.append(voice_clip)
            
            # Combine background music with voice tracks
            if voice_tracks:
                # Add background music as base layer
                if bg_music and os.path.exists(bg_music):
                    bg_clip = AudioFileClip(bg_music)
                    if bg_clip.duration < video_duration:
                        loops_needed = int(video_duration / bg_clip.duration) + 1
                        bg_clips = [bg_clip] * loops_needed
                        bg_clip = concatenate_audioclips(bg_clips).subclip(0, video_duration)
                    else:
                        bg_clip = bg_clip.subclip(0, video_duration)
                    bg_clip = bg_clip.volumex(0.3)  # Lower volume for background
                    voice_tracks.insert(0, bg_clip)
                
                final_audio = CompositeAudioClip(voice_tracks)
            elif bg_music and os.path.exists(bg_music):
                # Only background music
                bg_clip = AudioFileClip(bg_music)
                if bg_clip.duration < video_duration:
                    loops_needed = int(video_duration / bg_clip.duration) + 1
                    bg_clips = [bg_clip] * loops_needed
                    final_audio = concatenate_audioclips(bg_clips).subclip(0, video_duration)
                else:
                    final_audio = bg_clip.subclip(0, video_duration)
            else:
                logger.warning("No audio tracks to mix")
                return None
            
            # Write final audio
            final_audio = final_audio.subclip(0, video_duration)
            final_audio.write_audiofile(output_path, codec="aac", bitrate="192k")
            
            # Cleanup
            for clip in voice_tracks:
                clip.close()
            final_audio.close()
            
            logger.info(f"Generated complete audio track with voice: {output_path}")
            return output_path
        
        # Fallback: just background music
        if bg_music and os.path.exists(bg_music):
            return bg_music
        
        return None
    except Exception as e:
        logger.error(f"Failed to generate audio track from plan: {e}")
        return None
