"""
Pydantic models for Pipeline API

Request/response models for all ViMax content generation pipelines:
- movie, short_movie, lyrics, documentary
- ad, video, script2video, song
- song2musicvideo, kids_movie, learning_series
- adbanners, podcast2video, tvseries
"""
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================================
# Enums and Common Types
# =============================================================================

class ContentFormat(str, Enum):
    LIVE_ACTION = "live_action"
    ANIMATED = "animated"
    HYBRID = "hybrid"


class IdeationMode(str, Enum):
    CREATIVITY = "creativity"
    TRENDS = "trends"
    VIRAL = "viral"
    BRAND = "brand"
    PODCAST = "podcast"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Base Models
# =============================================================================

class PipelineTaskResponse(BaseModel):
    """Response when a pipeline task is started"""
    task_id: str
    pipeline: str
    status: PipelineStatus = PipelineStatus.PENDING
    message: str
    working_dir: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    """Response for checking pipeline task status"""
    task_id: str
    pipeline: str
    status: PipelineStatus
    progress: Optional[int] = None
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    output_path: Optional[str] = None


# =============================================================================
# movie
# =============================================================================

class MovieRequest(BaseModel):
    """Generate a full-length movie script (60-200 minutes)"""
    premise: str = Field(..., description="Film premise/logline")
    genre: str = Field("drama", description="Film genre (drama, action, comedy, sci-fi, etc.)")
    target_runtime_minutes: int = Field(90, ge=60, le=200, description="Target runtime in minutes")
    audience: Optional[str] = Field(None, description="Target audience (G, PG, PG-13, R, teens, adults, family)")
    style: str = Field("cinematic", description="Visual/narrative style")
    trendy: bool = Field(False, description="Incorporate trending themes")
    content_format: ContentFormat = Field(ContentFormat.LIVE_ACTION, description="live_action or animated")


class MovieResponse(BaseModel):
    """Movie generation result"""
    run_id: str
    premise: str
    genre: str
    target_runtime_minutes: int
    content_format: str
    story: str
    characters: List[Dict[str, Any]]
    script: Any
    act_breakdown: Dict[str, Any]
    monetization_plan: Dict[str, Any]


# =============================================================================
# tvseries
# =============================================================================

class TVSeriesRequest(BaseModel):
    """Generate a narrative TV series with seasonal arc"""
    premise: Optional[str] = Field(None, description="Series premise/logline")
    genre: str = Field("drama", description="Series genre")
    num_episodes: int = Field(5, description="Number of episodes")
    episode_duration_minutes: int = Field(30, description="Duration per episode")
    audience: Optional[str] = Field(None, description="Target audience")
    style: str = Field("cinematic", description="Visual style")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate series premise")
    ideation_mode: IdeationMode = Field(IdeationMode.CREATIVITY, description="Mode for auto-ideation")
    max_episodes_to_generate: Optional[int] = Field(1, description="Limit episodes to generate visuals for")


class TVSeriesResponse(BaseModel):
    run_id: str
    title: str
    premise: str
    synopsis: str
    episodes: List[Dict[str, Any]]
    monetization_plan: Dict[str, Any]
    working_dir: str


# =============================================================================
# short_movie
# =============================================================================

class ShortMovieRequest(BaseModel):
    """Generate a short film script (5-20 minutes)"""
    premise: str = Field(..., description="Film premise/logline")
    genre: str = Field("drama", description="Film genre")
    target_duration_minutes: int = Field(15, ge=5, le=20, description="Target duration in minutes")
    audience: Optional[str] = Field(None, description="Target audience")
    style: str = Field("cinematic", description="Visual/narrative style")
    trendy: bool = Field(False, description="Incorporate trending themes")
    content_format: ContentFormat = Field(ContentFormat.LIVE_ACTION, description="live_action or animated")


class ShortMovieResponse(BaseModel):
    run_id: str
    premise: str
    genre: str
    target_duration_minutes: int
    content_format: str
    story: str
    characters: List[Dict[str, Any]]
    script: Any
    monetization_plan: Dict[str, Any]


# =============================================================================
# short_video (end-to-end with video generation)
# =============================================================================

