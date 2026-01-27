# Checkpoint Implementation Status

## Overview

All pipelines are being systematically updated to support robust checkpoint/resume functionality. This ensures incomplete runs can be resumed from the exact point they left off, avoiding wasted resources on regenerating images/videos.

## Implementation Status

### ✅ Fully Implemented

1. **LearningSeriesPipeline** (`pipelines/series/learning.py`)
   - ✅ CheckpointManager initialized
   - ✅ S3 sync fallback
   - ✅ Phase-level tracking (curriculum)
   - ✅ Episode-level tracking
   - ✅ ContinuityMemory restoration
   - ✅ Shot-level tracking (segments)

2. **MoviePipeline** (`pipelines/movies/standard.py`)
   - ✅ CheckpointManager initialized
   - ✅ S3 sync fallback
   - ✅ Scene-level tracking
   - ✅ Shot-level tracking (frame + video per scene)
   - ✅ ContinuityMemory restoration
   - ✅ Image and video generation checkpointed separately

### 🔄 In Progress

3. **ShortMovieVideoPipeline** (`pipelines/movies/short_video.py`)
   - ✅ CheckpointManager initialized
   - ⏳ Shot-level tracking (needs frame/video checkpoint integration)

### 📋 To Be Implemented

4. **MusicVideoPipeline** (`pipelines/music/video.py`)
5. **Song2MusicVideoPipeline** (`pipelines/music/song_to_video.py`)
6. **Script2VideoPipeline** (`pipelines/base/script.py`)
7. **VideoPipeline** (`pipelines/base/idea.py`)
8. **Podcast2VideoPipeline** (`pipelines/content/podcast.py`)
9. **DocumentaryPipeline** (`pipelines/content/documentary.py`)
10. **AdPipeline** (`pipelines/ads/video.py`)
11. **TVSeriesPipeline** (`pipelines/series/tv.py`)
12. **PodcastSeriesPipeline** (`pipelines/series/podcast.py`)
13. **WeeklySeriesPipeline** (`pipelines/series/weekly.py`)
14. **ViralShortsPipeline** (`pipelines/social/shorts.py`)
15. **KidsMoviePipeline** (`pipelines/movies/kids.py`)
16. **ShortMoviePipeline** (`pipelines/movies/short.py`)
17. **SongPipeline** (`pipelines/music/song.py`)
18. **LyricsPipeline** (`pipelines/music/lyrics.py`)
19. **AdBannersPipeline** (`pipelines/ads/banners.py`)
20. **Novel2MoviePipeline** (`pipelines/movies/novel.py`)

## Implementation Pattern

For each pipeline, follow this pattern:

### 1. Import CheckpointManager

```python
from utils.pipeline.checkpoint import CheckpointManager
```

### 2. Initialize in __init__

```python
self.checkpoint = CheckpointManager(
    working_dir=self.working_dir,
    run_id=self.run_id,
    pipeline_type="pipeline_name"
)
```

### 3. Add S3 Sync and Resume Check at Start of __call__

```python
# RESUME CHECK: Try to sync from S3 if local folder is missing/incomplete
if not os.path.exists(self.working_dir):
    self.logger.info(f"Attempting to sync run state from S3 for run_id: {self.run_id}")
    if self.memory.sync_from_s3():
        self.logger.info("✅ Synced run state from S3")
        self.continuity_memory.load()
        self.continuity_memory.load_series_state()  # For series pipelines
    else:
        self.logger.info("No existing run found in S3, starting fresh")

# RESUME CHECK: Load checkpoint and check if run can be resumed
checkpoint = self.checkpoint.load()
can_resume = self.checkpoint.can_resume()

if can_resume and not self.force_regenerate:
    resume_info = self.checkpoint.get_resume_info()
    self.logger.info(f"🔄 Resuming incomplete run (status: {resume_info['status']})")
    # Log completed items
elif not checkpoint:
    self.checkpoint.initialize(metadata={...})
```

### 4. Checkpoint Before Image Generation

```python
# For shot-level tracking
scene_num = i + 1
shot_num = 0  # Frame generation

# RESUME CHECK: Skip if already completed
if self.checkpoint.is_shot_completed(scene_num, shot_num) and not self.force_regenerate:
    if os.path.exists(frame_path):
        # Use existing frame
        continue

# Start tracking
self.checkpoint.start_shot(scene_num, shot_num)

# Generate image
frame_path = await self._generate_frame(...)

# Mark complete
raw_frame_path = frame_path.replace(".png", "_raw.png")
self.checkpoint.complete_shot(
    scene_num, shot_num,
    image_path=frame_path,
    raw_image_path=raw_frame_path if os.path.exists(raw_frame_path) else None,
)
```

### 5. Checkpoint Before Video Generation

```python
# For shot-level tracking
shot_num = 1  # Video generation

# RESUME CHECK: Skip if already completed
if self.checkpoint.is_shot_completed(scene_num, shot_num) and not self.force_regenerate:
    if os.path.exists(video_path):
        # Use existing video
        continue

# Start tracking
self.checkpoint.start_shot(scene_num, shot_num)

# Generate video
video_path = await self._generate_video(...)

# Mark complete
self.checkpoint.complete_shot(
    scene_num, shot_num,
    video_path=video_path,
)
```

### 6. Mark Scene/Episode Complete

```python
# After all shots in scene/episode are done
output_files = [frame_path, video_path]  # All outputs
self.checkpoint.complete_scene(scene_num, output_files=output_files)
# OR for episodes:
self.checkpoint.complete_episode(episode_num, output_files=output_files)
```

### 7. Error Handling

```python
try:
    # ... generation code ...
except Exception as e:
    self.logger.error(f"Failed: {e}")
    self.checkpoint.fail_shot(scene_num, shot_num, str(e))
    # OR
    self.checkpoint.fail_scene(scene_num, str(e))
```

### 8. Mark Run Complete at End

```python
# At end of __call__, before S3 sync
self.checkpoint.mark_completed()

# Sync to S3 (includes checkpoint.json)
self.memory.sync_to_s3(exclude_patterns=["*.mp4"])
```

## Shot-Level Tracking

For pipelines that generate multiple shots/frames per scene:

- **Shot 0**: Frame/image generation
- **Shot 1**: Video generation  
- **Shot 2+**: Additional frames/videos if needed

This allows resuming at the exact shot level, avoiding regeneration of:
- ✅ Already generated images
- ✅ Already generated videos
- ✅ Already generated raw/gelled frames

## Key Benefits

1. **Resource Efficiency**: No wasted API calls for completed work
2. **Time Savings**: Resume from exact failure point
3. **Cost Reduction**: Avoid regenerating expensive video generations
4. **Reliability**: Handle network issues, rate limits, crashes gracefully
5. **S3 Integration**: Automatic sync/restore from cloud storage

## Testing Checklist

For each pipeline, verify:

- [ ] Checkpoint file created in working_dir
- [ ] S3 sync works when local folder missing
- [ ] Resume skips completed scenes/episodes/shots
- [ ] ContinuityMemory restored on resume
- [ ] Image generation skipped if already exists
- [ ] Video generation skipped if already exists
- [ ] Partial failures don't stop entire run
- [ ] Checkpoint synced to S3 on completion

---

*Last Updated: 2026-01-26*
