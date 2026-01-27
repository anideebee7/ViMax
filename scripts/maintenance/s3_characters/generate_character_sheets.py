#!/usr/bin/env python3
"""
Generate character sheets for existing S3 characters.

This script:
1. Loads existing characters from S3 that have front.png portraits
2. Generates a 3x3 character sheet grid with all views and expressions
3. Extracts individual views from the sheet
4. Uploads the sheet and extracted views to S3
5. Updates character.json with the new public URLs

The character sheet format:
+------------+------------+------------+
|  front     |   side     |   back     |  <- Neutral
|  neutral   |   neutral  |   neutral  |
+------------+------------+------------+
|  front     |   side     |   back     |  <- Happy
|  happy     |   happy    |   happy    |
+------------+------------+------------+
|  front     |   side     |   back     |  <- Sad
|  sad       |   sad      |   sad      |
+------------+------------+------------+

Usage:
    python generate_character_sheets.py --brand intelli-verse-x
    python generate_character_sheets.py --brand intelli-verse-x --character autocurio
    python generate_character_sheets.py --game quizverse --all
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.pipeline.s3_loader import S3CharacterLoader, S3Config, CharacterData
from utils.media.character_sheet import CharacterSheetSplitter, combine_views_to_sheet
from agents.producers.visuals.character_sheet import CharacterSheetGenerator
from interfaces.entities.character import CharacterInScene
from interfaces.entities.character_sheet import (
    CharacterView,
    CharacterExpression,
    SHEET_COLUMNS,
    SHEET_ROWS,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME", "intelli-verse-x-media")
S3_PREFIX = os.getenv("S3_ASSET_PREFIX", "agent-assets")
S3_REGION = os.getenv("AWS_REGION", "us-east-1")

# Working directory for temporary files
WORKING_DIR = Path(os.getenv("WORKING_DIR", ".working_dir/character_sheets"))


def get_image_generator(prefer_piapi: bool = True):
    """Initialize the unified image generator for character sheet generation.
    
    Uses the unified image generator with automatic fallback chain:
    1. Gemini API (GoogleImageGenerator) - Primary
    2. PiAPI nano-banana-pro - Fallback
    3. KieAI nano-banana-pro - Last resort
    
    NEVER change the image model - always use nano-banana-pro.
    
    Args:
        prefer_piapi: Ignored - uses unified generator with correct priority
    """
    from utils.pipeline.generator_factory import create_image_generator
    
    logger.info("Using UnifiedImageGenerator with fallback chain:")
    logger.info("  1. Gemini API (primary)")
    logger.info("  2. PiAPI nano-banana-pro (fallback)")
    logger.info("  3. KieAI nano-banana-pro (last resort)")
    
    return create_image_generator()


def download_from_s3(s3_path: str, local_path: str) -> bool:
    """Download a file from S3."""
    result = subprocess.run(
        ["aws", "s3", "cp", s3_path, local_path],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def upload_to_s3(local_path: str, s3_path: str, public: bool = True) -> bool:
    """Upload a file to S3."""
    args = ["aws", "s3", "cp", local_path, s3_path]
    if public:
        args.extend(["--acl", "public-read"])
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode == 0


def get_public_url(s3_path: str) -> str:
    """Convert S3 path to public URL."""
    # s3://bucket/prefix/... -> https://bucket.s3.region.amazonaws.com/prefix/...
    if s3_path.startswith("s3://"):
        path = s3_path[5:]  # Remove 's3://'
        bucket = path.split("/")[0]
        key = "/".join(path.split("/")[1:])
        return f"https://{bucket}.s3.{S3_REGION}.amazonaws.com/{key}"
    return s3_path


async def generate_character_sheet(
    char_data: CharacterData,
    image_generator,
    output_dir: Path,
    style: str = "colorful 3D animated cartoon style"
) -> Optional[Dict[str, str]]:
    """Generate a character sheet for a character.
    
    Args:
        char_data: Character data from S3
        image_generator: Image generator instance
        output_dir: Directory to save outputs
        style: Visual style for generation
        
    Returns:
        Dict mapping file names to local paths
    """
    char_id = char_data.identifier_in_scene
    char_dir = output_dir / char_id.replace(" ", "_")
    char_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Generating character sheet for {char_id}")
    
    # Check if front.png exists
    front_url = char_data.public_urls.get("front") or char_data.public_urls.get("portrait_front")
    if not front_url:
        logger.warning(f"No front portrait found for {char_id}, skipping")
        return None
    
    # Download front portrait as reference
    front_path = char_dir / "front_reference.png"
    logger.info(f"  Downloading front portrait from {front_url[:60]}...")
    
    try:
        from utils.media.image import download_image
        download_image(front_url, str(front_path))
    except Exception as e:
        logger.error(f"  Failed to download front portrait: {e}")
        return None
    
    if not front_path.exists():
        logger.error(f"  Front portrait not found at {front_path}")
        return None
    
    # Create a CharacterInScene for the generator
    char_scene = CharacterInScene(
        idx=0,
        identifier_in_scene=char_id,
        is_visible=True,
        static_features=char_data.static_features or char_data.appearance or char_data.description,
        dynamic_features=char_data.dynamic_features or "",
        description=char_data.description,
    )
    
    # Initialize the sheet generator
    sheet_generator = CharacterSheetGenerator(image_generator)
    
    # Generate from existing front portrait
    try:
        sheet = await sheet_generator.generate_from_existing_front(
            character=char_scene,
            front_neutral_path=str(front_path),
            style=style,
            output_dir=str(char_dir),
        )
        
        if not sheet:
            logger.error(f"  Failed to generate character sheet for {char_id}")
            return None
        
        # Collect generated files
        generated_files = {}
        
        # Character sheet
        sheet_path = char_dir / "character_sheet.png"
        if sheet_path.exists():
            generated_files["character_sheet.png"] = str(sheet_path)
        
        # Individual views with expressions
        for view in SHEET_COLUMNS:
            for expr in SHEET_ROWS:
                filename = f"{view.value}_{expr.value}.png"
                file_path = char_dir / filename
                if file_path.exists():
                    generated_files[filename] = str(file_path)
        
        logger.info(f"  Generated {len(generated_files)} files for {char_id}")
        return generated_files
        
    except Exception as e:
        logger.error(f"  Character sheet generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def upload_character_assets(
    char_id: str,
    generated_files: Dict[str, str],
    asset_type: str,
    asset_id: str,
) -> Dict[str, str]:
    """Upload generated character assets to S3.
    
    Returns:
        Dict mapping file names to public URLs
    """
    public_urls = {}
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{asset_type}/{asset_id}/Characters/{char_id}"
    
    for filename, local_path in generated_files.items():
        s3_path = f"{s3_base}/{filename}"
        logger.info(f"  Uploading {filename} to S3...")
        
        if upload_to_s3(local_path, s3_path):
            public_urls[filename] = get_public_url(s3_path)
            logger.info(f"    Uploaded: {public_urls[filename][:60]}...")
        else:
            logger.error(f"    Failed to upload {filename}")
    
    return public_urls


def update_character_json(
    asset_type: str,
    asset_id: str,
    char_id: str,
    new_urls: Dict[str, str],
) -> bool:
    """Update character.json with new public URLs."""
    s3_json_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/{asset_type}/{asset_id}/Characters/{char_id}/character.json"
    
    # Download existing character.json
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    
    try:
        if not download_from_s3(s3_json_path, temp_path):
            logger.warning(f"  Could not download character.json for {char_id}")
            return False
        
        with open(temp_path, "r") as f:
            char_json = json.load(f)
        
        # Update public_urls
        if "public_urls" not in char_json:
            char_json["public_urls"] = {}
        
        for filename, url in new_urls.items():
            # Map filenames to URL keys
            if filename == "character_sheet.png":
                char_json["public_urls"]["character_sheet"] = url
                char_json["public_urls"]["sheet"] = url
            else:
                # front_neutral.png -> front_neutral
                key = filename.replace(".png", "").replace(".jpg", "")
                char_json["public_urls"][key] = url
        
        # Write updated JSON
        with open(temp_path, "w") as f:
            json.dump(char_json, f, indent=2)
        
        # Upload back to S3
        if upload_to_s3(temp_path, s3_json_path):
            logger.info(f"  Updated character.json for {char_id}")
            return True
        else:
            logger.error(f"  Failed to upload updated character.json")
            return False
            
    except Exception as e:
        logger.error(f"  Error updating character.json: {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


async def process_character(
    char_data: CharacterData,
    image_generator,
    output_dir: Path,
    asset_type: str,
    asset_id: str,
    style: str,
    upload: bool = True,
) -> bool:
    """Process a single character: generate sheet, upload, update metadata."""
    char_id = char_data.identifier_in_scene
    logger.info(f"\n{'='*60}\nProcessing character: {char_id}\n{'='*60}")
    
    # Generate character sheet
    generated_files = await generate_character_sheet(
        char_data, image_generator, output_dir, style
    )
    
    if not generated_files:
        logger.warning(f"No files generated for {char_id}")
        return False
    
    if not upload:
        logger.info(f"Skipping upload (dry run) for {char_id}")
        return True
    
    # Upload to S3
    public_urls = upload_character_assets(
        char_id, generated_files, asset_type, asset_id
    )
    
    if not public_urls:
        logger.warning(f"No files uploaded for {char_id}")
        return False
    
    # Update character.json
    update_character_json(asset_type, asset_id, char_id, public_urls)
    
    logger.info(f"Completed processing {char_id}")
    return True


async def main():
    parser = argparse.ArgumentParser(description="Generate character sheets for S3 characters")
    parser.add_argument("--brand", help="Brand ID to process")
    parser.add_argument("--game", help="Game ID to process")
    parser.add_argument("--character", help="Specific character name to process")
    parser.add_argument("--all", action="store_true", help="Process all characters")
    parser.add_argument("--style", default="colorful 3D animated cartoon style",
                        help="Visual style for generation")
    parser.add_argument("--output-dir", type=Path, default=WORKING_DIR,
                        help="Output directory for generated files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate files but don't upload to S3")
    parser.add_argument("--use-kieai", action="store_true",
                        help="Use KieAI instead of PiAPI (PiAPI is faster)")
    
    args = parser.parse_args()
    
    if not args.brand and not args.game:
        parser.error("Either --brand or --game must be specified")
    
    # Initialize S3 loader
    config = S3Config(bucket=S3_BUCKET, prefix=S3_PREFIX, region=S3_REGION)
    loader = S3CharacterLoader(config)
    
    # Determine asset type and ID
    asset_type = "brands" if args.brand else "games"
    asset_id = args.brand or args.game
    
    # Load characters
    logger.info(f"Loading characters from {asset_type}/{asset_id}...")
    
    if args.brand:
        characters = loader.load_brand_characters(
            args.brand,
            [args.character] if args.character else None
        )
    else:
        characters = loader.load_game_characters(
            args.game,
            [args.character] if args.character else None
        )
    
    if not characters:
        logger.error("No characters found")
        return 1
    
    logger.info(f"Found {len(characters)} character(s)")
    
    # Initialize image generator
    try:
        image_generator = get_image_generator(prefer_piapi=not args.use_kieai)
        logger.info("Image generator initialized")
    except Exception as e:
        logger.error(f"Failed to initialize image generator: {e}")
        return 1
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process characters
    success_count = 0
    for char_data in characters:
        try:
            success = await process_character(
                char_data,
                image_generator,
                args.output_dir,
                asset_type,
                asset_id,
                args.style,
                upload=not args.dry_run,
            )
            if success:
                success_count += 1
        except Exception as e:
            logger.error(f"Error processing {char_data.identifier_in_scene}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Completed: {success_count}/{len(characters)} characters processed successfully")
    logger.info(f"{'='*60}")
    
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