class ShortMovieVideoRequest(BaseModel):
    """Generate a complete short film video (5-20 minutes) with storyboards and video"""
    premise: str = Field(..., description="Film premise/logline")
    genre: str = Field("drama", description="Film genre")
    target_duration_minutes: int = Field(15, ge=5, le=20, description="Target duration in minutes")
    audience: Optional[str] = Field(None, description="Target audience")
    style: str = Field("cinematic", description="Visual/narrative style")
    trendy: bool = Field(False, description="Incorporate trending themes")
    content_format: ContentFormat = Field(ContentFormat.ANIMATED, description="live_action or animated")
    generate_storyboard_images: bool = Field(True, description="Generate storyboard frames")
    generate_videos: bool = Field(True, description="Generate video clips for each scene")
    max_scenes: Optional[int] = Field(None, description="Limit scenes to process (for testing)")
    # S3 Entity Integration for character consistency
    brand_id: Optional[str] = Field(None, description="S3 brand ID for character loading (e.g., 'intelli-verse-x')")
    game_id: Optional[str] = Field(None, description="S3 game ID for character loading")
    character_names: Optional[List[str]] = Field(None, description="Specific character names to include from S3")


class ShortMovieVideoResponse(BaseModel):
    run_id: str
    premise: str
    genre: str
    target_duration_minutes: int
    content_format: str
    story: str
    characters: List[Dict[str, Any]]
    script_scenes: List[str]
    scene_outputs: List[Dict[str, Any]]
    final_video_path: Optional[str]
    monetization_plan: Dict[str, Any]
    # S3 Entity info
    is_s3_characters: bool = False
    brand_id: Optional[str] = None
    game_id: Optional[str] = None


# =============================================================================
# lyrics
# =============================================================================

class LyricsRequest(BaseModel):
    """Generate song lyrics from an idea"""
    idea: str = Field(..., description="The song idea or theme")
    user_requirement: str = Field(..., description="Additional requirements for the lyrics")
    style: str = Field(..., description="Style description (e.g., 'upbeat pop', 'melancholic ballad')")
    genre: Optional[str] = Field(None, description="Genre specification")
    mood: Optional[str] = Field(None, description="Mood specification")
    audience: Optional[str] = Field(None, description="Target audience (kids, teens, adults)")
    trendy: bool = Field(False, description="Incorporate trending topics")


class LyricsResponse(BaseModel):
    run_id: str
    idea: str
    style: str
    genre: Optional[str]
    mood: Optional[str]
    lyrics: Dict[str, Any]
    lyrics_path: str
    monetization_plan: Dict[str, Any]


# =============================================================================
# documentary
# =============================================================================

class DocumentaryRequest(BaseModel):
    """Generate documentary content from a topic"""
    topic: Optional[str] = Field(None, description="Documentary topic (optional if auto_ideate=True)")
    target_duration_minutes: int = Field(30, ge=10, le=60, description="Target duration in minutes")
    research_depth: str = Field("moderate", description="Research depth (light, moderate, deep)")
    audience: Optional[str] = Field(None, description="Target audience")
    style: str = Field("informative and engaging", description="Documentary style")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate documentary topic")
    ideation_mode: IdeationMode = Field(IdeationMode.CREATIVITY, description="Mode for auto-ideation")
    brand_hint: Optional[str] = Field(None, description="Brand name hint for brand-mode ideation")
    content_format: ContentFormat = Field(ContentFormat.LIVE_ACTION, description="live_action, animated, or hybrid")


class DocumentaryResponse(BaseModel):
    run_id: str
    topic: str
    target_duration_minutes: int
    content_format: str
    script: Dict[str, Any]
    narration_path: str
    monetization_plan: Dict[str, Any]
    ideation_result: Optional[Dict[str, Any]] = None


# =============================================================================
# ad
# =============================================================================

class AdRequest(BaseModel):
    """Generate advertisement content"""
    brand: Optional[str] = Field(None, description="Brand name (optional if auto_ideate=True)")
    product: Optional[str] = Field(None, description="Product/service being advertised")
    campaign_goal: Optional[str] = Field(None, description="Campaign objective (awareness, conversion, engagement)")
    audience: Optional[str] = Field(None, description="Target audience description")
    ad_format: str = Field("30s", description="Ad duration/format (6s, 15s, 30s, 60s)")
    generate_visuals: bool = Field(True, description="Generate visual frames")
    generate_videos: bool = Field(False, description="Generate video ads")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate ad concept")
    ideation_mode: IdeationMode = Field(IdeationMode.VIRAL, description="Mode for auto-ideation")


class AdResponse(BaseModel):
    run_id: str
    brand: str
    product: str
    campaign_goal: Optional[str]
    ad_format: str
    ad_script: Dict[str, Any]
    variant_visuals: Dict[str, str]
    variant_videos: Dict[str, str]
    monetization_plan: Dict[str, Any]


# =============================================================================
# video
# =============================================================================

