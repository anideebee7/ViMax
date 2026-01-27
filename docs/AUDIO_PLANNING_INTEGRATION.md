# Audio Planning Integration

## Overview
Comprehensive audio planning system that identifies voice-over, dialogue, dubbing, narration, background music, and sound effects at scene and shot levels across all pipelines.

## Components Created

### 1. Interfaces (`interfaces/content/audio_plan.py`)
- **AudioType**: Enum for audio content types (dialogue, voice_over, dubbing, narration, background_music, sound_effects, ambient, silent)
- **AudioRequirement**: Detailed requirement for a shot/scene including:
  - Text to be spoken
  - Character ID
  - Emotion/tone
  - Voice style
  - Lip-sync requirements
  - Timing
  - Background music style
  - Sound effects
  - Priority level
- **ShotAudioPlan**: Audio plan for a single shot
- **SceneAudioPlan**: Audio plan for a scene with shot-level plans
- **AudioPlan**: Complete audio plan for a script/movie

### 2. Audio Planner Agent (`agents/producers/audio/planner.py`)
- **AudioPlanner**: LLM-powered agent that analyzes scripts and determines audio requirements
- Methods:
  - `plan_audio_for_scenes()`: Plans audio for multiple scenes with shot-level detail
  - `plan_audio_for_shots()`: Plans audio for shots within a scene
  - `save_audio_plan()` / `load_audio_plan()`: Persistence
  - `_create_fallback_plan()`: Fallback if LLM fails

## Integration Status

### ✅ Completed
1. Created audio planning interfaces
2. Created AudioPlanner agent
3. Integrated AudioPlanner into Script2VideoPipeline (basic integration)
4. Audio plan is saved/loaded for continuity

### 🔄 In Progress
1. Update audio generation to use AudioPlan for voice-over/dialogue
2. Integrate AudioPlanner into all other pipelines:
   - VideoPipeline (base/idea.py)
   - MoviePipeline
   - DocumentaryPipeline
   - Podcast2VideoPipeline
   - KidsMoviePipeline
   - ShortMovieVideoPipeline
   - LearningSeriesPipeline
   - TVSeriesPipeline

### 📋 TODO
1. **Voice Generation Integration**: 
   - Use AudioPlan to identify dialogue/voice-over requirements
   - Generate voice using TTS (ElevenLabs or PiAPI)
   - Sync with video timing
   - Handle lip-sync when required

2. **Audio Mixing**:
   - Mix dialogue/voice-over with background music
   - Add sound effects at correct timing
   - Balance audio levels

3. **Memory Integration**:
   - Store audio plans in agent memory for cross-episode continuity
   - Maintain character voice consistency across scenes/episodes

4. **Pipeline-Specific Adaptations**:
   - Documentary: Focus on narration
   - Podcast: Dialogue-heavy
   - Kids: Age-appropriate voices
   - Movies: Complex dialogue with multiple characters

## Usage Example

```python
# In a pipeline
audio_planner = AudioPlanner(chat_model=chat_model, pipeline_kind="feature_film")

# Plan audio after shots are created
audio_plan = await audio_planner.plan_audio_for_scenes(
    scenes=scenes,
    shots_per_scene=shots_per_scene,
    previous_audio_plan=previous_plan,  # For continuity
    style=style,
    audience=audience,
    content_format=content_format,
)

# Use audio plan for generation
for scene_plan in audio_plan.scene_plans:
    for shot_plan in scene_plan.shot_plans:
        for req in shot_plan.requirements:
            if req.audio_type == AudioType.DIALOGUE:
                # Generate voice for dialogue
                generate_voice(req.text, req.character_id, req.emotion)
            elif req.audio_type == AudioType.BACKGROUND_MUSIC:
                # Generate background music
                generate_music(req.background_music_style)
```

## Next Steps

1. Complete integration into all pipelines
2. Implement voice generation using AudioPlan
3. Add audio mixing logic
4. Test with various content types
5. Document pipeline-specific audio planning strategies
