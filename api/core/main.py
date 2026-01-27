"""
ViMax Brand & Game Management API

REST API for creating and managing brands, games, and characters
with AI-powered generation capabilities.
"""
import asyncio
import os
import uuid
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware

# Thread pool for running async tasks in background
executor = ThreadPoolExecutor(max_workers=4)


def run_async_task(coro):
    """Run an async coroutine in a new event loop (for background tasks)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

from api.models.models import (
    BrandCreate, BrandResponse, BrandGenerateRequest,
    GameCreate, GameResponse, GameGenerateRequest,
    CharacterCreate, CharacterResponse, CharacterGenerateRequest,
    GenerationTaskResponse, GenerationStatusResponse,
    AssetType
)
from api.routes.pipelines import router as pipeline_router
from api.core.generators import (
    GeneratorConfig, ConceptGenerator, MediaGenerator, S3Storage
)


# ============== Background Task Storage ==============
generation_tasks: Dict[str, Dict] = {}


# ============== App Lifespan ==============
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.config = GeneratorConfig.from_env()
    app.state.concept_gen = ConceptGenerator(app.state.config)
    app.state.media_gen = MediaGenerator(app.state.config)
    app.state.storage = S3Storage(app.state.config)
    yield
    # Shutdown
    pass


# ============== FastAPI App ==============
app = FastAPI(
    title="ViMax API",
    description="""
    Complete API for ViMax content generation platform.
    
    ## Brand & Game Management
    - **Brands**: Create brand concepts with stories, values, and characters
    - **Games**: Design game concepts with narratives and character rosters
    - **Characters**: Generate detailed characters with portraits and voices
    - **AI Generation**: Use prompts to auto-generate complete concepts
    
    ## Pipeline API (`/pipelines/*`)
    Generate content using ViMax pipelines:
    - **Movies**: Full-length (60-200 min) and short films (5-20 min)
    - **Videos**: Standard videos and YouTube Shorts from ideas or scripts
    - **Music**: Lyrics, songs, and music video concepts
    - **Ads**: Ad scripts, visuals, videos, and banner images
    - **Educational**: Documentaries and learning series
    - **Kids**: Age-appropriate animated content
    - **Podcasts**: Convert podcast scripts to video
    
    All pipelines run as background tasks. Use `GET /pipelines/tasks/{task_id}` to check status.
    """,
    version="1.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Pipeline API routes
app.include_router(pipeline_router)


# ============== Helper Functions ==============

def slugify(name: str) -> str:
    """Convert name to URL-safe slug"""
    return name.lower().replace(" ", "-").replace("'", "").replace('"', "")


def get_character_folder_name(char_concept: Dict, char_id: str) -> str:
    """Determine the folder name for a character
    
    Prefers actual character name over generic IDs (C1, C2, etc.)
    This ensures consistency with the established S3 pattern.
    """
    # Prefer identifier_in_scene, then name, then fallback to char_id
    name = char_concept.get("identifier_in_scene") or char_concept.get("name")
    if name:
        # Convert to folder-safe name (remove spaces, special chars)
        folder_name = name.replace(" ", "")
        # Capitalize first letter of each word for consistency
        return folder_name
    return char_id


async def generate_full_character(
    task_id: str,
    char_concept: Dict,
    parent_type: str,
    parent_id: str,
    char_id: str,
    config: GeneratorConfig,
    generate_images: bool = True,
    generate_voice: bool = True
):
    """Background task to generate a complete character with media
    
    S3 Pattern:
        {parent_type}/{parent_id}/Characters/{CharacterName}/
            character.json
            front.png
            side.png
            back.png
            voice.m4a
    
    The character.json contains:
        - id, name, identifier_in_scene
        - static_features, dynamic_features
        - public_urls with both 'front' and 'portrait_front' keys
    """
    try:
        generation_tasks[task_id]["status"] = "processing"
        generation_tasks[task_id]["progress"] = 10
        
        media_gen = MediaGenerator(config)
        storage = S3Storage(config)
        
        # Determine character folder name (use actual name, not just C1, C2)
        char_folder = get_character_folder_name(char_concept, char_id)
        char_name = char_concept.get("name", char_folder)
        identifier = char_concept.get("identifier_in_scene", char_folder)
        
        # Build character data following established pattern
        char_data = {
            "id": char_folder,
            "name": char_name,
            "identifier_in_scene": identifier,
            "is_visible": True,
            "role": char_concept.get("role", "character"),
            "description": char_concept.get("backstory", ""),
            "appearance": char_concept.get("appearance", {}).get("overview", "") if isinstance(char_concept.get("appearance"), dict) else str(char_concept.get("appearance", "")),
            "personality": char_concept.get("personality", ""),
            "static_features": char_concept.get("static_features", char_concept.get("appearance", {}).get("overview", "") if isinstance(char_concept.get("appearance"), dict) else ""),
            "dynamic_features": char_concept.get("dynamic_features", "None"),
            "backstory": char_concept.get("backstory"),
            "media": {
                "portraits": {"front": "front.png", "side": "side.png", "back": "back.png"},
                "voice": None
            },
            "public_urls": {},
            "aliases": [char_id] if char_id != char_folder else []  # Keep legacy ID as alias
        }
        
        s3_key = f"{parent_type}/{parent_id}/Characters/{char_folder}"
        
        # Generate front portrait
        if generate_images:
            generation_tasks[task_id]["progress"] = 20
            generation_tasks[task_id]["message"] = f"Generating front portrait for {char_name}..."
            
            appearance = char_concept.get("appearance", {})
            if isinstance(appearance, dict):
                desc = appearance.get("overview", char_concept.get("static_features", ""))
            else:
                desc = char_concept.get("static_features", str(appearance))
            
            front_url = await media_gen.generate_character_portrait(desc)
            if front_url:
                # Use front.png as the standard name (not character.png)
                s3_url = await storage.download_and_upload(front_url, s3_key, "front.png")
                if s3_url:
                    # Add both URL formats for compatibility
                    char_data["public_urls"]["front"] = s3_url
                    char_data["public_urls"]["portrait_front"] = s3_url
                    
                    # Generate side portrait
                    generation_tasks[task_id]["progress"] = 40
                    generation_tasks[task_id]["message"] = f"Generating side portrait for {char_name}..."
                    
                    side_url = await media_gen.generate_side_portrait(s3_url, char_name)
                    if side_url:
                        side_s3_url = await storage.download_and_upload(side_url, s3_key, "side.png")
                        if side_s3_url:
                            char_data["public_urls"]["side"] = side_s3_url
                            char_data["public_urls"]["portrait_side"] = side_s3_url
                    
                    # Generate back portrait
                    generation_tasks[task_id]["progress"] = 60
                    generation_tasks[task_id]["message"] = f"Generating back portrait for {char_name}..."
                    
                    back_url = await media_gen.generate_back_portrait(s3_url, char_name)
                    if back_url:
                        back_s3_url = await storage.download_and_upload(back_url, s3_key, "back.png")
                        if back_s3_url:
                            char_data["public_urls"]["back"] = back_s3_url
                            char_data["public_urls"]["portrait_back"] = back_s3_url
        
        # Generate voice sample
        if generate_voice:
            generation_tasks[task_id]["progress"] = 80
            generation_tasks[task_id]["message"] = f"Generating voice sample for {char_name}..."
            
            voice_text = f"Hello, I am {char_name}. {char_concept.get('personality', 'Nice to meet you!')}"
            voice_url = await media_gen.generate_voice_sample(voice_text)
            if voice_url:
                voice_s3_url = await storage.download_and_upload(voice_url, s3_key, "voice.m4a")
                if voice_s3_url:
                    char_data["media"]["voice"] = {
                        "sample": "voice.m4a",
                        "format": "m4a"
                    }
                    char_data["public_urls"]["voice"] = voice_s3_url
        
        # Save character.json
        generation_tasks[task_id]["progress"] = 90
        generation_tasks[task_id]["message"] = "Saving character data..."
        
        await storage.save_json(s3_key, "character.json", char_data)
        
        # Update the characters_mapping.json for alias support
        generation_tasks[task_id]["progress"] = 95
        await storage.update_characters_mapping(
            parent_type, parent_id, char_id, char_folder, 
            char_data.get("aliases", [])
        )
        
        # Update the brand/game's characters list
        await storage.update_asset_characters_list(parent_type, parent_id, char_folder)
        
        generation_tasks[task_id]["status"] = "completed"
        generation_tasks[task_id]["progress"] = 100
        generation_tasks[task_id]["result"] = char_data
        generation_tasks[task_id]["asset_id"] = char_folder
        generation_tasks[task_id]["message"] = f"Character {char_name} created successfully!"
        
    except Exception as e:
        generation_tasks[task_id]["status"] = "failed"
        generation_tasks[task_id]["error"] = str(e)
        import traceback
        generation_tasks[task_id]["traceback"] = traceback.format_exc()


# ============== Health Check ==============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "vimax-api"}


# ============== Brand Endpoints ==============

@app.get("/brands", response_model=List[str])
async def list_brands():
    """List all brands"""
    storage: S3Storage = app.state.storage
    return storage.list_items("brands")


@app.get("/brands/{brand_id}", response_model=BrandResponse)
async def get_brand(brand_id: str):
    """Get brand details"""
    storage: S3Storage = app.state.storage
    data = await storage.load_json(f"brands/{brand_id}", "brand.json")
    if not data:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # Get characters
    characters = storage.list_items(f"brands/{brand_id}/Characters")
    data["characters"] = characters
    data["public_url"] = f"https://{storage.bucket}.s3.amazonaws.com/{storage.prefix}/brands/{brand_id}/"
    
    return BrandResponse(**data)


@app.post("/brands", response_model=BrandResponse)
async def create_brand(brand: BrandCreate):
    """Create a new brand manually"""
    storage: S3Storage = app.state.storage
    brand_id = slugify(brand.name)
    
    brand_data = {
        "id": brand_id,
        **brand.model_dump(),
        "media": {"logo": {"primary": "Logo.png", "variants": {}}},
        "characters": []
    }
    
    await storage.save_json(f"brands/{brand_id}", "brand.json", brand_data)
    
    brand_data["public_url"] = f"https://{storage.bucket}.s3.amazonaws.com/{storage.prefix}/brands/{brand_id}/"
    return BrandResponse(**brand_data)


@app.post("/brands/generate", response_model=GenerationTaskResponse)
async def generate_brand(
    request: BrandGenerateRequest,
    background_tasks: BackgroundTasks
):
    """Generate a complete brand from a prompt using AI"""
    task_id = str(uuid.uuid4())
    
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "brand",
        "message": "Starting brand generation..."
    }
    
    async def generate_brand_task():
        try:
            config = app.state.config
            concept_gen: ConceptGenerator = app.state.concept_gen
            media_gen: MediaGenerator = app.state.media_gen
            storage: S3Storage = app.state.storage
            
            generation_tasks[task_id]["status"] = "processing"
            generation_tasks[task_id]["progress"] = 10
            generation_tasks[task_id]["message"] = "Generating brand concept..."
            
            # Generate concept
            concept = await concept_gen.generate_brand_concept(
                request.prompt,
                request.industry,
                request.style
            )
            
            brand_id = slugify(concept["name"])
            generation_tasks[task_id]["asset_id"] = brand_id
            generation_tasks[task_id]["progress"] = 30
            
            # Generate logo if requested
            if request.generate_logo:
                generation_tasks[task_id]["message"] = "Generating logo..."
                logo_url = await media_gen.generate_logo(
                    concept["name"],
                    concept["description"],
                    concept.get("visual_style", "modern")
                )
                if logo_url:
                    await storage.download_and_upload(logo_url, f"brands/{brand_id}", "Logo.png")
            
            generation_tasks[task_id]["progress"] = 50
            
            # Build brand data
            brand_data = {
                "id": brand_id,
                "name": concept["name"],
                "description": concept["description"],
                "tagline": concept.get("tagline"),
                "story": concept.get("story"),
                "values": concept.get("values", []),
                "target_audience": concept.get("target_audience"),
                "visual_style": concept.get("visual_style"),
                "color_palette": concept.get("color_palette", []),
                "personality_traits": concept.get("personality_traits", []),
                "media": {"logo": {"primary": "Logo.png", "variants": {}}},
                "characters": []
            }
            
            await storage.save_json(f"brands/{brand_id}", "brand.json", brand_data)
            
            # Generate characters
            suggested_chars = concept.get("suggested_characters", [])[:request.num_characters]
            
            for i, char_info in enumerate(suggested_chars):
                generation_tasks[task_id]["progress"] = 50 + (i * 40 // len(suggested_chars)) if suggested_chars else 90
                generation_tasks[task_id]["message"] = f"Creating character {i+1}/{len(suggested_chars)}..."
                
                char_id = f"C{i+1}"
                char_concept = {
                    "name": char_info.get("name", f"Character {i+1}"),
                    "identifier_in_scene": slugify(char_info.get("name", f"char{i+1}")),
                    "role": char_info.get("role"),
                    "personality": char_info.get("personality"),
                    "appearance": {"overview": char_info.get("appearance", "")},
                    "static_features": char_info.get("appearance", ""),
                    "backstory": char_info.get("backstory", "")
                }
                
                # Generate character with media
                char_task_id = str(uuid.uuid4())
                generation_tasks[char_task_id] = {"status": "pending", "progress": 0}
                
                await generate_full_character(
                    char_task_id,
                    char_concept,
                    "brands",
                    brand_id,
                    char_id,
                    config,
                    generate_images=True,
                    generate_voice=True
                )
                
                brand_data["characters"].append(char_id)
            
            # Update brand.json with characters
            await storage.save_json(f"brands/{brand_id}", "brand.json", brand_data)
            
            generation_tasks[task_id]["status"] = "completed"
            generation_tasks[task_id]["progress"] = 100
            generation_tasks[task_id]["result"] = brand_data
            generation_tasks[task_id]["message"] = "Brand generation complete!"
            
        except Exception as e:
            generation_tasks[task_id]["status"] = "failed"
            generation_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, generate_brand_task())
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.BRAND,
        message="Brand generation started"
    )


# ============== Game Endpoints ==============

@app.get("/games", response_model=List[str])
async def list_games():
    """List all games"""
    storage: S3Storage = app.state.storage
    return storage.list_items("games")


@app.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game_id: str):
    """Get game details"""
    storage: S3Storage = app.state.storage
    data = await storage.load_json(f"games/{game_id}", "game.json")
    if not data:
        raise HTTPException(status_code=404, detail="Game not found")
    
    characters = storage.list_items(f"games/{game_id}/Characters")
    data["characters"] = characters
    data["public_url"] = f"https://{storage.bucket}.s3.amazonaws.com/{storage.prefix}/games/{game_id}/"
    
    return GameResponse(**data)


@app.post("/games", response_model=GameResponse)
async def create_game(game: GameCreate):
    """Create a new game manually"""
    storage: S3Storage = app.state.storage
    game_id = slugify(game.name)
    
    game_data = {
        "id": game_id,
        **game.model_dump(),
        "brand": game.brand_id,
        "media": {"icon": {"primary": "icon.png", "variants": {}}},
        "characters": []
    }
    
    await storage.save_json(f"games/{game_id}", "game.json", game_data)
    
    game_data["public_url"] = f"https://{storage.bucket}.s3.amazonaws.com/{storage.prefix}/games/{game_id}/"
    return GameResponse(**game_data)


@app.post("/games/generate", response_model=GenerationTaskResponse)
async def generate_game(
    request: GameGenerateRequest,
    background_tasks: BackgroundTasks
):
    """Generate a complete game concept from a prompt using AI"""
    task_id = str(uuid.uuid4())
    
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "game",
        "message": "Starting game generation..."
    }
    
    async def generate_game_task():
        try:
            config = app.state.config
            concept_gen: ConceptGenerator = app.state.concept_gen
            media_gen: MediaGenerator = app.state.media_gen
            storage: S3Storage = app.state.storage
            
            generation_tasks[task_id]["status"] = "processing"
            generation_tasks[task_id]["progress"] = 10
            generation_tasks[task_id]["message"] = "Generating game concept..."
            
            # Get brand context if provided
            brand_context = None
            if request.brand_id:
                brand_data = await storage.load_json(f"brands/{request.brand_id}", "brand.json")
                if brand_data:
                    brand_context = f"Brand: {brand_data['name']} - {brand_data['description']}"
            
            # Generate concept
            concept = await concept_gen.generate_game_concept(
                request.prompt,
                request.genre,
                request.platforms,
                brand_context
            )
            
            game_id = slugify(concept["name"])
            generation_tasks[task_id]["asset_id"] = game_id
            generation_tasks[task_id]["progress"] = 30
            
            # Generate icon if requested
            if request.generate_icon:
                generation_tasks[task_id]["message"] = "Generating game icon..."
                icon_url = await media_gen.generate_logo(
                    concept["name"],
                    concept["description"],
                    concept.get("visual_style", "game icon")
                )
                if icon_url:
                    await storage.download_and_upload(icon_url, f"games/{game_id}", "icon.png")
            
            generation_tasks[task_id]["progress"] = 50
            
            # Build game data
            game_data = {
                "id": game_id,
                "name": concept["name"],
                "description": concept["description"],
                "genre": concept.get("genre"),
                "brand": request.brand_id,
                "platforms": request.platforms,
                "story": concept.get("story"),
                "mechanics": concept.get("mechanics"),
                "target_audience": concept.get("target_audience"),
                "unique_features": concept.get("unique_features", []),
                "visual_style": concept.get("visual_style"),
                "media": {"icon": {"primary": "icon.png", "variants": {}}},
                "characters": []
            }
            
            await storage.save_json(f"games/{game_id}", "game.json", game_data)
            
            # Generate characters
            suggested_chars = concept.get("suggested_characters", [])[:request.num_characters]
            
            for i, char_info in enumerate(suggested_chars):
                generation_tasks[task_id]["progress"] = 50 + (i * 40 // len(suggested_chars)) if suggested_chars else 90
                generation_tasks[task_id]["message"] = f"Creating character {i+1}/{len(suggested_chars)}..."
                
                char_id = f"C{i+1}"
                char_concept = {
                    "name": char_info.get("name", f"Character {i+1}"),
                    "identifier_in_scene": slugify(char_info.get("name", f"char{i+1}")),
                    "role": char_info.get("role"),
                    "personality": char_info.get("personality"),
                    "appearance": {"overview": char_info.get("appearance", "")},
                    "static_features": char_info.get("appearance", ""),
                    "backstory": char_info.get("backstory", ""),
                }
                
                char_task_id = str(uuid.uuid4())
                generation_tasks[char_task_id] = {"status": "pending", "progress": 0}
                
                await generate_full_character(
                    char_task_id,
                    char_concept,
                    "games",
                    game_id,
                    char_id,
                    config,
                    generate_images=True,
                    generate_voice=True
                )
                
                game_data["characters"].append(char_id)
            
            await storage.save_json(f"games/{game_id}", "game.json", game_data)
            
            generation_tasks[task_id]["status"] = "completed"
            generation_tasks[task_id]["progress"] = 100
            generation_tasks[task_id]["result"] = game_data
            generation_tasks[task_id]["message"] = "Game generation complete!"
            
        except Exception as e:
            generation_tasks[task_id]["status"] = "failed"
            generation_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, generate_game_task())
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.GAME,
        message="Game generation started"
    )


# ============== Character Endpoints ==============

@app.get("/brands/{brand_id}/characters", response_model=List[str])
async def list_brand_characters(brand_id: str):
    """List characters for a brand"""
    storage: S3Storage = app.state.storage
    return storage.list_items(f"brands/{brand_id}/Characters")


@app.get("/games/{game_id}/characters", response_model=List[str])
async def list_game_characters(game_id: str):
    """List characters for a game"""
    storage: S3Storage = app.state.storage
    return storage.list_items(f"games/{game_id}/Characters")


@app.get("/brands/{brand_id}/characters/{char_id}", response_model=CharacterResponse)
async def get_brand_character(brand_id: str, char_id: str):
    """Get character details from a brand"""
    storage: S3Storage = app.state.storage
    data = await storage.load_json(f"brands/{brand_id}/Characters/{char_id}", "character.json")
    if not data:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterResponse(**data)


@app.get("/games/{game_id}/characters/{char_id}", response_model=CharacterResponse)
async def get_game_character(game_id: str, char_id: str):
    """Get character details from a game"""
    storage: S3Storage = app.state.storage
    data = await storage.load_json(f"games/{game_id}/Characters/{char_id}", "character.json")
    if not data:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterResponse(**data)


@app.post("/brands/{brand_id}/characters", response_model=GenerationTaskResponse)
async def add_brand_character(
    brand_id: str,
    character: CharacterCreate,
    background_tasks: BackgroundTasks,
    generate_images: bool = Query(True, description="Auto-generate portraits"),
    generate_voice: bool = Query(True, description="Auto-generate voice sample")
):
    """Add a character to a brand"""
    storage: S3Storage = app.state.storage
    
    # Check brand exists
    brand_data = await storage.load_json(f"brands/{brand_id}", "brand.json")
    if not brand_data:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # Determine next character ID
    existing = storage.list_items(f"brands/{brand_id}/Characters")
    char_num = len(existing) + 1
    char_id = f"C{char_num}"
    
    task_id = str(uuid.uuid4())
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "character",
        "asset_id": char_id,
        "message": "Starting character creation..."
    }
    
    char_concept = {
        "name": character.name,
        "identifier_in_scene": character.identifier_in_scene,
        "role": character.role,
        "personality": character.personality,
        "static_features": character.static_features,
        "dynamic_features": character.dynamic_features,
        "backstory": character.backstory,
        "appearance": {"overview": character.static_features}
    }
    
    background_tasks.add_task(
        generate_full_character,
        task_id,
        char_concept,
        "brands",
        brand_id,
        char_id,
        app.state.config,
        generate_images,
        generate_voice
    )
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.CHARACTER,
        asset_id=char_id,
        message="Character creation started"
    )


@app.post("/games/{game_id}/characters", response_model=GenerationTaskResponse)
async def add_game_character(
    game_id: str,
    character: CharacterCreate,
    background_tasks: BackgroundTasks,
    generate_images: bool = Query(True, description="Auto-generate portraits"),
    generate_voice: bool = Query(True, description="Auto-generate voice sample")
):
    """Add a character to a game"""
    storage: S3Storage = app.state.storage
    
    # Check game exists
    game_data = await storage.load_json(f"games/{game_id}", "game.json")
    if not game_data:
        raise HTTPException(status_code=404, detail="Game not found")
    
    existing = storage.list_items(f"games/{game_id}/Characters")
    char_num = len(existing) + 1
    char_id = f"C{char_num}"
    
    task_id = str(uuid.uuid4())
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "character",
        "asset_id": char_id,
        "message": "Starting character creation..."
    }
    
    char_concept = {
        "name": character.name,
        "identifier_in_scene": character.identifier_in_scene,
        "role": character.role,
        "personality": character.personality,
        "static_features": character.static_features,
        "dynamic_features": character.dynamic_features,
        "backstory": character.backstory,
        "appearance": {"overview": character.static_features}
    }
    
    background_tasks.add_task(
        generate_full_character,
        task_id,
        char_concept,
        "games",
        game_id,
        char_id,
        app.state.config,
        generate_images,
        generate_voice
    )
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.CHARACTER,
        asset_id=char_id,
        message="Character creation started"
    )


@app.post("/brands/{brand_id}/characters/generate", response_model=GenerationTaskResponse)
async def generate_brand_character(
    brand_id: str,
    request: CharacterGenerateRequest,
    background_tasks: BackgroundTasks
):
    """Generate a character from a prompt and add to brand"""
    storage: S3Storage = app.state.storage
    
    brand_data = await storage.load_json(f"brands/{brand_id}", "brand.json")
    if not brand_data:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    existing = storage.list_items(f"brands/{brand_id}/Characters")
    char_num = len(existing) + 1
    char_id = f"C{char_num}"
    
    task_id = str(uuid.uuid4())
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "character",
        "asset_id": char_id,
        "message": "Starting AI character generation..."
    }
    
    async def generate_task():
        try:
            concept_gen: ConceptGenerator = app.state.concept_gen
            
            generation_tasks[task_id]["status"] = "processing"
            generation_tasks[task_id]["progress"] = 10
            generation_tasks[task_id]["message"] = "Generating character concept..."
            
            # Generate concept
            context = f"Brand: {brand_data['name']} - {brand_data.get('description', '')}"
            char_concept = await concept_gen.generate_character_concept(
                request.prompt,
                request.style,
                context
            )
            
            generation_tasks[task_id]["progress"] = 30
            
            # Generate full character with media
            await generate_full_character(
                task_id,
                char_concept,
                "brands",
                brand_id,
                char_id,
                app.state.config,
                request.generate_images,
                request.generate_voice
            )
            
        except Exception as e:
            generation_tasks[task_id]["status"] = "failed"
            generation_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, generate_task())
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.CHARACTER,
        asset_id=char_id,
        message="AI character generation started"
    )


@app.post("/games/{game_id}/characters/generate", response_model=GenerationTaskResponse)
async def generate_game_character(
    game_id: str,
    request: CharacterGenerateRequest,
    background_tasks: BackgroundTasks
):
    """Generate a character from a prompt and add to game"""
    storage: S3Storage = app.state.storage
    
    game_data = await storage.load_json(f"games/{game_id}", "game.json")
    if not game_data:
        raise HTTPException(status_code=404, detail="Game not found")
    
    existing = storage.list_items(f"games/{game_id}/Characters")
    char_num = len(existing) + 1
    char_id = f"C{char_num}"
    
    task_id = str(uuid.uuid4())
    generation_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "asset_type": "character",
        "asset_id": char_id,
        "message": "Starting AI character generation..."
    }
    
    async def generate_task():
        try:
            concept_gen: ConceptGenerator = app.state.concept_gen
            
            generation_tasks[task_id]["status"] = "processing"
            generation_tasks[task_id]["progress"] = 10
            generation_tasks[task_id]["message"] = "Generating character concept..."
            
            context = f"Game: {game_data['name']} - {game_data.get('description', '')}"
            char_concept = await concept_gen.generate_character_concept(
                request.prompt,
                request.style,
                context
            )
            
            generation_tasks[task_id]["progress"] = 30
            
            await generate_full_character(
                task_id,
                char_concept,
                "games",
                game_id,
                char_id,
                app.state.config,
                request.generate_images,
                request.generate_voice
            )
            
        except Exception as e:
            generation_tasks[task_id]["status"] = "failed"
            generation_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_async_task, generate_task())
    
    return GenerationTaskResponse(
        task_id=task_id,
        status="pending",
        asset_type=AssetType.CHARACTER,
        asset_id=char_id,
        message="AI character generation started"
    )


# ============== Task Status Endpoint ==============

@app.get("/tasks/{task_id}", response_model=GenerationStatusResponse)
async def get_task_status(task_id: str):
    """Get the status of a generation task"""
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = generation_tasks[task_id]
    return GenerationStatusResponse(
        task_id=task_id,
        status=task.get("status", "unknown"),
        progress=task.get("progress"),
        result=task.get("result"),
        error=task.get("error")
    )


# ============== Share Characters Between Brand and Game ==============

@app.post("/games/{game_id}/characters/share-from-brand/{brand_id}")
async def share_brand_characters_to_game(game_id: str, brand_id: str):
    """Copy all characters from a brand to a game"""
    storage: S3Storage = app.state.storage
    
    # Check both exist
    game_data = await storage.load_json(f"games/{game_id}", "game.json")
    if not game_data:
        raise HTTPException(status_code=404, detail="Game not found")
    
    brand_data = await storage.load_json(f"brands/{brand_id}", "brand.json")
    if not brand_data:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # Sync characters
    import subprocess
    result = subprocess.run([
        "aws", "s3", "sync",
        f"s3://{storage.bucket}/{storage.prefix}/brands/{brand_id}/Characters/",
        f"s3://{storage.bucket}/{storage.prefix}/games/{game_id}/Characters/"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to sync characters")
    
    # Update game.json
    characters = storage.list_items(f"games/{game_id}/Characters")
    game_data["characters"] = characters
    game_data["shared_from_brand"] = brand_id
    await storage.save_json(f"games/{game_id}", "game.json", game_data)
    
    return {
        "message": f"Shared {len(characters)} characters from {brand_id} to {game_id}",
        "characters": characters
    }


# ============== Validation & Utility Endpoints ==============

@app.get("/validate/brand/{brand_id}")
async def validate_brand_structure(brand_id: str):
    """Validate S3 structure for a brand follows the expected pattern
    
    Checks:
    - brand.json exists and is valid
    - Characters folder exists
    - Each character has character.json with required fields
    - public_urls have proper format
    """
    storage: S3Storage = app.state.storage
    issues = []
    warnings = []
    
    # Check brand.json
    brand_data = await storage.load_json(f"brands/{brand_id}", "brand.json")
    if not brand_data:
        issues.append("brand.json not found or invalid")
    else:
        if "name" not in brand_data:
            issues.append("brand.json missing 'name' field")
        if "characters" not in brand_data:
            warnings.append("brand.json missing 'characters' list")
    
    # List and validate characters
    characters = storage.list_items(f"brands/{brand_id}/Characters")
    validated_chars = []
    
    for char_id in characters:
        if char_id.endswith(".json"):
            continue  # Skip mapping file
        
        char_data = await storage.load_json(
            f"brands/{brand_id}/Characters/{char_id}", "character.json"
        )
        
        char_status = {"id": char_id, "valid": True, "issues": [], "warnings": []}
        
        if not char_data:
            char_status["valid"] = False
            char_status["issues"].append("character.json not found")
        else:
            required_fields = ["id", "name", "identifier_in_scene"]
            for field in required_fields:
                if field not in char_data:
                    char_status["issues"].append(f"Missing required field: {field}")
                    char_status["valid"] = False
            
            # Check public_urls
            urls = char_data.get("public_urls", {})
            if not urls:
                char_status["warnings"].append("No public_urls defined")
            else:
                # Should have both 'front' and 'portrait_front' for compatibility
                if "front" not in urls and "portrait_front" not in urls:
                    char_status["warnings"].append("No front portrait URL")
                if "front" in urls and "portrait_front" not in urls:
                    char_status["warnings"].append("Missing 'portrait_front' alias (for compatibility)")
        
        validated_chars.append(char_status)
    
    is_valid = len(issues) == 0 and all(c["valid"] for c in validated_chars)
    
    return {
        "brand_id": brand_id,
        "valid": is_valid,
        "issues": issues,
        "warnings": warnings,
        "characters": validated_chars,
        "character_count": len(validated_chars)
    }


@app.get("/validate/game/{game_id}")
async def validate_game_structure(game_id: str):
    """Validate S3 structure for a game"""
    storage: S3Storage = app.state.storage
    issues = []
    warnings = []
    
    game_data = await storage.load_json(f"games/{game_id}", "game.json")
    if not game_data:
        issues.append("game.json not found or invalid")
    else:
        if "name" not in game_data:
            issues.append("game.json missing 'name' field")
    
    characters = storage.list_items(f"games/{game_id}/Characters")
    validated_chars = []
    
    for char_id in characters:
        if char_id.endswith(".json"):
            continue
        
        char_data = await storage.load_json(
            f"games/{game_id}/Characters/{char_id}", "character.json"
        )
        
        char_status = {"id": char_id, "valid": True, "issues": [], "warnings": []}
        
        if not char_data:
            char_status["valid"] = False
            char_status["issues"].append("character.json not found")
        else:
            for field in ["id", "name", "identifier_in_scene"]:
                if field not in char_data:
                    char_status["issues"].append(f"Missing: {field}")
                    char_status["valid"] = False
        
        validated_chars.append(char_status)
    
    is_valid = len(issues) == 0 and all(c["valid"] for c in validated_chars)
    
    return {
        "game_id": game_id,
        "valid": is_valid,
        "issues": issues,
        "warnings": warnings,
        "characters": validated_chars
    }


@app.post("/brands/{brand_id}/characters/{char_id}/aliases")
async def add_character_alias(brand_id: str, char_id: str, alias: str):
    """Add an alias for a character (for backward compatibility)"""
    storage: S3Storage = app.state.storage
    
    # Load character data
    char_data = await storage.load_json(
        f"brands/{brand_id}/Characters/{char_id}", "character.json"
    )
    if not char_data:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Add alias
    if "aliases" not in char_data:
        char_data["aliases"] = []
    if alias not in char_data["aliases"]:
        char_data["aliases"].append(alias)
    
    # Save updated character.json
    await storage.save_json(
        f"brands/{brand_id}/Characters/{char_id}", "character.json", char_data
    )
    
    # Update mapping
    await storage.update_characters_mapping(
        "brands", brand_id, alias, char_id, char_data.get("aliases", [])
    )
    
    return {"message": f"Added alias '{alias}' for character '{char_id}'"}


@app.get("/brands/{brand_id}/characters-mapping")
async def get_characters_mapping(brand_id: str):
    """Get the characters mapping for a brand"""
    storage: S3Storage = app.state.storage
    mapping = await storage.load_json(
        f"brands/{brand_id}/Characters", "characters_mapping.json"
    )
    if not mapping:
        return {"mapping": {}, "characters": {}}
    return mapping


@app.post("/fix/brand/{brand_id}/public-urls")
async def fix_brand_public_urls(brand_id: str):
    """Fix public_urls to have both 'front' and 'portrait_front' formats"""
    storage: S3Storage = app.state.storage
    fixed_count = 0
    
    characters = storage.list_items(f"brands/{brand_id}/Characters")
    
    for char_id in characters:
        if char_id.endswith(".json"):
            continue
        
        char_data = await storage.load_json(
            f"brands/{brand_id}/Characters/{char_id}", "character.json"
        )
        if not char_data:
            continue
        
        urls = char_data.get("public_urls", {})
        updated = False
        
        # Ensure both formats exist
        for view in ["front", "side", "back"]:
            if view in urls and f"portrait_{view}" not in urls:
                urls[f"portrait_{view}"] = urls[view]
                updated = True
            elif f"portrait_{view}" in urls and view not in urls:
                urls[view] = urls[f"portrait_{view}"]
                updated = True
        
        if updated:
            char_data["public_urls"] = urls
            await storage.save_json(
                f"brands/{brand_id}/Characters/{char_id}", "character.json", char_data
            )
            fixed_count += 1
    
    return {"message": f"Fixed public_urls for {fixed_count} characters"}


# ============== S3 Pattern Documentation ==============

@app.get("/docs/s3-pattern")
async def get_s3_pattern_documentation():
    """Return documentation for the expected S3 structure"""
    return {
        "description": "Expected S3 structure for brands, games, and characters",
        "pattern": {
            "brands": {
                "path": "s3://{bucket}/{prefix}/brands/{brand_id}/",
                "files": {
                    "brand.json": {
                        "required_fields": ["id", "name", "description"],
                        "optional_fields": ["tagline", "story", "values", "characters"],
                        "note": "characters should be list of character folder names"
                    }
                },
                "folders": {
                    "Characters/": {
                        "{CharacterName}/": {
                            "character.json": {
                                "required_fields": ["id", "name", "identifier_in_scene"],
                                "recommended_fields": ["static_features", "public_urls", "role"]
                            },
                            "front.png": "Front view portrait",
                            "side.png": "Side view portrait",
                            "back.png": "Back view portrait",
                            "voice.m4a": "Voice sample (optional)"
                        },
                        "characters_mapping.json": "Optional - maps aliases to canonical names"
                    }
                }
            },
            "games": {
                "path": "s3://{bucket}/{prefix}/games/{game_id}/",
                "note": "Same structure as brands, with game.json instead of brand.json"
            }
        },
        "public_urls_format": {
            "note": "For compatibility, include both short and long key formats",
            "example": {
                "front": "https://..../front.png",
                "portrait_front": "https://..../front.png",
                "side": "https://..../side.png",
                "portrait_side": "https://..../side.png"
            }
        },
        "naming_conventions": {
            "character_folders": "Use actual character names (AUTOcurio, DotDot) not IDs (C1, C2)",
            "aliases": "Store legacy IDs in character.json aliases field",
            "mapping": "Use characters_mapping.json for alias resolution"
        }
    }


# ============== S3 API Endpoints ==============

@app.get("/s3/config")
async def get_s3_config():
    """Return S3 configuration (no secrets). For building public URLs and frontend."""
    storage: S3Storage = app.state.storage
    base = f"https://{storage.bucket}.s3.{storage.region}.amazonaws.com/{storage.prefix}"
    return {
        "bucket": storage.bucket,
        "prefix": storage.prefix,
        "region": storage.region,
        "base_url": base + "/" if not base.endswith("/") else base,
    }


@app.get("/s3/presign-url")
async def get_s3_presign_url(
    key: str = Query(..., description="Full S3 object key (e.g. agent-assets/brands/x/Logo.png)"),
    expires: int = Query(3600, ge=60, le=604800, description="URL expiry in seconds (60–604800)"),
):
    """Generate a presigned GET URL for a private S3 object. Key is the full object key within the bucket."""
    storage: S3Storage = app.state.storage
    url = storage.generate_presigned_url(key, expires=expires)
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate presigned URL")
    return {"url": url, "expires_in": expires}


@app.get("/s3/list")
async def list_s3_objects(
    prefix: str = Query("", description="Prefix under S3_ASSET_PREFIX (e.g. brands, brands/x/Characters)"),
    max_keys: int = Query(100, ge=1, le=1000, description="Max keys to return"),
):
    """List S3 objects under the given prefix (relative to S3_ASSET_PREFIX). Returns key, size, last_modified."""
    storage: S3Storage = app.state.storage
    objects = storage.list_objects(prefix=prefix, max_keys=max_keys)
    return {"prefix": prefix, "objects": objects, "count": len(objects)}


# ============== Run Server ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
