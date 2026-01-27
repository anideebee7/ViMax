"""
Pipeline API Routes

FastAPI router exposing all ViMax content generation pipelines as HTTP endpoints.
Pipelines run as background tasks; use GET /pipelines/tasks/{task_id} to check status.

Usage:
    POST /pipelines/movie         - Generate full-length movie script
    POST /pipelines/short_movie    - Generate short film script
    POST /pipelines/lyrics        - Generate song lyrics
    POST /pipelines/documentary   - Generate documentary content
    POST /pipelines/ad            - Generate advertisement content
    POST /pipelines/video         - Generate video from idea
    POST /pipelines/script2video  - Convert script to video
    POST /pipelines/song          - Generate complete song (lyrics + audio)
    POST /pipelines/music_video    - Generate music video concept
    POST /pipelines/kids_movie     - Generate kids animated movie content
    POST /pipelines/learning_series- Generate educational video series
    POST /pipelines/ad_banners     - Generate ad banner images
    POST /pipelines/tvseries      - Generate narrative TV series
    POST /pipelines/podcast2video - Convert podcast script to video
    GET  /pipelines/tasks/{task_id} - Get task status
"""
import asyncio
import os
import uuid
import tempfile
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query

from api.models.pipelines import (
    # Common
    PipelineTaskResponse, PipelineStatusResponse, PipelineStatus,
    # Request models
MovieRequest, ShortMovieRequest, ShortMovieVideoRequest,
LyricsRequest, DocumentaryRequest, AdRequest, VideoRequest,
    Script2VideoRequest, SongRequest, Song2MusicVideoRequest,
KidsMovieRequest, LearningSeriesRequest, AdBannersRequest,
    Podcast2VideoRequest,
    # Response models
MovieResponse, ShortMovieResponse, ShortMovieVideoResponse,
LyricsResponse, DocumentaryResponse, AdResponse, VideoResponse,
    Script2VideoResponse, SongResponse, Song2MusicVideoResponse,
KidsMovieResponse, LearningSeriesResponse, AdBannersResponse,
    Podcast2VideoResponse, TVSeriesRequest, TVSeriesResponse,
)


router = APIRouter(prefix="/pipelines", tags=["Pipelines"])

# Task storage (in production, use Redis or database)
pipeline_tasks: Dict[str, Dict] = {}

# Thread pool for running async tasks
executor = ThreadPoolExecutor(max_workers=4)


def run_async_task(coro):
    """Run an async coroutine in a new event loop (for background tasks)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Task Status Endpoint
# =============================================================================

@router.get("/tasks/{task_id}", response_model=PipelineStatusResponse)
async def get_pipeline_task_status(task_id: str):
    """Get the status of a pipeline task"""
    if task_id not in pipeline_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = pipeline_tasks[task_id]
    return PipelineStatusResponse(
        task_id=task_id,
        pipeline=task.get("pipeline", "unknown"),
        status=task.get("status", PipelineStatus.PENDING),
        progress=task.get("progress"),
        message=task.get("message"),
        result=task.get("result"),
        error=task.get("error"),
        output_path=task.get("output_path"),
    )


@router.get("/tasks", response_model=Dict[str, PipelineStatusResponse])
async def list_pipeline_tasks(
    pipeline: Optional[str] = Query(None, description="Filter by pipeline name"),
    status: Optional[PipelineStatus] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum tasks to return"),
):
    """List pipeline tasks with optional filters"""
    result = {}
    count = 0
    for task_id, task in pipeline_tasks.items():
        if count >= limit:
            break
        if pipeline and task.get("pipeline") != pipeline:
            continue
        if status and task.get("status") != status:
            continue
        result[task_id] = PipelineStatusResponse(
            task_id=task_id,
            pipeline=task.get("pipeline", "unknown"),
            status=task.get("status", PipelineStatus.PENDING),
            progress=task.get("progress"),
            message=task.get("message"),
            result=task.get("result"),
            error=task.get("error"),
            output_path=task.get("output_path"),
        )
        count += 1
    return result


# =============================================================================
# movie
# =============================================================================

@router.post("/movie", response_model=PipelineTaskResponse)
async def generate_movie(
    request: MovieRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/movie.yaml", description="Path to config file"),
):
    """
    Generate a full-length movie script (60-200 minutes).
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    Result includes story, characters, script with 3-act structure, and monetization plan.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "movie",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting movie generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.movies.standard import MoviePipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline_tasks[task_id]["progress"] = 5
            pipeline_tasks[task_id]["message"] = "Initializing pipeline..."
            
            pipeline = MoviePipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            pipeline_tasks[task_id]["progress"] = 10
            pipeline_tasks[task_id]["message"] = "Generating movie script..."
            
            result = await pipeline(
                premise=request.premise,
                genre=request.genre,
                target_runtime_minutes=request.target_runtime_minutes,
                audience=request.audience,
                style=request.style,
                trendy=request.trendy,
                content_format=request.content_format.value,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["message"] = "Movie script generated successfully"
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
            pipeline_tasks[task_id]["message"] = f"Failed: {e}"
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="movie",
        status=PipelineStatus.PENDING,
        message="Movie generation started",
    )


