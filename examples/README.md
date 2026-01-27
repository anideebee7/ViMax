# ViMax Pipeline Examples

This folder contains example scripts showing how to use each ViMax pipeline programmatically.

## Recommended: Use the CLI

For most use cases, the unified CLI (`vimax.py`) is the easiest way to run pipelines:

```bash
# List all available pipelines
python vimax.py list

# Run a pipeline
python vimax.py video --idea "Your story idea" --style "animated"
python vimax.py movie --premise "Your movie premise" --genre "sci-fi" --duration 120
python vimax.py short_movie-video --premise "Your short film premise" --brand autocurio
```

## Programmatic Usage

If you need more control, use the examples in this folder as templates.

### Video Generation

| Example | Pipeline | Description |
|---------|----------|-------------|
| `main_video.py` | VideoPipeline | Generate video from idea/script |
| `main_script2video.py` | Script2VideoPipeline | Generate video from existing script |
| `main_short_movie.py` | ShortMoviePipeline | Generate short film script (5-20 min) |
| `kids_movie_video_example.py` | ShortMovieVideoPipeline | Generate complete kids video |

### Movie Generation

| Example | Pipeline | Description |
|---------|----------|-------------|
| `main_movie.py` | MoviePipeline | Generate full movie script |
| `main_kids_movie.py` | KidsMoviePipeline | Generate kids movie script |
| `main_documentary.py` | DocumentaryPipeline | Generate documentary |

### Music & Audio

| Example | Pipeline | Description |
|---------|----------|-------------|
| `main_lyrics.py` | LyricsPipeline | Generate song lyrics |
| `main_song.py` | SongPipeline | Generate lyrics + composition |
| `main_music_video.py` | MusicVideoPipeline | Generate complete music video |
| `main_song2musicvideo.py` | Song2MusicVideoPipeline | Generate music video from song |

### Advertising

| Example | Pipeline | Description |
|---------|----------|-------------|
| `main_ad.py` | AdPipeline | Generate ad video |
| `main_adbanners.py` | AdBannersPipeline | Generate ad banners |

### Other

| Example | Pipeline | Description |
|---------|----------|-------------|
| `main_learning_series.py` | LearningSeriesPipeline | Generate educational series |
| `main_podcast2video.py` | Podcast2VideoPipeline | Convert podcast to video |
| `main_content_planner.py` | Content Planning | Weekly content planning |

## Running Examples

```bash
# From project root
cd /path/to/ViMax
python examples/main_video.py
```

Or edit the example file to customize the input:

```python
# In examples/main_video.py
idea = "Your custom story idea here"
style = "your preferred style"
```

## Configuration

Each pipeline reads from a YAML config in `configs/pipelines/`. To customize:

1. Copy the relevant config (e.g., `configs/pipelines/video.yaml`)
2. Modify settings (API keys, model, etc.)
3. Update the config path in your example script
