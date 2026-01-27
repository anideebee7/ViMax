"""
Voice Memory System for Character Voice Consistency and Dialogue Tracking.

Maintains:
1. Character voice ID mappings (ElevenLabs voice IDs per character)
2. Character dialogue history for continuity
3. Voice-over narrator consistency
4. Cross-episode/series voice continuity
"""
import os
import json
import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CharacterVoice:
    """Voice configuration for a character."""
    character_id: str
    voice_id: str  # ElevenLabs voice ID
    voice_name: str  # Human-readable name (e.g., "Rachel", "Adam")
    model_id: str = "eleven_multilingual_v2"
    voice_settings: Optional[Dict[str, float]] = None  # stability, similarity_boost, etc.
    created_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.voice_settings is None:
            self.voice_settings = {"stability": 0.5, "similarity_boost": 0.75}


@dataclass
class CharacterDialogue:
    """Dialogue spoken by a character for continuity tracking."""
    character_id: str
    text: str
    emotion: Optional[str] = None
    scene_idx: Optional[int] = None
    shot_idx: Optional[int] = None
    timestamp: Optional[str] = None
    context: Optional[str] = None  # Scene/context where dialogue was spoken
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class VoiceOverMemory:
    """Memory for voice-over/narration consistency."""
    narrator_voice_id: str
    narrator_voice_name: str
    style: str  # e.g., "authoritative", "warm", "documentary"
    previous_narration: List[str] = None  # Recent narration text for style consistency
    
    def __post_init__(self):
        if self.previous_narration is None:
            self.previous_narration = []