# =============================================================================
# short_movie
# =============================================================================

@router.post("/short_movie", response_model=PipelineTaskResponse)
async def generate_short_movie(
    request: ShortMovieRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/short_movie.yaml", description="Path to config file"),
):
    """
    Generate a short film script (5-20 minutes).
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "short_movie",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting short movie generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.movies.short import ShortMoviePipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = ShortMoviePipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                premise=request.premise,
                genre=request.genre,
                target_duration_minutes=request.target_duration_minutes,
                audience=request.audience,
                style=request.style,
                trendy=request.trendy,
                content_format=request.content_format.value,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="short_movie",
        status=PipelineStatus.PENDING,
        message="Short movie generation started",
    )


# =============================================================================
# short_video (end-to-end with video generation)
# =============================================================================

@router.post("/shortmovie-video", response_model=PipelineTaskResponse)
async def generate_short_movie_video(
    request: ShortMovieVideoRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/short_video.yaml", description="Path to config file"),
):
    """
    Generate a complete short film video (5-20 minutes) with storyboards and video clips.
    
    This is an end-to-end pipeline that produces actual video output, unlike /shortmovie
    which only generates the script.
    
    Flow: idea → story → script → storyboards → scene videos → final video
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    
    Note: This pipeline is resource-intensive and may take several minutes per scene.
    Use max_scenes to limit processing for testing.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "short_video",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting short movie video generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.movies.short_video import ShortMovieVideoPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline_tasks[task_id]["progress"] = 5
            pipeline_tasks[task_id]["message"] = "Initializing pipeline..."
            
            pipeline = ShortMovieVideoPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            pipeline_tasks[task_id]["progress"] = 10
            pipeline_tasks[task_id]["message"] = "Generating story and script..."
            
            result = await pipeline(
                premise=request.premise,
                genre=request.genre,
                target_duration_minutes=request.target_duration_minutes,
                audience=request.audience,
                style=request.style,
                trendy=request.trendy,
                content_format=request.content_format.value,
                generate_storyboard_images=request.generate_storyboard_images,
                generate_videos=request.generate_videos,
                max_scenes=request.max_scenes,
                # S3 Entity Integration
                brand_id=request.brand_id,
                game_id=request.game_id,
                character_names=request.character_names,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["message"] = "Short movie video generated successfully"
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
            pipeline_tasks[task_id]["message"] = f"Failed: {e}"
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="short_video",
        status=PipelineStatus.PENDING,
        message="Short movie video generation started",
    )


# =============================================================================
# lyrics
# =============================================================================

@router.post("/lyrics", response_model=PipelineTaskResponse)
async def generate_lyrics(
    request: LyricsRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/lyrics.yaml", description="Path to config file"),
):
    """
    Generate song lyrics from an idea.
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    Result includes lyrics, metadata, and monetization plan.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "lyrics",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting lyrics generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.music.lyrics import LyricsPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = LyricsPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                idea=request.idea,
                user_requirement=request.user_requirement,
                style=request.style,
                genre=request.genre,
                mood=request.mood,
                audience=request.audience,
                trendy=request.trendy,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="lyrics",
        status=PipelineStatus.PENDING,
        message="Lyrics generation started",
    )


# =============================================================================
# documentary
# =============================================================================

@router.post("/documentary", response_model=PipelineTaskResponse)
async def generate_documentary(
    request: DocumentaryRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/documentary.yaml", description="Path to config file"),
):
    """
    Generate documentary content from a topic.
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    Result includes script, segments, narration, and monetization plan.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "documentary",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting documentary generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.content.documentary import DocumentaryPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = DocumentaryPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                topic=request.topic,
                target_duration_minutes=request.target_duration_minutes,
                research_depth=request.research_depth,
                audience=request.audience,
                style=request.style,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
                brand_hint=request.brand_hint,
                content_format=request.content_format.value,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="documentary",
        status=PipelineStatus.PENDING,
        message="Documentary generation started",
    )