class VideoRequest(BaseModel):
    """Generate a video from an idea (standard or shorts)"""
    idea: Optional[str] = Field(None, description="The idea/concept for the video")
    user_requirement: Optional[str] = Field(None, description="Additional requirements")
    style: str = Field("cinematic", description="Visual style for the video")
    audience: Optional[str] = Field(None, description="Target audience")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate the idea")
    ideation_mode: IdeationMode = Field(IdeationMode.CREATIVITY, description="Mode for auto-ideation")
    brand_hint: Optional[str] = Field(None, description="Brand name hint for brand-mode ideation")
    content_format: ContentFormat = Field(ContentFormat.LIVE_ACTION, description="live_action or animated")
    # Shorts mode (configured in YAML, but can override)
    shorts_mode: bool = Field(False, description="Enable shorts mode (vertical, 15-60s)")


class VideoResponse(BaseModel):
    run_id: str
    idea: str
    style: str
    content_format: str
    story: str
    script: Any
    characters: List[Dict[str, Any]]
    video_path: Optional[str] = None
    monetization_plan: Optional[Dict[str, Any]] = None


# =============================================================================
# script2video
# =============================================================================

class Script2VideoRequest(BaseModel):
    """Convert a script to video"""
    script: str = Field(..., description="The script text (scenes)")
    user_requirement: str = Field(..., description="Additional requirements")
    style: str = Field("realistic", description="Visual style")
    audience: Optional[str] = Field(None, description="Target audience")
    trendy: bool = Field(False, description="Incorporate trending content")
    content_format: Optional[ContentFormat] = Field(None, description="live_action or animated")


class Script2VideoResponse(BaseModel):
    run_id: str
    script: str
    style: str
    content_format: Optional[str]
    characters: List[Dict[str, Any]]
    video_path: str
    shots_count: int


# =============================================================================
# song
# =============================================================================

class SongRequest(BaseModel):
    """Generate a complete song (lyrics + audio)"""
    idea: Optional[str] = Field(None, description="Song idea/concept")
    user_requirement: Optional[str] = Field(None, description="Additional requirements")
    style: str = Field("pop", description="Music style")
    audience: Optional[str] = Field(None, description="Target audience")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate the idea")
    ideation_mode: IdeationMode = Field(IdeationMode.CREATIVITY, description="Mode for auto-ideation")
    brand_hint: Optional[str] = Field(None, description="Brand name hint for brand-mode ideation")


class SongResponse(BaseModel):
    run_id: str
    idea: str
    style: str
    lyrics: Dict[str, Any]
    audio_path: Optional[str] = None
    cover_path: Optional[str] = None
    monetization_plan: Optional[Dict[str, Any]] = None


# =============================================================================
# song2musicvideo
# =============================================================================

class Song2MusicVideoRequest(BaseModel):
    """Generate music video concept from song data"""
    song_title: str = Field(..., description="Title of the song")
    lyrics: str = Field(..., description="Song lyrics")
    genre: str = Field(..., description="Music genre")
    mood: str = Field(..., description="Song mood")
    song_structure: Optional[str] = Field(None, description="Song structure (verse-chorus-verse, etc.)")
    style: str = Field("cinematic", description="Visual style preference")
    audience: Optional[str] = Field(None, description="Target audience")
    generate_storyboard_images: bool = Field(True, description="Generate storyboard frames")
    trendy: bool = Field(False, description="Incorporate trending visual styles")
    kids_mode: bool = Field(False, description="G-rated kids animated music video")


class Song2MusicVideoResponse(BaseModel):
    run_id: str
    song_title: str
    genre: str
    mood: str
    kids_mode: bool
    concept: Dict[str, Any]
    storyboard_images: Dict[str, str]
    monetization_plan: Dict[str, Any]


# =============================================================================
# kids_movie
# =============================================================================

class KidsMovieRequest(BaseModel):
    """Generate kids animated movie content"""
    story_idea: Optional[str] = Field(None, description="Story concept (optional if auto_ideate=True)")
    age_group: str = Field("6-8", description="Target age group (3-5, 6-8, 9-12)")
    characters: Optional[str] = Field(None, description="Character descriptions")
    moral_lesson: Optional[str] = Field(None, description="Moral/lesson to teach")
    target_duration_minutes: int = Field(15, description="Target duration")
    style: str = Field("colorful 3D animation", description="Animation style")
    audience: Optional[str] = Field(None, description="Additional audience description")
    generate_character_art: bool = Field(True, description="Generate character designs")
    trendy: bool = Field(False, description="Incorporate trending kids content themes")
    auto_ideate: bool = Field(False, description="Auto-generate story idea")
    ideation_mode: IdeationMode = Field(IdeationMode.CREATIVITY, description="Mode for auto-ideation")
    brand_hint: Optional[str] = Field(None, description="Brand name hint for brand-mode ideation")


