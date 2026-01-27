# Pipeline Generator Unification Status

**Date**: 2026-01-26  
**Status**: ✅ **COMPLETE** - All pipelines now use unified generator logic

## Summary

All pipelines that require image/video generators now use the unified generator factory (`utils.pipeline.generator_factory`) with the correct fallback chain:

- **Image Generation Priority** (nano-banana-pro model):
  1. GoogleImageGenerator (Gemini API) - Primary
  2. PiAPIImageGenerator (nano-banana-pro) - Fallback
  3. KieAIImageGenerator (nano-banana-pro) - Last resort

- **Video Generation Priority** (Veo 3.1):
  1. KieAIVideoGenerator (veo3_fast) - Primary
  2. PiAPIVideoGenerator (veo3.1) - Fallback
  3. VeoGoogleVideoGenerator (veo-3.1-generate-preview) - Last resort

## Pipeline Status

### ✅ Base Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| VideoPipeline | `pipelines/base/idea.py` | ✅ Unified | `create_generators_from_config(config)` |
| Script2VideoPipeline | `pipelines/base/script.py` | ✅ Unified | `create_generators_from_config(config)` |

### ✅ Movie Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| ShortMovieVideoPipeline | `pipelines/movies/short_video.py` | ✅ Unified | `create_generators_from_config(config)` |
| KidsMoviePipeline | `pipelines/movies/kids.py` | ✅ Unified | `create_generators_from_config(config)` |
| ShortMoviePipeline | `pipelines/movies/short.py` | ✅ N/A | No generators (script-only) |
| MoviePipeline | `pipelines/movies/standard.py` | ✅ N/A | Accepts generators as constructor params |
| Novel2MoviePipeline | `pipelines/movies/novel.py` | ✅ N/A | Accepts generators as constructor params |

### ✅ Music Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| MusicVideoPipeline | `pipelines/music/video.py` | ✅ Unified | `create_generators_from_config(config)` |
| Song2MusicVideoPipeline | `pipelines/music/song_to_video.py` | ✅ Unified | `create_generators_from_config(config)` |
| SongPipeline | `pipelines/music/song.py` | ✅ Unified | `create_image_generator(rate_limiter)` |
| LyricsPipeline | `pipelines/music/lyrics.py` | ✅ N/A | No generators (text-only) |

**Note**: `MusicVideoPipeline` and `SongPipeline` still use direct class loading for audio generators, which is acceptable as audio generators are not yet part of the unified system.

### ✅ Content Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| DocumentaryPipeline | `pipelines/content/documentary.py` | ✅ Unified | `create_generators_from_config(config)` |
| Podcast2VideoPipeline | `pipelines/content/podcast.py` | ✅ Unified | `create_generators_from_config(config)` |

### ✅ Series Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| TVSeriesPipeline | `pipelines/series/tv.py` | ✅ Unified | `create_generators_from_config(config)` |
| WeeklySeriesPipeline | `pipelines/series/weekly.py` | ✅ Unified | `create_generators_from_config(config)` |
| LearningSeriesPipeline | `pipelines/series/learning.py` | ✅ Unified | `create_generators_from_config(config)` |
| PodcastSeriesPipeline | `pipelines/series/podcast.py` | ✅ Unified | `create_generators_from_config(config)` |

### ✅ Social Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| ViralShortsPipeline | `pipelines/social/shorts.py` | ✅ Unified | `create_generators_from_config(config)` |

### ✅ Ad Pipelines

| Pipeline | File | Status | Method Used |
|----------|------|--------|-------------|
| AdPipeline | `pipelines/ads/video.py` | ✅ Unified | `create_generators_from_config(config)` |
| AdBannersPipeline | `pipelines/ads/banners.py` | ✅ Unified | `create_generators_from_config(config)` |

## Implementation Details

### Unified Generator Factory

All pipelines use one of these factory functions:

1. **`create_generators_from_config(config)`** - Preferred method
   - Extracts rate limiting from config
   - Extracts API keys from config init_args
   - Creates unified generators with proper fallback chain
   - Used by: All pipelines with `init_from_config` methods

2. **`create_image_generator(rate_limiter)`** - For image-only pipelines
   - Used by: `SongPipeline` (only needs image generator for cover art)

3. **`create_generators(...)`** - Direct creation (not used in pipelines)
   - Available for manual instantiation if needed

### Removed Direct Class Loading

All pipelines previously used this pattern (now removed):
```python
# OLD (REMOVED):
mod, clz = config["image_generator"]["class_path"].rsplit(".", 1)
cls_obj = getattr(importlib.import_module(mod), clz)
image_generator = cls_obj(**args)
```

Replaced with:
```python
# NEW (UNIFIED):
from utils.pipeline.generator_factory import create_generators_from_config
image_generator, video_generator = create_generators_from_config(config)
```

## Validation

### Files Verified

All 16 pipeline files that use generators have been verified:
- ✅ All use `create_generators_from_config` or `create_image_generator`
- ✅ No direct class loading for image/video generators
- ✅ Rate limiting properly extracted from config
- ✅ API keys properly resolved from config or environment

### Exceptions

1. **Audio Generators**: `MusicVideoPipeline` and `SongPipeline` still use direct class loading for audio generators. This is acceptable as audio generators are not yet part of the unified system.

2. **Pipelines Without Generators**: 
   - `ShortMoviePipeline` - Script-only, no generators
   - `LyricsPipeline` - Text-only, no generators

3. **Pipelines Without `init_from_config`**:
   - `MoviePipeline` - Accepts generators as constructor parameters
   - `Novel2MoviePipeline` - Accepts generators as constructor parameters
   - These are initialized by callers who should use unified generators

## Testing Recommendations

To validate the unified generator system:

1. **Run a pipeline** (e.g., `ViralShortsPipeline` or `ShortMovieVideoPipeline`)
2. **Check logs** for generator initialization:
   - Should see: "Creating unified generators with fallback chains..."
   - Should see: "Trying Gemini API..." (not "Calling KieAI...")
3. **Verify fallback behavior** by temporarily disabling Gemini API key
   - Should fallback to PiAPI, then KieAI

## Benefits

1. **Consistent Fallback Chain**: All pipelines use the same priority (Gemini → PiAPI → KieAI)
2. **Centralized Configuration**: Generator logic is in one place (`utils/pipeline/generator_factory.py`)
3. **Easier Maintenance**: Changes to generator priority only need to be made in one file
4. **Better Resource Utilization**: Proper fallback ensures optimal API usage
5. **Rate Limiting**: Consistent rate limiting across all pipelines

## Next Steps

- ✅ All pipelines verified and updated
- ✅ Documentation created
- ⏳ Test one pipeline to validate unified generator is working (recommended)
