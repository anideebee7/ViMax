# Music and Song Integration - Complete

## Overview
Complete integration of music and song generation into the creative pipeline. The system now identifies when music/songs are needed in scripts, generates them automatically, and seamlessly inserts them into videos at appropriate points.

## Key Features

### 1. Script-Level Music Support
- **Enhanced Screenwriter**: Prompts now encourage identifying music needs
- **Music Cues**: Recognizes `[MUSIC]`, `[SONG]`, `[MUSICAL NUMBER]`, `[MONTAGE]` cues
- **Lyrics Support**: Extracts lyrics when characters are singing
- **Style Detection**: Determines music style from scene context

### 2. Audio Planning for Music
- **MUSIC_SEGMENT Type**: Standalone music for montages, transitions, emotional moments
- **SONG Type**: Full songs with lyrics for musical numbers
- **Automatic Detection**: AudioPlanner identifies music needs from script cues
- **Duration Estimation**: Estimates music duration from script descriptions

### 3. Music Generation
- **ElevenLabs Primary**: High-quality music composition with lyrics support
- **Udio via PiAPI Fallback**: Reliable fallback for music generation
- **Style Variety**: Supports various music styles (pop, ballad, rock, orchestral, etc.)
- **Lyrics Integration**: Generates songs with vocals when lyrics provided

### 4. Video Integration
- **Timeline Insertion**: Music segments inserted at appropriate points
- **Visual Placeholders**: Black screen or visual placeholders (can be enhanced)
- **Seamless Concatenation**: Music integrated with video clips
- **Cross-Pipeline Support**: Works across all video pipelines

## Supported Pipelines

✅ **Script2VideoPipeline**: Music segments after shots
✅ **VideoPipeline**: Music segments between scenes
✅ **MoviePipeline**: Music segments between scenes
✅ **ShortMovieVideoPipeline**: Music segments in short films
✅ **KidsMoviePipeline**: Music segments in kids movies
✅ **DocumentaryPipeline**: Music segments between segments

## Usage Flow

### 1. Script Writing (Screenwriter)
The screenwriter can now include music cues in scripts:

```
SCENE 3: The characters break into song
[MUSICAL NUMBER]
Alice: (singing) "This is a wonderful day, full of joy and light..."
Bob: (singing) "Yes, it's amazing, everything feels right!"
[MUSIC: upbeat pop, 60 seconds]

SCENE 5: Emotional montage
[MONTAGE]
[Music: emotional ballad, 45 seconds]
- Character training montage
- Character growth moments
- Emotional climax
```

### 2. Audio Planning (AudioPlanner)
AudioPlanner automatically detects:
- `[MUSIC]` cues → Creates `MUSIC_SEGMENT` requirement
- `[SONG]` or `[MUSICAL NUMBER]` → Creates `SONG` requirement with lyrics
- `[MONTAGE]` → Creates `MUSIC_SEGMENT` for montage music
- Extracts lyrics from script
- Determines music style from context
- Estimates duration

### 3. Music Generation
Music generator creates:
- Instrumental music for `MUSIC_SEGMENT`
- Songs with vocals for `SONG` type
- Style-matched music based on context
- Duration-matched music for seamless integration

### 4. Video Integration
Music segments are:
- Generated as audio files
- Converted to video clips with visual placeholders
- Inserted into video timeline at appropriate points
- Seamlessly concatenated with video clips

## Example Script with Music

```
SCENE 1: Opening
Alice walks into the room, looking determined.

SCENE 2: Training Montage
[MONTAGE]
[Music: energetic rock, 90 seconds]
- Alice practices martial arts
- Alice studies late at night
- Alice runs through the city
- Alice gets stronger with each day

SCENE 3: The Big Performance
[MUSICAL NUMBER]
[Song: inspirational pop, 120 seconds]
Alice: (singing) "I've come so far, I won't give up now..."
Chorus: (singing) "We believe in you, you can do it!"
Alice: (singing) "This is my moment, this is my time!"

SCENE 4: Victory
Alice wins the competition. The crowd cheers.
```

## Technical Implementation

### AudioPlan Enhancements
- Added `MUSIC_SEGMENT` and `SONG` to `AudioType` enum
- Added `lyrics`, `music_style`, `music_duration`, `is_musical_number` to `AudioRequirement`

### Music Generator (`utils/pipeline/music_generator.py`)
- `generate_music_segment()`: Generates standalone music/song
- `generate_music_segments_from_plan()`: Generates all music from AudioPlan

### Pipeline Integration
- All pipelines check for music segments in AudioPlan
- Music segments converted to video clips with visual placeholders
- Inserted into video timeline during concatenation

## Future Enhancements

1. **Visual Enhancements**:
   - Lyrics overlay on music segments
   - Music visualizers
   - Character animations during musical numbers
   - Montage-style visuals for music segments

2. **Advanced Music Features**:
   - Multi-character duets
   - Chorus sections
   - Instrumental breaks
   - Music transitions between scenes

3. **Style Customization**:
   - Genre-specific music generation
   - Tempo control
   - Key/mode selection
   - Instrument selection

4. **Integration Improvements**:
   - Smooth transitions between video and music
   - Fade in/out effects
   - Synchronized visuals with music beats
   - Lip-sync for singing characters

## Benefits

1. **Creative Flexibility**: Scripts can naturally include music/songs
2. **Automatic Generation**: Music generated automatically from script cues
3. **Seamless Integration**: Music inserted at appropriate points
4. **Style Matching**: Music style matches scene context
5. **Cross-Pipeline Support**: Works across all video pipelines
6. **Lyrics Support**: Full song generation with lyrics