class KidsMovieResponse(BaseModel):
    run_id: str
    story_idea: str
    age_group: str
    moral_lesson: Optional[str]
    script: Dict[str, Any]
    characters: List[Dict[str, Any]]
    character_art: Dict[str, str]
    monetization_plan: Dict[str, Any]


# =============================================================================
# learning_series
# =============================================================================

class LearningSeriesRequest(BaseModel):
    """Generate educational video series with curriculum"""
    topic: str = Field(..., description="Course topic")
    num_episodes: int = Field(5, ge=1, le=20, description="Number of episodes")
    episode_duration_minutes: int = Field(10, ge=5, le=30, description="Duration per episode")
    audience: Optional[str] = Field(None, description="Target audience")
    skill_level: str = Field("beginner", description="Skill level (beginner, intermediate, advanced)")
    learning_goals: Optional[str] = Field(None, description="Learning objectives")
    trendy: bool = Field(False, description="Incorporate trending topics")
    generate_images: bool = Field(True, description="Generate visual content")
    generate_videos: bool = Field(True, description="Generate video content")
    visual_style: str = Field("professional educational, clean, modern", description="Visual style")
    max_episodes_to_generate: Optional[int] = Field(None, description="Limit episodes to generate (for testing)")
    # S3 Entity Integration
    brand_id: Optional[str] = Field(None, description="S3 brand id for character integration")
    game_id: Optional[str] = Field(None, description="S3 game id for character integration")
    character_names: Optional[List[str]] = Field(None, description="Character names to include")
    featured_character: Optional[str] = Field(None, description="Main character for the series")


class LearningSeriesResponse(BaseModel):
    run_id: str
    topic: str
    num_episodes: int
    skill_level: str
    curriculum: Dict[str, Any]
    episodes: List[Dict[str, Any]]
    monetization_plan: Dict[str, Any]
    output_path: str


# =============================================================================
# adbanners
# =============================================================================

class AdBannersRequest(BaseModel):
    """Generate high-converting ad banner images"""
    brand_or_game: str = Field(..., description="Brand or game name")
    entity_type: Literal["brand", "game"] = Field("brand", description="Entity type")
    brief: str = Field("", description="Campaign/banner brief")
    audience: str = Field("General mobile and desktop users, 18-44", description="Target audience")
    campaign_goal: str = Field("Conversions and installs", description="Campaign objective")
    platforms: str = Field("Google Display, Meta (Facebook/Instagram), programmatic", description="Ad platforms")
    trendy: bool = Field(False, description="Use trend analyzer for trend-based concepts")
    brand_id: Optional[str] = Field(None, description="S3 brand id")
    game_id: Optional[str] = Field(None, description="S3 game id")
    num_concepts: int = Field(5, ge=3, le=10, description="Number of concepts")
    sizes: Optional[List[str]] = Field(None, description="Subset of ad sizes; None = all standard sizes")


class AdBannersResponse(BaseModel):
    run_id: str
    entity_name: str
    entity_type: str
    num_concepts: int
    concepts: List[Dict[str, Any]]
    banners: Dict[str, Dict[str, str]]  # concept -> size -> path
    output_path: str


# =============================================================================
# podcast2video
# =============================================================================

class Podcast2VideoRequest(BaseModel):
    """Convert podcast script to video"""
    script_text: Optional[str] = Field(None, description="Podcast script text (if not using script_path)")
    script_path: Optional[str] = Field(None, description="Path to podcast script file (PDF or TXT)")
    max_scenes: Optional[int] = Field(None, description="Maximum scenes to process (for testing)")
    audience: Optional[str] = Field(None, description="Target audience")
    trendy: bool = Field(False, description="Incorporate trending topics")
    auto_ideate: bool = Field(False, description="Auto-generate podcast episode idea")
    ideation_mode: IdeationMode = Field(IdeationMode.PODCAST, description="Mode for auto-ideation")
    topic_area: Optional[str] = Field(None, description="Topic area for podcast ideation")
    brand_id: str = Field("intelli-verse-x", description="Brand ID for characters")


class Podcast2VideoResponse(BaseModel):
    run_id: str
    title: str
    scenes_count: int
    video_path: str
    parsed_podcast: Dict[str, Any]
    monetization_plan: Optional[Dict[str, Any]] = None
