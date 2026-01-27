"""
Pydantic models for the Brand/Game/Character API
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class AssetType(str, Enum):
    BRAND = "brand"
    GAME = "game"
    CHARACTER = "character"


# ============== Character Models ==============

class CharacterMedia(BaseModel):
    """Character media assets - flexible structure"""
    model_config = {"extra": "allow"}
    
    portraits: Optional[Dict[str, Any]] = None
    voice: Optional[Dict[str, Any]] = None


class CharacterCreate(BaseModel):
    name: str = Field(..., description="Character name")
    identifier_in_scene: str = Field(..., description="Identifier used in scenes/scripts")
    static_features: str = Field(..., description="Permanent character traits and appearance")
    dynamic_features: Optional[str] = Field("None", description="Changeable traits")
    backstory: Optional[str] = Field(None, description="Character's background story")
    personality: Optional[str] = Field(None, description="Personality traits")
    role: Optional[str] = Field(None, description="Role in the brand/game")


class CharacterResponse(BaseModel):
    """Character response model following S3 pattern"""
    model_config = {"extra": "allow"}
    
    id: str
    name: str
    identifier_in_scene: str
    is_visible: bool = True
    static_features: str = ""
    dynamic_features: str = "None"
    description: Optional[str] = None
    appearance: Optional[str] = None
    backstory: Optional[str] = None
    personality: Optional[str] = None
    role: Optional[str] = None
    media: Optional[CharacterMedia] = None
    public_urls: Optional[Dict[str, str]] = None
    aliases: Optional[List[str]] = None  # For backward compatibility (C1 -> AUTOcurio)


class CharacterGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Describe the character you want to create")
    style: Optional[str] = Field("3D animated cartoon", description="Visual style")
    generate_images: bool = Field(True, description="Auto-generate character portraits")
    generate_voice: bool = Field(True, description="Auto-generate voice sample")


# ============== Brand Models ==============

class BrandCreate(BaseModel):
    name: str = Field(..., description="Brand name")
    description: str = Field(..., description="Brand description")
    tagline: Optional[str] = Field(None, description="Brand tagline/slogan")
    story: Optional[str] = Field(None, description="Brand story and origin")
    values: Optional[List[str]] = Field(None, description="Core brand values")
    target_audience: Optional[str] = Field(None, description="Target audience description")
    visual_style: Optional[str] = Field(None, description="Visual/artistic style")


class BrandResponse(BaseModel):
    id: str
    name: str
    description: str
    tagline: Optional[str] = None
    story: Optional[str] = None
    values: Optional[List[str]] = None
    target_audience: Optional[str] = None
    visual_style: Optional[str] = None
    media: Optional[Dict[str, Any]] = None
    characters: List[str] = []
    public_url: Optional[str] = None


class BrandGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Describe the brand concept you want to create")
    industry: Optional[str] = Field(None, description="Industry/niche (e.g., 'gaming', 'education', 'health')")
    style: Optional[str] = Field(None, description="Visual/brand style preference")
    generate_logo: bool = Field(True, description="Auto-generate brand logo")
    num_characters: int = Field(3, description="Number of characters to auto-generate")


# ============== Game Models ==============

class GameCreate(BaseModel):
    name: str = Field(..., description="Game name")
    description: str = Field(..., description="Game description")
    genre: Optional[str] = Field(None, description="Game genre")
    brand_id: Optional[str] = Field(None, description="Parent brand ID")
    platforms: Optional[List[str]] = Field(None, description="Target platforms")
    story: Optional[str] = Field(None, description="Game story/narrative")
    mechanics: Optional[str] = Field(None, description="Core game mechanics")
    target_audience: Optional[str] = Field(None, description="Target audience")


class GameResponse(BaseModel):
    id: str
    name: str
    description: str
    genre: Optional[str] = None
    brand: Optional[str] = None
    platforms: Optional[List[str]] = None
    story: Optional[str] = None
    mechanics: Optional[str] = None
    target_audience: Optional[str] = None
    media: Optional[Dict[str, Any]] = None
    characters: List[str] = []
    public_url: Optional[str] = None


class GameGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Describe the game concept you want to create")
    genre: Optional[str] = Field(None, description="Game genre preference")
    brand_id: Optional[str] = Field(None, description="Parent brand ID (optional)")
    platforms: Optional[List[str]] = Field(["mobile"], description="Target platforms")
    generate_icon: bool = Field(True, description="Auto-generate game icon")
    num_characters: int = Field(4, description="Number of characters to auto-generate")


# ============== Generation Response Models ==============

class GenerationTaskResponse(BaseModel):
    task_id: str
    status: str
    asset_type: AssetType
    asset_id: Optional[str] = None
    message: str


class GenerationStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