# =============================================================================
# ad
# =============================================================================

@router.post("/ad", response_model=PipelineTaskResponse)
async def generate_ad(
    request: AdRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/ad.yaml", description="Path to config file"),
):
    """
    Generate advertisement content with A/B variants.
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    Result includes ad scripts, visuals, videos (if requested), and monetization plan.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "ad",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting ad generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.ads.video import AdPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = AdPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                brand=request.brand,
                product=request.product,
                campaign_goal=request.campaign_goal,
                audience=request.audience,
                ad_format=request.ad_format,
                generate_visuals=request.generate_visuals,
                generate_videos=request.generate_videos,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="ad",
        status=PipelineStatus.PENDING,
        message="Ad generation started",
    )


# =============================================================================
# video
# =============================================================================

@router.post("/video", response_model=PipelineTaskResponse)
async def generate_video(
    request: VideoRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/video.yaml", description="Path to config file"),
):
    """
    Generate a video from an idea.
    
    Supports standard videos and shorts (via shorts_mode or config).
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    
    Note: This pipeline can be slow for multi-scene videos.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "video",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting video generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.base.idea import VideoPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            
            # Use shorts config if shorts_mode requested
            effective_config = "configs/pipelines/video_shorts.yaml" if request.shorts_mode else config_path
            
            pipeline = VideoPipeline.init_from_config(effective_config)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                idea=request.idea,
                user_requirement=request.user_requirement,
                style=request.style,
                audience=request.audience,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
                brand_hint=request.brand_hint,
                content_format=request.content_format.value,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="video",
        status=PipelineStatus.PENDING,
        message="Video generation started",
    )


# =============================================================================
# script2video
# =============================================================================

@router.post("/script2video", response_model=PipelineTaskResponse)
async def convert_script_to_video(
    request: Script2VideoRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/script2video.yaml", description="Path to config file"),
):
    """
    Convert a script to video.
    
    Provide scene descriptions; the pipeline generates storyboards, frames, and video.
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "script2video",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting script-to-video conversion...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.base.script import Script2VideoPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = Script2VideoPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            content_format = request.content_format.value if request.content_format else None
            
            result = await pipeline(
                script=request.script,
                user_requirement=request.user_requirement,
                style=request.style,
                audience=request.audience,
                trendy=request.trendy,
                content_format=content_format,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="script2video",
        status=PipelineStatus.PENDING,
        message="Script-to-video conversion started",
    )


# =============================================================================
# song
# =============================================================================

@router.post("/song", response_model=PipelineTaskResponse)
async def generate_song(
    request: SongRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/song.yaml", description="Path to config file"),
):
    """
    Generate a complete song (lyrics + audio).
    
    Requires working audio generator (ElevenLabs/PiAPI Music).
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "song",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting song generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.music.song import SongPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = SongPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                idea=request.idea,
                user_requirement=request.user_requirement,
                style=request.style,
                audience=request.audience,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
                brand_hint=request.brand_hint,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="song",
        status=PipelineStatus.PENDING,
        message="Song generation started",
    )


# =============================================================================
# song2musicvideo
# =============================================================================

