"""
Audio planning interfaces for scene and shot-level audio requirements.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from enum import Enum


class AudioType(str, Enum):
    """Types of audio content"""
    DIALOGUE = "dialogue"  # Character dialogue/speech
    VOICE_OVER = "voice_over"  # Narrator voice-over
    DUBBING = "dubbing"  # Dubbing for existing video
    NARRATION = "narration"  # Documentary-style narration
    BACKGROUND_MUSIC = "background_music"  # Background music/soundtrack
    MUSIC_SEGMENT = "music_segment"  # Standalone music/song segment (e.g., musical number, montage)
    SONG = "song"  # Full song with lyrics (musical number, karaoke, etc.)
    SOUND_EFFECTS = "sound_effects"  # Sound effects
    AMBIENT = "ambient"  # Ambient sounds
    SILENT = "silent"  # No audio needed


class AudioRequirement(BaseModel):
    """Audio requirement for a shot or scene"""
    audio_type: AudioType = Field(
        description="Type of audio content needed"
    )
    text: Optional[str] = Field(
        default=None,
        description="Text to be spoken/narrated (for dialogue, voice-over, narration, dubbing)"
    )
    character_id: Optional[str] = Field(
        default=None,
        description="Character identifier for dialogue/dubbing (e.g., '<Alice>', 'Narrator')"
    )
    emotion: Optional[str] = Field(
        default=None,
        description="Emotion/tone for delivery (e.g., 'happy', 'sad', 'urgent', 'calm')"
    )
    voice_style: Optional[str] = Field(
        default=None,
        description="Voice style description (e.g., 'deep male voice', 'childlike', 'authoritative')"
    )
    lip_sync_required: bool = Field(
        default=False,
        description="Whether lip-sync is required (for dialogue/dubbing when character is visible)"
    )
    timing_start: Optional[float] = Field(
        default=None,
        description="Start time in seconds within the shot/scene"
    )
    timing_end: Optional[float] = Field(
        default=None,
        description="End time in seconds within the shot/scene"
    )
    background_music_style: Optional[str] = Field(
        default=None,
        description="Style of background music if needed (e.g., 'energetic', 'melancholic', 'suspenseful')"
    )
    sound_effects: Optional[List[str]] = Field(
        default=None,
        description="List of sound effects needed (e.g., ['footsteps', 'door creak', 'wind'])"
    )
    lyrics: Optional[str] = Field(
        default=None,
        description="Lyrics for song/music segment (if audio_type is SONG or MUSIC_SEGMENT)"
    )
    music_style: Optional[str] = Field(
        default=None,
        description="Style/genre of music (e.g., 'upbeat pop', 'emotional ballad', 'energetic rock', 'cinematic orchestral')"
    )
    music_duration: Optional[float] = Field(
        default=None,
        description="Duration of music segment in seconds (for MUSIC_SEGMENT or SONG)"
    )
    is_musical_number: bool = Field(
        default=False,
        description="Whether this is a full musical number (characters singing, dance sequence, etc.)"
    )
    priority: Literal["critical", "important", "optional"] = Field(
        default="important",
        description="Priority level of this audio requirement"
    )


class ShotAudioPlan(BaseModel):
    """Audio plan for a single shot"""
    shot_idx: int = Field(
        description="Index of the shot"
    )
    requirements: List[AudioRequirement] = Field(
        default_factory=list,
        description="List of audio requirements for this shot"
    )
    estimated_duration: Optional[float] = Field(
        default=None,
        description="Estimated duration of the shot in seconds"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about audio for this shot"
    )


class SceneAudioPlan(BaseModel):
    """Audio plan for a scene"""
    scene_idx: int = Field(
        description="Index of the scene"
    )
    shot_plans: List[ShotAudioPlan] = Field(
        default_factory=list,
        description="Audio plans for each shot in the scene"
    )
    overall_audio_type: AudioType = Field(
        description="Overall audio type for the scene"
    )
    continuity_notes: Optional[str] = Field(
        default=None,
        description="Notes about audio continuity from previous scenes"
    )
    character_voice_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Mapping of character identifiers to voice IDs/styles for consistency"
    )


class AudioPlan(BaseModel):
    """Complete audio plan for a script/movie"""
    scene_plans: List[SceneAudioPlan] = Field(
        default_factory=list,
        description="Audio plans for each scene"
    )
    global_voice_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Global mapping of character identifiers to voice IDs/styles"
    )
    background_music_theme: Optional[str] = Field(
        default=None,
        description="Overall background music theme for the content"
    )
    audio_style_guide: Optional[str] = Field(
        default=None,
        description="Style guide for audio production (tone, pacing, etc.)"
    )
