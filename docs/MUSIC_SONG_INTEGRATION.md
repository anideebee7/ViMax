# Music and Song Integration

## Overview
Enhanced system to support music segments and songs in scripts, with automatic generation and insertion into videos. The system identifies when music/songs are needed in the creative process and seamlessly integrates them into the video timeline.

## Features

### 1. Script-Level Music Support
- **Audio Planning**: AudioPlanner identifies music segments and songs from scripts
- **Script Cues**: Recognizes cues like `[MUSIC]`, `[SONG]`, `[MUSICAL NUMBER]`, `[MONTAGE]`, `[CHARACTER SINGS]`
- **Lyrics Extraction**: Extracts lyrics when characters are singing
- **Style Detection**: Determines music style based on scene context

### 2. Music Generation
- **Standalone Music Segments**: Instrumental or vocal music for montages, transitions, emotional moments
- **Full Songs**: Complete songs with lyrics for musical numbers
- **Style Support**: Various music styles (upbeat pop, emotional ballad, cinematic orchestral, etc.)
- **Duration Control**: Generates music to match required duration

### 3. Video Integration
- **Timeline Insertion**: Music segments inserted at appropriate points in video timeline
- **Visual Placeholders**: Black screen or visual placeholders for music segments (can be enhanced with lyrics overlay)
- **Seamless Concatenation**: Music segments integrated with video clips during concatenation

## Components

### AudioPlan Enhancements

New `AudioType` values:
- `MUSIC_SEGMENT`: Standalone music segment (montages, transitions)
- `SONG`: Full song with lyrics (musical numbers)

New `AudioRequirement` fields:
- `lyrics`: Lyrics for songs
- `music_style`: Style/genre of music
- `music_duration`: Duration of music segment
- `is_musical_number`: Whether it's a full musical performance

### Music Generator (`utils/pipeline/music_generator.py`)

```python
from utils.pipeline.music_generator import generate_music_segment, generate_music_segments_from_plan

# Generate a standalone music segment
music_path = await generate_music_segment(
    music_style="upbeat pop",
    duration_seconds=30.0,
    lyrics="Optional lyrics for song",
    is_song=False,
    output_path="music.mp3",
)

# Generate all music segments from AudioPlan
music_segments = await generate_music_segments_from_plan(
    audio_plan=audio_plan,
    working_dir=working_dir,
)
```

### Pipeline Integration

**Script2VideoPipeline:**
- Generates music segments from AudioPlan
- Inserts music segments after corresponding shots
- Creates visual placeholders for music segments

**MoviePipeline:**
- Generates music segments for movie scenes
- Inserts music segments between scenes
- Maintains timeline continuity

**DocumentaryPipeline:**
- Generates music segments for documentary segments
- Inserts music segments between segments
- Supports narration with music

## Usage Flow

1. **Script Writing**: Screenwriter writes script with music cues
   ```
   SCENE 3: The characters break into song
   [MUSICAL NUMBER]
   Alice: (singing) "This is a wonderful day..."
   Bob: (singing) "Yes, it's amazing!"
   [MUSIC: upbeat pop, 60 seconds]
   ```

2. **Audio Planning**: AudioPlanner identifies music needs
   - Detects `[MUSIC]`, `[SONG]`, `[MUSICAL NUMBER]` cues
   - Extracts lyrics from script
   - Determines music style from context
   - Creates `AudioRequirement` with `MUSIC_SEGMENT` or `SONG` type

3. **Music Generation**: Music generator creates audio
   - Uses ElevenLabs or Udio via PiAPI
   - Generates music matching style and duration
   - Includes vocals if lyrics provided

4. **Video Integration**: Music segments inserted into timeline
   - After corresponding shots/scenes
   - With visual placeholders
   - Seamlessly concatenated with video

## Supported Pipelines

- ✅ **Script2VideoPipeline**: Music segments after shots
- ✅ **VideoPipeline**: Inherits from Script2VideoPipeline
- ✅ **MoviePipeline**: Music segments between scenes
- ✅ **ShortMovieVideoPipeline**: Music segments in short films
- ✅ **KidsMoviePipeline**: Music segments in kids movies
- ✅ **DocumentaryPipeline**: Music segments between segments

## Music Generation Providers

1. **ElevenLabs** (Primary):
   - Supports music composition with lyrics
   - Configurable duration
   - High quality output

2. **Udio via PiAPI** (Fallback):
   - Music generation with lyrics support
   - Various music styles
   - Reliable fallback option

## Future Enhancements

1. **Visual Enhancements**:
   - Lyrics overlay on music segments
   - Visual music visualizers
   - Character animations during musical numbers

2. **Advanced Music Features**:
   - Multi-character duets
   - Chorus sections
   - Instrumental breaks

3. **Style Customization**:
   - Genre-specific music generation
   - Tempo control
   - Key/mode selection

4. **Integration Improvements**:
   - Smooth transitions between video and music
   - Fade in/out effects
   - Synchronized visuals with music beats