@router.post("/music_video", response_model=PipelineTaskResponse)
async def generate_music_video(
    request: Song2MusicVideoRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/song2musicvideo.yaml", description="Path to config file"),
):
    """
    Generate music video concept from song data.
    
    Supports kids_mode for G-rated animated content.
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "song2musicvideo",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting music video generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.music.song_to_video import Song2MusicVideoPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = Song2MusicVideoPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                song_title=request.song_title,
                lyrics=request.lyrics,
                genre=request.genre,
                mood=request.mood,
                song_structure=request.song_structure,
                style=request.style,
                audience=request.audience,
                generate_storyboard_images=request.generate_storyboard_images,
                trendy=request.trendy,
                kids_mode=request.kids_mode,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="song2musicvideo",
        status=PipelineStatus.PENDING,
        message="Music video generation started",
    )


# =============================================================================
# kids_movie
# =============================================================================

@router.post("/kids_movie", response_model=PipelineTaskResponse)
async def generate_kids_movie(
    request: KidsMovieRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/kids_movie.yaml", description="Path to config file"),
):
    """
    Generate kids animated movie content.
    
    Age-appropriate, G-rated content with moral lessons.
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "kids_movie",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting kids movie generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.movies.kids import KidsMoviePipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = KidsMoviePipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                story_idea=request.story_idea,
                age_group=request.age_group,
                characters=request.characters,
                moral_lesson=request.moral_lesson,
                target_duration_minutes=request.target_duration_minutes,
                style=request.style,
                audience=request.audience,
                generate_character_art=request.generate_character_art,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
                brand_hint=request.brand_hint,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="kids_movie",
        status=PipelineStatus.PENDING,
        message="Kids movie generation started",
    )


# =============================================================================
# learning_series
# =============================================================================

@router.post("/learning_series", response_model=PipelineTaskResponse)
async def generate_learning_series(
    request: LearningSeriesRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/learning_series.yaml", description="Path to config file"),
):
    """
    Generate educational video series with curriculum.
    
    Creates complete course structure with episodes, visuals, and videos.
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "learning_series",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting learning series generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.series.learning import LearningSeriesPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = LearningSeriesPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                topic=request.topic,
                num_episodes=request.num_episodes,
                episode_duration_minutes=request.episode_duration_minutes,
                audience=request.audience,
                skill_level=request.skill_level,
                learning_goals=request.learning_goals,
                trendy=request.trendy,
                generate_images=request.generate_images,
                generate_videos=request.generate_videos,
                visual_style=request.visual_style,
                max_episodes_to_generate=request.max_episodes_to_generate,
                brand_id=request.brand_id,
                game_id=request.game_id,
                character_names=request.character_names,
                featured_character=request.featured_character,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="learning_series",
        status=PipelineStatus.PENDING,
        message="Learning series generation started",
    )


# =============================================================================
# adbanners
# =============================================================================

@router.post("/ad_banners", response_model=PipelineTaskResponse)
async def generate_ad_banners(
    request: AdBannersRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/ad_banners.yaml", description="Path to config file"),
):
    """
    Generate high-converting ad banner images.
    
    Creates multiple concepts with various sizes for different platforms.
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "ad_banners",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting ad banners generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.ads.banners import AdBannersPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = AdBannersPipeline.init_from_config(config_path)
            pipeline.force_regenerate = True
            
            result = await pipeline(
                brand_or_game=request.brand_or_game,
                entity_type=request.entity_type,
                brief=request.brief,
                audience=request.audience,
                campaign_goal=request.campaign_goal,
                platforms=request.platforms,
                trendy=request.trendy,
                brand_id=request.brand_id,
                game_id=request.game_id,
                num_concepts=request.num_concepts,
                sizes=request.sizes,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="adbanners",
        status=PipelineStatus.PENDING,
        message="Ad banners generation started",
    )


# =============================================================================
# podcast2video
# =============================================================================

