# Audio Planning Integration - Complete

## Overview
Comprehensive audio planning and voice generation system integrated across all pipelines. The system identifies voice-over, dialogue, dubbing, narration, background music, and sound effects at scene and shot levels.

## Components

### 1. Audio Planning Interfaces (`interfaces/content/audio_plan.py`)
- **AudioType**: Enum for audio content types
- **AudioRequirement**: Detailed requirement with text, character, emotion, timing, etc.
- **ShotAudioPlan**: Audio plan for a single shot
- **SceneAudioPlan**: Audio plan for a scene
- **AudioPlan**: Complete audio plan for a script/movie

### 2. Audio Planner Agent (`agents/producers/audio/planner.py`)
- Analyzes scripts and determines audio requirements
- Plans at scene and shot levels
- Maintains continuity across episodes
- Saves/loads plans for resume functionality
- Integrates with agent memory

### 3. Voice Generator (`utils/pipeline/voice_generator.py`)
- **generate_voice_from_text()**: Converts text to speech using ElevenLabs TTS
- **generate_audio_track_from_plan()**: Creates complete audio track from AudioPlan
- Mixes dialogue, voice-over, narration, and background music
- Handles timing and synchronization

### 4. Enhanced Audio Generator (`tools/audio_generator_elevenlabs.py`)
- Added `text_to_speech()` method for TTS generation
- Supports voice ID mapping for character consistency
- Configurable voice settings (emotion, stability, etc.)

## Integration Status

### ✅ All Pipelines Integrated

1. **Script2VideoPipeline** - Plans audio at shot level after decomposition
2. **VideoPipeline** - Inherits from Script2VideoPipeline (scene-level)
3. **MoviePipeline** - Plans audio after script generation
4. **DocumentaryPipeline** - Plans audio for segments (opening, main, closing)
5. **Podcast2VideoPipeline** - Plans audio for podcast scenes
6. **KidsMoviePipeline** - Plans audio for kids movie scenes
7. **ShortMovieVideoPipeline** - Plans audio for short film scenes
8. **LearningSeriesPipeline** - Plans audio per episode segment
9. **TVSeriesPipeline** - Aggregates audio plans from Script2VideoPipeline episodes

## Audio Generation Flow

1. **Planning Phase** (After script/scene generation):
   - AudioPlanner analyzes scripts
   - Identifies dialogue, voice-over, narration needs
   - Determines background music style
   - Plans sound effects
   - Saves plan for continuity

2. **Generation Phase** (During video concatenation):
   - If AudioPlan exists: Generate voice tracks + background music
   - If no AudioPlan: Generate background music only (fallback)
   - Mix all audio tracks with proper timing
   - Add to final video

## Voice Generation Features

- **Character Voice Mapping**: Maintains consistent voices for characters
- **Emotion Support**: Adjusts voice settings based on emotion
- **Timing Synchronization**: Positions dialogue/voice-over at correct times
- **Background Music Mixing**: Combines voice tracks with background music
- **Volume Balancing**: Dialogue at full volume, background music at 30%

## Memory Integration

- Audio plans saved to JSON files for resume
- Plans can be loaded from previous episodes for continuity
- Character voice mappings maintained across series
- Integration with RunMemory for S3 persistence

## Usage Example

```python
# Audio planning happens automatically in pipelines
# After script generation:
audio_plan = await audio_planner.plan_audio_for_scenes(
    scenes=scenes,
    shots_per_scene=shots_per_scene,
    previous_audio_plan=previous_plan,  # For continuity
    style=style,
    audience=audience,
    content_format=content_format,
)

# Audio generation uses the plan:
from utils.pipeline.voice_generator import generate_audio_track_from_plan
audio_path = await generate_audio_track_from_plan(
    audio_plan=audio_plan,
    video_duration=video_duration,
    output_path="final_audio.mp3",
    working_dir=working_dir,
)
```

## Pipeline-Specific Adaptations

- **Documentary**: Focus on narration with presenter voice
- **Podcast**: Dialogue-heavy with character voices
- **Kids Movies**: Age-appropriate voices and music
- **Movies**: Complex dialogue with multiple characters
- **Series**: Cross-episode voice consistency

## Next Steps

1. **Voice ID Mapping**: Create character-to-voice_id mapping system
2. **Lip-Sync Integration**: Sync generated voice with character lip movements
3. **Sound Effects Library**: Integrate sound effects generation
4. **Multi-language Support**: Extend TTS for multiple languages
5. **Voice Cloning**: Support custom voice cloning for characters
