# ViMax Documentation

## Quick Navigation

| Document | Description |
|----------|-------------|
| [API_KEYS_SETUP.md](./API_KEYS_SETUP.md) | How to configure API keys for various services |
| [DOCKER.md](./DOCKER.md) | Docker deployment instructions |
| [PIPELINE_API_README.md](./PIPELINE_API_README.md) | REST API documentation |
| [S3_ASSETS_GUIDE.md](./S3_ASSETS_GUIDE.md) | Guide for S3 character/brand assets |
| [CONTENT_PLANNER_README.md](./CONTENT_PLANNER_README.md) | Content planning workflow |
| [IDEA2ADBANNERS_README.md](./IDEA2ADBANNERS_README.md) | Ad banner generation |
| [CHARACTER_CONSISTENCY_ANALYSIS.md](./CHARACTER_CONSISTENCY_ANALYSIS.md) | Technical analysis of character consistency |
| [Communication.md](./Communication.md) | Community and communication channels |

## Getting Started

1. **Setup**: See [API_KEYS_SETUP.md](./API_KEYS_SETUP.md) for configuration
2. **Docker**: See [DOCKER.md](./DOCKER.md) for containerized deployment
3. **API**: See [PIPELINE_API_README.md](./PIPELINE_API_README.md) for REST endpoints

## Pipeline Documentation

Each pipeline has specific configuration in `configs/` and examples in `examples/`.

### Video Pipelines

- **video** - Generate video from idea/script
- **short_movie-video** - Generate complete short film (5-20 min)
- **script2video** - Generate video from existing script

### Movie Pipelines

- **movie** - Generate full movie script (60-180 min)
- **short_movie** - Generate short film script
- **kids_movie** - Generate kids movie
- **documentary** - Generate documentary

### Music Pipelines

- **lyrics** - Generate song lyrics
- **song** - Generate lyrics + composition plan
- **music_video** - Generate complete music video
- **song2musicvideo** - Generate music video from existing song

### Advertising Pipelines

- **ad** - Generate ad video
- **adbanners** - Generate ad banners

### Other Pipelines

- **learning_series** - Generate educational content
- **podcast2video** - Convert podcast to video
- **novel2movie** - Adapt novel to movie

## Configuration

Pipeline configs are in `configs/` with format:

```yaml
chat_model:
  init_args:
    model: "openai/gpt-4o-mini"
    api_key: "${OPENAI_API_KEY}"

image_generator:
  module: "tools.image_generator_..."
  class: "..."

video_generator:
  module: "tools.video_generator_..."
  class: "..."
```

## Character Consistency

ViMax uses a multi-step approach to maintain character consistency:

1. **S3 Character Resolution** - Load existing character assets
2. **Portrait Generation** - Generate canonical character portraits
3. **Reference Images** - Pass portraits to AI generators
4. **Post-Processing Compositing** - Overlay portraits on frames

See [CHARACTER_CONSISTENCY_ANALYSIS.md](./CHARACTER_CONSISTENCY_ANALYSIS.md) for details.