class VoiceMemory:
    """
    Manages character voice consistency and dialogue tracking across runs.
    
    Persists:
    - Character voice mappings (character_id -> voice_id)
    - Dialogue history for each character
    - Voice-over narrator configuration
    - Cross-episode/series continuity
    """
    
    def __init__(self, working_dir: str, series_id: Optional[str] = None):
        """
        Initialize voice memory system.
        
        Args:
            working_dir: Working directory for persistence
            series_id: Optional series identifier for cross-episode continuity
        """
        self.working_dir = working_dir
        self.series_id = series_id
        
        # File paths
        self.voice_mapping_path = os.path.join(working_dir, "voice_mapping.json")
        self.dialogue_history_path = os.path.join(working_dir, "dialogue_history.json")
        self.voiceover_memory_path = os.path.join(working_dir, "voiceover_memory.json")
        
        # In-memory storage
        self.character_voices: Dict[str, CharacterVoice] = {}
        self.dialogue_history: Dict[str, List[CharacterDialogue]] = {}  # character_id -> dialogues
        self.voiceover_memory: Optional[VoiceOverMemory] = None
        
        # Load existing data
        self.load()
    
    def load(self):
        """Load voice memory from disk."""
        # Load character voice mappings
        if os.path.exists(self.voice_mapping_path):
            try:
                with open(self.voice_mapping_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for char_id, voice_data in data.items():
                        self.character_voices[char_id] = CharacterVoice(**voice_data)
                logger.info(f"Loaded {len(self.character_voices)} character voice mappings")
            except Exception as e:
                logger.warning(f"Failed to load voice mappings: {e}")
        
        # Load dialogue history
        if os.path.exists(self.dialogue_history_path):
            try:
                with open(self.dialogue_history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for char_id, dialogues_data in data.items():
                        self.dialogue_history[char_id] = [
                            CharacterDialogue(**d) for d in dialogues_data
                        ]
                total_dialogues = sum(len(d) for d in self.dialogue_history.values())
                logger.info(f"Loaded {total_dialogues} dialogues for {len(self.dialogue_history)} characters")
            except Exception as e:
                logger.warning(f"Failed to load dialogue history: {e}")
        
        # Load voice-over memory
        if os.path.exists(self.voiceover_memory_path):
            try:
                with open(self.voiceover_memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.voiceover_memory = VoiceOverMemory(**data)
                logger.info("Loaded voice-over memory")
            except Exception as e:
                logger.warning(f"Failed to load voice-over memory: {e}")
    
    def save(self):
        """Save voice memory to disk."""
        os.makedirs(self.working_dir, exist_ok=True)
        
        # Save character voice mappings
        voice_mapping_data = {
            char_id: asdict(voice) for char_id, voice in self.character_voices.items()
        }
        with open(self.voice_mapping_path, "w", encoding="utf-8") as f:
            json.dump(voice_mapping_data, f, indent=2, ensure_ascii=False)
        
        # Save dialogue history
        dialogue_data = {
            char_id: [asdict(d) for d in dialogues]
            for char_id, dialogues in self.dialogue_history.items()
        }
        with open(self.dialogue_history_path, "w", encoding="utf-8") as f:
            json.dump(dialogue_data, f, indent=2, ensure_ascii=False)
        
        # Save voice-over memory
        if self.voiceover_memory:
            with open(self.voiceover_memory_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.voiceover_memory), f, indent=2, ensure_ascii=False)
        
        logger.info("Saved voice memory to disk")
    
    def get_character_voice(self, character_id: str) -> Optional[CharacterVoice]:
        """Get voice configuration for a character."""
        return self.character_voices.get(character_id)
    
    def set_character_voice(
        self,
        character_id: str,
        voice_id: str,
        voice_name: str,
        model_id: str = "eleven_multilingual_v2",
        voice_settings: Optional[Dict[str, float]] = None,
    ):
        """Set or update voice configuration for a character."""
        self.character_voices[character_id] = CharacterVoice(
            character_id=character_id,
            voice_id=voice_id,
            voice_name=voice_name,
            model_id=model_id,
            voice_settings=voice_settings,
        )
        self.save()
        logger.info(f"Set voice for character '{character_id}': {voice_name} (ID: {voice_id})")
    
    def add_dialogue(
        self,
        character_id: str,
        text: str,
        emotion: Optional[str] = None,
        scene_idx: Optional[int] = None,
        shot_idx: Optional[int] = None,
        context: Optional[str] = None,
    ):
        """Add dialogue to character's history for continuity."""
        if character_id not in self.dialogue_history:
            self.dialogue_history[character_id] = []
        
        dialogue = CharacterDialogue(
            character_id=character_id,
            text=text,
            emotion=emotion,
            scene_idx=scene_idx,
            shot_idx=shot_idx,
            context=context,
        )
        self.dialogue_history[character_id].append(dialogue)
        
        # Keep only last 100 dialogues per character (prevent unbounded growth)
        if len(self.dialogue_history[character_id]) > 100:
            self.dialogue_history[character_id] = self.dialogue_history[character_id][-100:]
        
        self.save()
        logger.debug(f"Added dialogue for character '{character_id}': {text[:50]}...")
    
    def get_recent_dialogues(
        self,
        character_id: str,
        limit: int = 10,
    ) -> List[CharacterDialogue]:
        """Get recent dialogues for a character."""
        if character_id not in self.dialogue_history:
            return []
        return self.dialogue_history[character_id][-limit:]
    
    def get_character_style_context(self, character_id: str) -> str:
        """Get style context from character's dialogue history."""
        recent = self.get_recent_dialogues(character_id, limit=5)
        if not recent:
            return ""
        
        # Build context from recent dialogues
        context_parts = []
        for dialogue in recent:
            if dialogue.emotion:
                context_parts.append(f"Emotion: {dialogue.emotion}")
            if dialogue.context:
                context_parts.append(f"Context: {dialogue.context}")
        
        return ". ".join(context_parts) if context_parts else ""
    
    def set_voiceover_memory(
        self,
        narrator_voice_id: str,
        narrator_voice_name: str,
        style: str,
    ):
        """Set voice-over narrator configuration."""
        self.voiceover_memory = VoiceOverMemory(
            narrator_voice_id=narrator_voice_id,
            narrator_voice_name=narrator_voice_name,
            style=style,
        )
        self.save()
        logger.info(f"Set voice-over narrator: {narrator_voice_name} (ID: {narrator_voice_id}, Style: {style})")
    
    def get_voiceover_memory(self) -> Optional[VoiceOverMemory]:
        """Get voice-over narrator configuration."""
        return self.voiceover_memory
    
    def add_narration(self, text: str):
        """Add narration text to voice-over memory for style consistency."""
        if not self.voiceover_memory:
            return
        
        self.voiceover_memory.previous_narration.append(text)
        # Keep only last 20 narration texts
        if len(self.voiceover_memory.previous_narration) > 20:
            self.voiceover_memory.previous_narration = self.voiceover_memory.previous_narration[-20:]
        
        self.save()
    
    def get_narration_style_context(self) -> str:
        """Get style context from previous narration."""
        if not self.voiceover_memory or not self.voiceover_memory.previous_narration:
            return ""
        
        recent = self.voiceover_memory.previous_narration[-5:]
        return f"Previous narration style examples: {' | '.join(recent[:3])}"
    
    def sync_from_series(self, series_working_dir: str):
        """Sync voice memory from series-level directory for cross-episode continuity."""
        series_voice_memory = VoiceMemory(series_working_dir, series_id=self.series_id)
        
        # Merge character voices (series takes precedence)
        for char_id, voice in series_voice_memory.character_voices.items():
            if char_id not in self.character_voices:
                self.character_voices[char_id] = voice
                logger.info(f"Synced voice for character '{char_id}' from series")
        
        # Merge dialogue history (append, don't replace)
        for char_id, dialogues in series_voice_memory.dialogue_history.items():
            if char_id not in self.dialogue_history:
                self.dialogue_history[char_id] = []
            # Add dialogues that aren't already present
            existing_texts = {d.text for d in self.dialogue_history[char_id]}
            for dialogue in dialogues:
                if dialogue.text not in existing_texts:
                    self.dialogue_history[char_id].append(dialogue)
        
        # Sync voice-over memory
        if series_voice_memory.voiceover_memory and not self.voiceover_memory:
            self.voiceover_memory = series_voice_memory.voiceover_memory
        
        self.save()
        logger.info("Synced voice memory from series directory")
    
    def sync_to_series(self, series_working_dir: str):
        """Sync voice memory to series-level directory."""
        series_voice_memory = VoiceMemory(series_working_dir, series_id=self.series_id)
        
        # Update series with current character voices
        for char_id, voice in self.character_voices.items():
            series_voice_memory.character_voices[char_id] = voice
        
        # Merge dialogue history to series
        for char_id, dialogues in self.dialogue_history.items():
            if char_id not in series_voice_memory.dialogue_history:
                series_voice_memory.dialogue_history[char_id] = []
            existing_texts = {d.text for d in series_voice_memory.dialogue_history[char_id]}
            for dialogue in dialogues:
                if dialogue.text not in existing_texts:
                    series_voice_memory.dialogue_history[char_id].append(dialogue)
        
        # Update voice-over memory
        if self.voiceover_memory:
            series_voice_memory.voiceover_memory = self.voiceover_memory
        
        series_voice_memory.save()
        logger.info("Synced voice memory to series directory")
