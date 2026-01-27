# Resume/Retry Run ID Fix

## Overview

Fixed the issue where pipelines were creating new `run_id` folders on each retry or resume of an errored/incomplete pipeline run. Now all pipelines properly detect and reuse existing `run_id` directories when resuming.

## Changes Made

### 1. Created Unified Helper Function

**File**: `utils/core/run_id.py`

Added `initialize_run_directory()` function that:
- Detects existing `run_id` from `working_dir` path or `run.json`
- Reuses existing `run_id` directory when resuming
- Only creates new `run_id` when starting a fresh run
- Handles all edge cases (missing directories, existing metadata, etc.)

```python
def initialize_run_directory(
    working_dir: str,
    pipeline_name: str,
    run_id: Optional[str] = None,
    use_run_id: bool = True,
) -> tuple[str, Optional[str]]:
    """Initialize run directory with proper resume detection."""
    # ... implementation
```

### 2. Updated All Pipeline `__init__` Methods

All pipelines now use `initialize_run_directory()` instead of manual `run_id` generation:

**Updated Pipelines:**
- ✅ `VideoPipeline` (`pipelines/base/idea.py`)
- ✅ `Script2VideoPipeline` (`pipelines/base/script.py`)
- ✅ `ViralShortsPipeline` (`pipelines/social/shorts.py`)
- ✅ `MoviePipeline` (`pipelines/movies/standard.py`)
- ✅ `MusicVideoPipeline` (`pipelines/music/video.py`)
- ✅ `LearningSeriesPipeline` (`pipelines/series/learning.py`)
- ✅ `TVSeriesPipeline` (`pipelines/series/tv.py`)
- ✅ `PodcastSeriesPipeline` (`pipelines/series/podcast.py`)
- ✅ `WeeklySeriesPipeline` (`pipelines/series/weekly.py`)
- ✅ `KidsMoviePipeline` (`pipelines/movies/kids.py`)
- ✅ `ShortMoviePipeline` (`pipelines/movies/short.py`)
- ✅ `ShortMovieVideoPipeline` (`pipelines/movies/short_video.py`)
- ✅ `Novel2MoviePipeline` (`pipelines/movies/novel.py`)
- ✅ `SongPipeline` (`pipelines/music/song.py`)
- ✅ `Song2MusicVideoPipeline` (`pipelines/music/song_to_video.py`)
- ✅ `LyricsPipeline` (`pipelines/music/lyrics.py`)
- ✅ `AdPipeline` (`pipelines/ads/video.py`)
- ✅ `AdBannersPipeline` (`pipelines/ads/banners.py`)
- ✅ `DocumentaryPipeline` (`pipelines/content/documentary.py`)
- ✅ `Podcast2VideoPipeline` (`pipelines/content/podcast.py`)

### 3. Updated `init_from_config` Methods

Key pipelines now accept `run_id` and `working_dir` parameters for resume scenarios:

- ✅ `MoviePipeline.init_from_config()`
- ✅ `MusicVideoPipeline.init_from_config()`
- ✅ `LearningSeriesPipeline.init_from_config()`
- ✅ `VideoPipeline.init_from_config()` (already had it)
- ✅ `Script2VideoPipeline.init_from_config()` (already had it)
- ✅ `ViralShortsPipeline.init_from_config()` (already had it)

### 4. Fixed Syntax Error

Fixed a syntax error in `DocumentaryPipeline` where `StoryboardArtist` was incorrectly instantiated.

## How It Works

### Resume Detection Logic

1. **If `run_id` is provided**: Check if `working_dir` matches the `run_id` directory name
   - If match and directory exists → Resume scenario, reuse existing directory
   - Otherwise → Create new subdirectory with that `run_id`

2. **If `run_id` is NOT provided**: Try to extract from `working_dir`
   - Check `run.json` file in the directory
   - Check if directory name matches `run_id` pattern (`prefix_timestamp_token`)
   - If found → Resume scenario, reuse existing directory
   - If not found → Generate new `run_id`

3. **Metadata Protection**: Only write `run.json` if it doesn't exist (prevents overwriting resume metadata)

### Example Usage

**Resuming a failed run:**
```python
# Option 1: Provide run_id explicitly
pipeline = MoviePipeline.init_from_config(
    'configs/pipelines/movie.yaml',
    run_id='movie_20260126_120000_abcdef12',
    working_dir='.working_dir/movie/movie_20260126_120000_abcdef12'
)

# Option 2: Just provide working_dir (run_id extracted automatically)
pipeline = MoviePipeline.init_from_config(
    'configs/pipelines/movie.yaml',
    working_dir='.working_dir/movie/movie_20260126_120000_abcdef12'
)
```

**Starting a new run:**
```python
# Just use init_from_config normally - new run_id will be generated
pipeline = MoviePipeline.init_from_config('configs/pipelines/movie.yaml')
```

## Benefits

1. **No More Duplicate Folders**: Resuming a run no longer creates new `run_id` directories
2. **Automatic Detection**: Pipelines automatically detect existing runs from `working_dir`
3. **Consistent Behavior**: All pipelines use the same resume detection logic
4. **Backward Compatible**: Existing code continues to work, new resume features are opt-in
5. **Metadata Preservation**: Existing `run.json` files are never overwritten

## Testing

Created and ran comprehensive tests verifying:
- ✅ New run creation
- ✅ Resume with existing `run_id`
- ✅ Resume by extracting `run_id` from path
- ✅ Multiple runs in different base directories
- ✅ `run_id` extraction from `run.json`
- ✅ `run_id` extraction from directory name pattern

All tests passed successfully.

## Next Steps

For pipelines that don't yet have `init_from_config` updated with `run_id`/`working_dir` parameters, they can be updated as needed. The core `__init__` methods all support resume functionality now.
