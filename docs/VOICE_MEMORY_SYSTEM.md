# Voice Memory System

## Overview
Comprehensive voice consistency and dialogue tracking system that maintains character voices and dialogue history across videos, episodes, and series.

## Key Features

### 1. Character Voice Mapping
- **Persistent Voice IDs**: Each character maintains a consistent ElevenLabs voice ID
- **Voice Settings**: Customizable stability, similarity_boost, and other voice parameters
- **Automatic Assignment**: Default voice assigned if character doesn't have one
- **Cross-Episode Consistency**: Voice mappings persist across episodes in a series

### 2. Dialogue Tracking
- **Dialogue History**: Stores all dialogues spoken by each character
- **Context Preservation**: Tracks scene, shot, emotion, and context for each dialogue
- **Style Consistency**: Uses recent dialogue history to maintain character voice style
- **Bounded Storage**: Keeps last 100 dialogues per character (prevents unbounded growth)

### 3. Voice-Over Memory
- **Narrator Consistency**: Maintains consistent narrator voice across content
- **Style Tracking**: Tracks narration style (authoritative, warm, documentary, etc.)
- **Previous Narration**: Stores recent narration text for style consistency

### 4. Cross-Episode/Series Continuity
- **Series-Level Sync**: Voice memory syncs between episode and series directories
- **Character Continuity**: Character voices maintained across all episodes
- **Dialogue History**: Aggregates dialogue history across episodes
- **Automatic Propagation**: New episodes inherit voice mappings from series

## Components

### VoiceMemory Class (`utils/pipeline/voice_memory.py`)

```python
from utils.pipeline.voice_memory import VoiceMemory

# Initialize voice memory
voice_memory = VoiceMemory(working_dir="./working_dir", series_id="series_001")

# Set character voice
voice_memory.set_character_voice(
    character_id="Alice",
    voice_id="21m00Tcm4TlvDq8ikWAM",  # ElevenLabs voice ID
    voice_name="Rachel",
    voice_settings={"stability": 0.5, "similarity_boost": 0.75}
)

# Add dialogue for continuity
voice_memory.add_dialogue(
    character_id="Alice",
    text="Hello, how are you?",
    emotion="happy",
    scene_idx=0,
    shot_idx=1,
    context="Opening scene"
)

# Get character voice
voice = voice_memory.get_character_voice("Alice")
# Returns: CharacterVoice with voice_id, voice_name, etc.

# Get recent dialogues for style context
recent = voice_memory.get_recent_dialogues("Alice", limit=5)
```

### Integration with AudioPlanner

The `AudioPlanner` now uses `VoiceMemory` to:
1. **Maintain Voice Consistency**: Uses character voice mappings when planning audio
2. **Track Dialogues**: Automatically stores dialogues from audio plans
3. **Provide Context**: Includes voice mapping and dialogue history in planning prompts
4. **Ensure Continuity**: Maintains character voices across scenes and episodes

### Integration with Voice Generator

The `voice_generator` uses `VoiceMemory` to:
1. **Use Correct Voice**: Retrieves character voice ID from memory
2. **Apply Voice Settings**: Uses stored voice settings (stability, similarity_boost)
3. **Maintain Narrator**: Uses consistent narrator voice for voice-over/narration
4. **Track Usage**: Dialogues are automatically added to memory after generation

## Usage in Pipelines

### Script2VideoPipeline

```python
# Voice memory is automatically initialized
self.voice_memory = VoiceMemory(working_dir=self.working_dir)
self.audio_planner = AudioPlanner(
    chat_model=self.chat_model,
    working_dir=self.working_dir,
    voice_memory=self.voice_memory,  # Pass voice memory
)

# Audio planning uses voice memory for consistency
audio_plan = await self.audio_planner.plan_audio_for_scenes(
    scenes=scenes,
    characters=characters,  # Characters are used for voice mapping
    ...
)

# Voice generation uses voice memory
audio_path = await generate_audio_track_from_plan(
    audio_plan=audio_plan,
    voice_memory=self.voice_memory,  # Pass voice memory
    ...
)
```

### TVSeriesPipeline (Cross-Episode Continuity)

```python
# Series-level voice memory
self.voice_memory = VoiceMemory(working_dir=self.working_dir, series_id=self.run_id)

# Each episode syncs from series
s2v.voice_memory.sync_from_series(self.working_dir)

# After episode, sync back to series
s2v.voice_memory.sync_to_series(self.working_dir)
```

## Data Persistence

### File Structure

```
working_dir/
├── voice_mapping.json          # Character voice mappings
├── dialogue_history.json       # Dialogue history per character
└── voiceover_memory.json       # Voice-over narrator configuration
```

### Voice Mapping Format

```json
{
  "Alice": {
    "character_id": "Alice",
    "voice_id": "21m00Tcm4TlvDq8ikWAM",
    "voice_name": "Rachel",
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
      "stability": 0.5,
      "similarity_boost": 0.75
    },
    "created_at": "2026-01-26T12:00:00"
  }
}
```

### Dialogue History Format

```json
{
  "Alice": [
    {
      "character_id": "Alice",
      "text": "Hello, how are you?",
      "emotion": "happy",
      "scene_idx": 0,
      "shot_idx": 1,
      "timestamp": "2026-01-26T12:00:00",
      "context": "Opening scene"
    }
  ]
}
```

## Benefits

1. **Character Consistency**: Same character always uses same voice across all content
2. **Style Continuity**: Character voice style maintained based on dialogue history
3. **Cross-Episode Continuity**: Series maintain consistent voices across episodes
4. **Automatic Tracking**: Dialogues automatically tracked without manual intervention
5. **Resume Support**: Voice mappings persist across pipeline runs
6. **Memory Efficiency**: Bounded storage prevents unbounded growth

## Future Enhancements

1. **Voice Cloning**: Support for custom voice cloning per character
2. **Emotion Mapping**: Automatic voice setting adjustment based on emotion
3. **Multi-language Support**: Character voices in multiple languages
4. **Voice Quality Metrics**: Track and optimize voice quality over time
5. **Character Voice Profiles**: Rich profiles with age, accent, tone, etc.