@router.post("/podcast2video", response_model=PipelineTaskResponse)
async def convert_podcast_to_video(
    request: Podcast2VideoRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/podcast2video.yaml", description="Path to config file"),
):
    """
    Convert podcast script to video.
    
    Uses S3-hosted character assets for consistent visuals.
    Provide script_text or script_path (path to PDF/TXT file).
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    
    Note: This pipeline can be slow for full episodes; use max_scenes for testing.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "podcast2video",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting podcast-to-video conversion...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.content.podcast import Podcast2VideoPipeline, PodcastConfig
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            
            # Create podcast config
            podcast_config = PodcastConfig(
                brand_id=request.brand_id,
                working_dir=".working_dir/podcast",
            )
            
            pipeline = Podcast2VideoPipeline.init_from_config(config_path, podcast_config)
            
            # Handle script_text by writing to temp file
            script_path = request.script_path
            temp_file = None
            if request.script_text and not script_path:
                temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
                temp_file.write(request.script_text)
                temp_file.close()
                script_path = temp_file.name
            
            if not script_path:
                raise ValueError("Either script_text or script_path must be provided")
            
            try:
                result = await pipeline.run(
                    script_path=script_path,
                    max_scenes=request.max_scenes,
                    audience=request.audience,
                    trendy=request.trendy,
                    auto_ideate=request.auto_ideate,
                    ideation_mode=request.ideation_mode.value,
                    topic_area=request.topic_area,
                )
                
                pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
                pipeline_tasks[task_id]["progress"] = 100
                pipeline_tasks[task_id]["result"] = result
                pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
                
            finally:
                if temp_file:
                    try:
                        os.unlink(temp_file.name)
                    except OSError:
                        pass
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="podcast2video",
        status=PipelineStatus.PENDING,
        message="Podcast-to-video conversion started",
    )


# =============================================================================
# tvseries
# =============================================================================

@router.post("/tvseries", response_model=PipelineTaskResponse)
async def generate_tv_series(
    request: TVSeriesRequest,
    background_tasks: BackgroundTasks,
    config_path: str = Query("configs/pipelines/movie.yaml", description="Path to config file"),
):
    """
    Generate a narrative TV series with seasonal arc.
    
    Returns a task_id; poll GET /pipelines/tasks/{task_id} for status.
    """
    task_id = str(uuid.uuid4())
    pipeline_tasks[task_id] = {
        "pipeline": "tvseries",
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "message": "Starting TV series generation...",
    }
    
    async def run_pipeline():
        try:
            from pipelines.series.tv import TVSeriesPipeline
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.PROCESSING
            pipeline = TVSeriesPipeline.init_from_config(config_path)
            
            result = await pipeline(
                premise=request.premise,
                genre=request.genre,
                num_episodes=request.num_episodes,
                episode_duration_minutes=request.episode_duration_minutes,
                audience=request.audience,
                style=request.style,
                trendy=request.trendy,
                auto_ideate=request.auto_ideate,
                ideation_mode=request.ideation_mode.value,
                max_episodes_to_generate=request.max_episodes_to_generate,
            )
            
            pipeline_tasks[task_id]["status"] = PipelineStatus.COMPLETED
            pipeline_tasks[task_id]["progress"] = 100
            pipeline_tasks[task_id]["result"] = result
            pipeline_tasks[task_id]["output_path"] = pipeline.working_dir
            
        except Exception as e:
            pipeline_tasks[task_id]["status"] = PipelineStatus.FAILED
            pipeline_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, run_pipeline())
    
    return PipelineTaskResponse(
        task_id=task_id,
        pipeline="tvseries",
        status=PipelineStatus.PENDING,
        message="TV series generation started",
    )


# =============================================================================
# Documentation Endpoint
# =============================================================================

@router.get("/docs/overview")
async def get_pipeline_documentation():
    """
    Get overview documentation for all pipeline endpoints.
    """
    return {
        "title": "ViMax Pipeline API",
        "description": "HTTP API for all ViMax content generation pipelines",
        "version": "1.0.0",
        "pipelines": {
            "movie": {
                "endpoint": "POST /pipelines/movie",
                "description": "Generate full-length movie scripts (60-200 min)",
                "config": "configs/pipelines/movie.yaml",
                "requires_media": False,
                "typical_duration": "30-60 seconds",
            },
            "shortmovie": {
                "endpoint": "POST /pipelines/shortmovie",
                "description": "Generate short film scripts (5-20 min) - script only",
                "config": "configs/pipelines/short_movie.yaml",
                "requires_media": False,
                "typical_duration": "20-40 seconds",
            },
            "shortmovie-video": {
                "endpoint": "POST /pipelines/shortmovie-video",
                "description": "Generate complete short film VIDEO (5-20 min) with storyboards",
                "config": "configs/pipelines/short_video.yaml",
                "requires_media": True,
                "typical_duration": "5-30 minutes (varies by scene count)",
                "note": "End-to-end pipeline: idea → script → storyboards → scene videos → final video",
            },
            "lyrics": {
                "endpoint": "POST /pipelines/lyrics",
                "description": "Generate song lyrics",
                "config": "configs/pipelines/lyrics.yaml",
                "requires_media": False,
                "typical_duration": "10-20 seconds",
            },
            "documentary": {
                "endpoint": "POST /pipelines/documentary",
                "description": "Generate documentary scripts and narration",
                "config": "configs/pipelines/documentary.yaml",
                "requires_media": "Optional (image/video for B-roll)",
                "typical_duration": "30-60 seconds",
            },
            "ad": {
                "endpoint": "POST /pipelines/ad",
                "description": "Generate advertisement content with A/B variants",
                "config": "configs/pipelines/ad.yaml",
                "requires_media": "Optional (for visuals/videos)",
                "typical_duration": "20-120 seconds",
            },
            "video": {
                "endpoint": "POST /pipelines/video",
                "description": "Generate video from idea (standard or shorts)",
                "config": "configs/pipelines/video.yaml or configs/pipelines/video_shorts.yaml",
                "requires_media": True,
                "typical_duration": "2-10 minutes (varies by scene count)",
            },
            "script2video": {
                "endpoint": "POST /pipelines/script2video",
                "description": "Convert script to video",
                "config": "configs/pipelines/script2video.yaml",
                "requires_media": True,
                "typical_duration": "1-5 minutes (varies by scene count)",
            },
            "song": {
                "endpoint": "POST /pipelines/song",
                "description": "Generate complete song (lyrics + audio)",
                "config": "configs/pipelines/song.yaml",
                "requires_media": True,
                "requires_audio": "ElevenLabs or PiAPI Music",
                "typical_duration": "30-120 seconds",
            },
            "musicvideo": {
                "endpoint": "POST /pipelines/musicvideo",
                "description": "Generate music video concept and storyboard",
                "config": "configs/pipelines/song2musicvideo.yaml",
                "requires_media": "Optional (for storyboard images)",
                "typical_duration": "30-60 seconds",
            },
            "kidsmovie": {
                "endpoint": "POST /pipelines/kidsmovie",
                "description": "Generate kids animated movie content",
                "config": "configs/pipelines/kids_movie.yaml",
                "requires_media": "Optional (for character art)",
                "typical_duration": "30-60 seconds",
            },
            "learningseries": {
                "endpoint": "POST /pipelines/learningseries",
                "description": "Generate educational video series",
                "config": "configs/pipelines/learning_series.yaml",
                "requires_media": "Optional (for episode visuals/videos)",
                "typical_duration": "1-10 minutes (varies by episode count)",
            },
            "adbanners": {
                "endpoint": "POST /pipelines/adbanners",
                "description": "Generate ad banner images",
                "config": "configs/pipelines/ad_banners.yaml",
                "requires_media": True,
                "typical_duration": "30-120 seconds",
            },
            "podcast2video": {
                "endpoint": "POST /pipelines/podcast2video",
                "description": "Convert podcast script to video",
                "config": "configs/pipelines/podcast2video.yaml",
                "requires_media": True,
                "typical_duration": "5-30 minutes (varies by scene count)",
            },
        },
        "common_parameters": {
            "trendy": "bool - Incorporate real-time trending topics (requires trend_analyzer in config)",
            "auto_ideate": "bool - Auto-generate the idea/premise using AI",
            "ideation_mode": "str - Mode for auto-ideation: creativity, trends, viral, brand, podcast",
            "content_format": "str - Visual style: live_action, animated, hybrid",
            "audience": "str - Target audience: G, PG, PG-13, R, kids, teens, adults, family",
        },
        "task_workflow": {
            "1": "POST /pipelines/{pipeline} with request body → returns task_id",
            "2": "GET /pipelines/tasks/{task_id} → returns status, progress, result",
            "3": "When status=completed, result contains pipeline output and output_path",
        },
        "error_handling": {
            "status=failed": "Check 'error' field for error message",
            "common_errors": [
                "Missing API keys (GEMINI_API_KEY, PIAPI_API_KEY, etc.)",
                "Invalid config path",
                "Missing required parameters",
            ],
        },
    }
