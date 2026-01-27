# Checkpoint and Resume System

## Overview

All pipelines now support robust checkpoint and resume functionality. This allows seamless recovery from incomplete, aborted, or errored runs using just the `run_id` folder.

## Features

### ✅ Automatic Checkpoint Tracking
- **Phase-level tracking**: Each major phase (curriculum, episodes, scenes) is tracked
- **Episode-level tracking**: Individual episodes in series pipelines
- **Scene-level tracking**: Individual scenes in movie pipelines
- **Error tracking**: All errors are logged with context

### ✅ Resume Capabilities
- **Automatic detection**: Pipeline automatically detects incomplete runs
- **S3 sync fallback**: If local folder missing, syncs from S3 automatically
- **ContinuityMemory restoration**: Character/prop/lighting state restored
- **Skip completed work**: Only processes incomplete phases/episodes/scenes

### ✅ Failure Handling
- **Graceful degradation**: Failed episodes/scenes don't stop entire run
- **Error logging**: All errors tracked in checkpoint with timestamps
- **Partial completion**: Run marked as "partial" if some items failed

## Usage

### Basic Resume

Simply run the pipeline again with the same `run_id`:

```python
pipeline = LearningSeriesPipeline(
    chat_model=chat_model,
    image_generator=image_generator,
    video_generator=video_generator,
    working_dir=".working_dir/learning_series",
    run_id="existing_run_id",  # Same run_id as before
)

result = await pipeline(
    topic="Python Programming",
    num_episodes=5,
    # ... other params
)
```

The pipeline will:
1. Check for existing checkpoint
2. Sync from S3 if local folder missing
3. Restore ContinuityMemory state
4. Skip completed phases/episodes
5. Resume from last incomplete point

### Force Regenerate

To ignore checkpoints and start fresh:

```python
pipeline = LearningSeriesPipeline(
    # ...
    force_regenerate=True,  # Ignores checkpoints
)
```

### Check Resume Status

```python
checkpoint = pipeline.checkpoint.load()
if checkpoint:
    resume_info = pipeline.checkpoint.get_resume_info()
    print(f"Status: {resume_info['status']}")
    print(f"Completed episodes: {resume_info['completed_episodes']}")
    print(f"Errors: {resume_info['errors']}")
```

## Checkpoint File Structure

Checkpoints are stored in `{working_dir}/checkpoint.json`:

```json
{
  "run_id": "learning_series_20260126_123456",
  "pipeline_type": "learning_series",
  "status": "in_progress",
  "created_at": "2026-01-26T12:34:56",
  "updated_at": "2026-01-26T12:45:30",
  "phases": {
    "curriculum": {
      "phase_name": "curriculum",
      "status": "completed",
      "started_at": "2026-01-26T12:34:57",
      "completed_at": "2026-01-26T12:35:15",
      "output_files": ["curriculum.json"]
    }
  },
  "episodes": {
    "1": {
      "episode_number": 1,
      "status": "completed",
      "started_at": "2026-01-26T12:35:20",
      "completed_at": "2026-01-26T12:40:10",
      "output_files": ["episode_01/episode_01_full.mp4"]
    },
    "2": {
      "episode_number": 2,
      "status": "failed",
      "started_at": "2026-01-26T12:40:15",
      "completed_at": "2026-01-26T12:42:30",
      "error": "Video generation timeout"
    }
  },
  "errors": [
    "Episode 2: Video generation timeout"
  ]
}
```

## Status Values

- `not_started`: Run initialized but not started
- `in_progress`: Run currently executing
- `completed`: All phases/episodes completed successfully
- `failed`: Run failed (critical error)
- `aborted`: Run was manually aborted
- `partial`: Some items completed, some failed

## Integration with ContinuityMemory

Checkpoint system automatically:
1. **Restores ContinuityMemory** from `series_continuity.json` on resume
2. **Saves ContinuityMemory** after each episode/scene
3. **Preserves state** across resume operations

## S3 Integration

When resuming:
1. Pipeline checks if local `working_dir` exists
2. If missing, automatically syncs from S3 using `RunMemory.sync_from_s3()`
3. Restores checkpoint, ContinuityMemory, and all intermediate files
4. Resumes from last checkpoint

## Pipeline Coverage

### ✅ Fully Integrated
- `LearningSeriesPipeline` - Example implementation

### 🔄 To Be Integrated
- `TVSeriesPipeline`
- `PodcastSeriesPipeline`
- `WeeklySeriesPipeline`
- `MoviePipeline`
- `ShortMovieVideoPipeline`
- `MusicVideoPipeline`
- `Song2MusicVideoPipeline`
- `VideoPipeline` (base)
- `Script2VideoPipeline`
- `Podcast2VideoPipeline`
- `DocumentaryPipeline`
- `AdPipeline`
- `ViralShortsPipeline`

## Implementation Pattern

For each pipeline, add:

1. **Initialize CheckpointManager**:
```python
from utils.pipeline.checkpoint import CheckpointManager

self.checkpoint = CheckpointManager(
    working_dir=self.working_dir,
    run_id=self.run_id,
    pipeline_type="pipeline_name"
)
```

2. **Check for resume at start**:
```python
# Sync from S3 if needed
if not os.path.exists(self.working_dir):
    self.memory.sync_from_s3()

# Load checkpoint
checkpoint = self.checkpoint.load()
can_resume = self.checkpoint.can_resume()
```

3. **Track phases**:
```python
self.checkpoint.start_phase("phase_name")
try:
    # ... do work ...
    self.checkpoint.complete_phase("phase_name", output_files=[...])
except Exception as e:
    self.checkpoint.fail_phase("phase_name", str(e))
```

4. **Track episodes/scenes**:
```python
if self.checkpoint.is_episode_completed(episode_num):
    # Skip
    continue

self.checkpoint.start_episode(episode_num)
try:
    # ... process episode ...
    self.checkpoint.complete_episode(episode_num, output_files=[...])
except Exception as e:
    self.checkpoint.fail_episode(episode_num, str(e))
```

5. **Mark completed at end**:
```python
self.checkpoint.mark_completed()
```

## Error Scenarios Handled

1. **Network timeout during generation**: Episode marked as failed, others continue
2. **API rate limit**: Phase marked as failed, can resume later
3. **Disk full**: Checkpoint saved before crash, resume from last saved point
4. **Process killed**: Checkpoint preserved, resume on restart
5. **S3 sync failure**: Falls back to local checkpoint if available

## Best Practices

1. **Always use run_id**: Enables resume functionality
2. **Check resume status**: Before long runs, check what's already done
3. **Monitor checkpoint file**: Check `checkpoint.json` for progress
4. **Handle partial runs**: Some episodes may fail, but run continues
5. **S3 backup**: Checkpoint automatically synced to S3 on completion

---

*Last Updated: 2026-01-26*
