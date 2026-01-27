# ViMax Pipeline API

HTTP API for all ViMax content generation pipelines. Run the server and use REST endpoints to generate movies, videos, songs, ads, and more.

## Quick Start

```bash
# Start the API server
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Open API docs
open http://localhost:8000/docs
```

## Available Pipelines

| Endpoint | Pipeline | Description | Media Required |
|----------|----------|-------------|----------------|
| `POST /pipelines/movie` | movie | Full-length movie scripts (60-200 min) | No |
| `POST /pipelines/shortmovie` | short_movie | Short film scripts (5-20 min) | No |
| `POST /pipelines/lyrics` | lyrics | Song lyrics | No |
| `POST /pipelines/documentary` | documentary | Documentary scripts and narration | Optional |
| `POST /pipelines/ad` | ad | Advertisement content with A/B variants | Optional |
| `POST /pipelines/video` | video | Video from idea (standard or shorts) | Yes |
| `POST /pipelines/script2video` | script2video | Convert script to video | Yes |
| `POST /pipelines/song` | song | Complete song (lyrics + audio) | Yes (audio) |
| `POST /pipelines/musicvideo` | song2musicvideo | Music video concept and storyboard | Optional |
| `POST /pipelines/kidsmovie` | kids_movie | Kids animated movie content | Optional |
| `POST /pipelines/learningseries` | learning_series | Educational video series | Optional |
| `POST /pipelines/adbanners` | adbanners | Ad banner images | Yes |
| `POST /pipelines/podcast2video` | podcast2video | Convert podcast script to video | Yes |

## Workflow

All pipelines run as background tasks:

```
1. POST /pipelines/{pipeline}  →  returns { task_id, status: "pending" }
2. GET /pipelines/tasks/{task_id}  →  returns { status, progress, result }
3. When status="completed", result contains full output and output_path
```

## Examples

### Generate a Movie Script

```bash
curl -X POST http://localhost:8000/pipelines/movie \
  -H "Content-Type: application/json" \
  -d '{
    "premise": "A retired astronaut discovers signals from her long-lost space station",
    "genre": "sci-fi drama",
    "target_runtime_minutes": 110,
    "audience": "PG-13",
    "content_format": "live_action"
  }'
```

Response:
```json
{
  "task_id": "abc123-...",
  "pipeline": "movie",
  "status": "pending",
  "message": "Movie generation started"
}
```

Check status:
```bash
curl http://localhost:8000/pipelines/tasks/abc123-...
```

### Generate a Short Video

```bash
curl -X POST http://localhost:8000/pipelines/video \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "A robot learns to paint",
    "user_requirement": "Emotional, reflective tone",
    "style": "cinematic",
    "content_format": "animated",
    "shorts_mode": true
  }'
```

### Generate Song Lyrics

```bash
curl -X POST http://localhost:8000/pipelines/lyrics \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "Finding hope after a storm",
    "user_requirement": "Uplifting chorus, acoustic feel",
    "style": "folk pop",
    "mood": "hopeful",
    "audience": "young adults"
  }'
```

### Generate Ad Banners

```bash
curl -X POST http://localhost:8000/pipelines/adbanners \
  -H "Content-Type: application/json" \
  -d '{
    "brand_or_game": "QuizVerse",
    "entity_type": "game",
    "brief": "Summer campaign for trivia app",
    "audience": "Mobile gamers 18-35",
    "campaign_goal": "App installs",
    "num_concepts": 3,
    "sizes": ["medium_rectangle", "leaderboard", "square_social"]
  }'
```

### Generate Educational Series

```bash
curl -X POST http://localhost:8000/pipelines/learningseries \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Introduction to Machine Learning",
    "num_episodes": 5,
    "episode_duration_minutes": 10,
    "skill_level": "beginner",
    "learning_goals": "Understand ML concepts, train a simple model",
    "generate_images": true,
    "generate_videos": false
  }'
```

## Common Parameters

### Content Format
- `live_action` - Real-world footage style
- `animated` - 2D/3D animation style
- `hybrid` - Mix of both (documentaries)

### Audience
- MPAA ratings: `G`, `PG`, `PG-13`, `R`, `NC-17`
- Age groups: `kids 3-5`, `kids 6-8`, `kids 9-12`, `teens`, `young adult`, `adults`
- General: `family`, `general`

### Ideation Mode
When `auto_ideate=true`:
- `creativity` - Free creative ideation
- `trends` - Based on real-time trends
- `viral` - Optimized for viral potential
- `brand` - Brand-aligned content (use with `brand_hint`)
- `podcast` - Podcast-style content

### Trendy Flag
Set `trendy=true` to incorporate real-time trending topics. Requires `trend_analyzer` configured in the pipeline's YAML config with enabled sources (Google Trends, YouTube, Reddit, NewsAPI).

## Configuration

Each pipeline uses a YAML config file. Override with `?config_path=path/to/config.yaml`:

```bash
curl -X POST "http://localhost:8000/pipelines/movie?config_path=configs/custom_movie.yaml" \
  -H "Content-Type: application/json" \
  -d '{"premise": "...", "genre": "comedy"}'
```

## Environment Variables

Required for different pipelines:

| Variable | Used By | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | Most pipelines | Google Gemini for chat/image/video |
| `XAI_API_KEY` | video, script2video, podcast2video | xAI Grok for chat |
| `PIAPI_API_KEY` | ad, adbanners, documentary | PiAPI for image/video generation |
| `PIAPI_IMAGE_MODEL` | PiAPI pipelines | Model for image generation |
| `PIAPI_VIDEO_MODEL` | PiAPI pipelines | Model for video generation |
| `YOUTUBE_API_KEY` | Trend analyzer | YouTube trends |
| `NEWSAPI_KEY` | Trend analyzer | NewsAPI trends |

## Task Management

### List all tasks
```bash
curl "http://localhost:8000/pipelines/tasks?limit=10"
```

### Filter by pipeline
```bash
curl "http://localhost:8000/pipelines/tasks?pipeline=movie"
```

### Filter by status
```bash
curl "http://localhost:8000/pipelines/tasks?status=completed"
```

## Output Structure

Completed tasks include:
- `result` - Full pipeline output (JSON)
- `output_path` - Path to working directory with all generated files

Example `output_path` contents:
```
.working_dir/movie/movie_20260125_123456_abc123/
├── movie_output.json    # Full result
├── story.txt            # Story synopsis
├── script.json          # Scene-by-scene script
├── characters.json      # Character descriptions
├── trends.json          # Trend data (if trendy=true)
└── ...
```

## Error Handling

When `status=failed`:
```json
{
  "task_id": "abc123",
  "pipeline": "movie",
  "status": "failed",
  "error": "Missing required API key: GEMINI_API_KEY"
}
```

Common errors:
- Missing API keys
- Invalid config path
- Missing required parameters (e.g., `topic` for documentary without `auto_ideate`)
- Rate limits exceeded

## API Documentation

Interactive documentation available at:
- **API Explorer (frontend)**: Run `cd frontend && npm install && npm run dev`, then open http://localhost:5173. Exposes all core (brands, games, characters, tasks) and pipeline endpoints with forms.
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Pipeline overview: `GET /pipelines/docs/overview`
