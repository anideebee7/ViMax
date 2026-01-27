#!/usr/bin/env python3
"""
Regenerate character sheets from front_reference.png files.

This script:
1. Uses front_reference.png from the working directory as the source of truth
2. Generates all 9 variants (3 views x 3 expressions) using image-to-image generation
3. Creates a character_sheet.png grid
4. Uploads to S3 for intelli-verse-x brand
5. Replicates to quiz-verse game

Usage:
    python regenerate_character_sheets_from_reference.py
    python regenerate_character_sheets_from_reference.py --character autocurio
    python regenerate_character_sheets_from_reference.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from utils.pipeline.generator_factory import create_image_generator
from utils.media.character_sheet import combine_views_to_sheet
from interfaces.entities.character_sheet import CharacterView, CharacterExpression

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets"
S3_REGION = "us-east-1"

# Working directory with reference images
WORKING_DIR = Path(os.getenv("WORKING_DIR", ".working_dir/character_sheets"))

# Character definitions with detailed visual descriptions
# These descriptions are used to generate consistent variants
CHARACTERS = {
    "autocurio": {
        "name": "AutoCurio",
        "description": """Cute black robot character with a rounded body and head. Key features:
- Matte black smooth body with soft edges
- Large round glowing cyan/blue eyes with white reflections
- Blue antenna ball on top of head
- Black circular ear pieces on sides of head
- Blue "X" logo on chest
- Small stubby arms and legs
- Friendly, curious expression
- 3D animated cartoon style""",
    },
    "DotDot": {
        "name": "DotDot",
        "description": """Spherical flying drone character. Key features:
- Metallic teal/cyan spherical body
- Black rectangular face screen in front showing yellow emoji expressions
- Two teal wing-like protrusions on the sides
- Floating/hovering with subtle shadow below
- Smooth metallic surface with subtle highlights
- 3D animated cartoon style""",
    },
    "Gloop": {
        "name": "Gloop",
        "description": """Cute blue slime/water droplet character. Key features:
- Bright cyan/light blue translucent gelatinous body
- Rounded droplet shape with pointed top
- Large friendly white eyes with black pupils
- Wide happy smile showing pink inside
- Small stubby arms
- Sitting pose with rounded bottom
- Glossy, shiny surface with highlights
- 3D animated cartoon style""",
    },
    "NanaNova": {
        "name": "NanaNova",
        "description": """Energetic elderly scientist/inventor character. Key features:
- Gray/white wild messy hair
- Round glasses with brown frames
- Peachy/tan skin with rosy cheeks
- Big friendly smile showing teeth
- Blue coat/cardigan over cream/beige shirt
- Brown pants and brown shoes
- Holding a glowing blue staff/wand with blue orb on top
- Dynamic energetic pose
- 3D animated Pixar-style cartoon""",
    },
    "Tinker": {
        "name": "Tinker",
        "description": """Young inventor boy character. Key features:
- Brown messy spiky hair
- Large round eyes with brown irises
- Goggles pushed up on forehead
- Orange/rust colored hoodie
- Khaki/tan cargo shorts with pockets
- Brown boots
- Teal/turquoise tech backpack with tools and wires
- Robotic grabber arm held up in one hand
- Small glowing blue cube accessory
- Utility belt with tools
- Smudges of dirt/grease on face and clothes
- 3D animated cartoon style""",
    },
    "Whispurr": {
        "name": "Whispurr",
        "description": """Magical white fluffy cat character. Key features:
- Pure white fluffy fur coat
- Large expressive blue eyes
- Pink nose
- Pointed ears with pink inner ears
- Fluffy white chest fur
- Long flowing tail with light blue/cyan magical glow at tip
- Four white paws
- Cute friendly expression
- 3D animated cartoon style""",
    },
}


@dataclass
class GenerationResult:
    """Result of generating a single image."""
    success: bool
    path: Optional[str] = None
    error: Optional[str] = None


def get_s3_public_url(asset_type: str, asset_id: str, char_id: str, filename: str) -> str:
    """Generate S3 public URL."""
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{S3_PREFIX}/{asset_type}/{asset_id}/Characters/{char_id}/{filename}"


def upload_to_s3(local_path: str, s3_key: str, public: bool = True) -> bool:
    """Upload file to S3."""
    args = ["aws", "s3", "cp", local_path, f"s3://{S3_BUCKET}/{s3_key}"]
    if public:
        args.extend(["--acl", "public-read"])
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"S3 upload failed: {result.stderr}")
        return False
    return True


def download_from_s3(s3_key: str, local_path: str) -> bool:
    """Download file from S3."""
    result = subprocess.run(
        ["aws", "s3", "cp", f"s3://{S3_BUCKET}/{s3_key}", local_path],
        capture_output=True, text=True
    )
    return result.returncode == 0


def upload_json_to_s3(data: Dict, s3_key: str, public: bool = True) -> bool:
    """Upload JSON data to S3."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
        json.dump(data, f, indent=2)
        temp_path = f.name
    try:
        return upload_to_s3(temp_path, s3_key, public)
    finally:
        os.unlink(temp_path)


def download_json_from_s3(s3_key: str) -> Optional[Dict]:
    """Download JSON from S3."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    try:
        if download_from_s3(s3_key, temp_path):
            with open(temp_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Error downloading JSON: {e}")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return None


class CharacterSheetRegenerator:
    """Regenerate character sheets from reference images."""
    
    def __init__(self, working_dir: Path, dry_run: bool = False):
        self.working_dir = working_dir
        self.dry_run = dry_run
        self.image_generator = None
        
    async def initialize(self):
        """Initialize the image generator."""
        logger.info("Initializing image generator (UnifiedImageGenerator with fallback chain)")
        self.image_generator = create_image_generator()
        
    async def generate_single_view(
        self,
        char_id: str,
        char_info: Dict,
        reference_path: str,
        view: CharacterView,
        expression: CharacterExpression,
        output_dir: Path,
    ) -> GenerationResult:
        """Generate a single view image using the reference as input."""
        
        output_path = output_dir / f"{view.value}_{expression.value}.png"
        
        # Build the prompt
        view_instructions = {
            CharacterView.FRONT: "FRONT VIEW - character facing directly toward camera",
            CharacterView.SIDE: "SIDE VIEW (90-degree profile) - character facing left, full body in profile",
            CharacterView.BACK: "BACK VIEW - character facing away from camera, back visible, NO face",
        }
        
        expression_instructions = {
            CharacterExpression.NEUTRAL: "neutral, calm expression",
            CharacterExpression.HAPPY: "happy, joyful, smiling expression",
            CharacterExpression.SAD: "sad, melancholy expression",
        }
        
        prompt = f"""Generate the EXACT same character as shown in the reference image, but with a different view and expression.

CHARACTER: {char_info['name']}
{char_info['description']}

REQUIRED VIEW: {view_instructions[view]}
REQUIRED EXPRESSION: {expression_instructions[expression]}

CRITICAL REQUIREMENTS:
1. The character MUST be IDENTICAL to the reference - same design, colors, clothing, accessories, proportions
2. Only the camera angle (view) and facial expression should change
3. Full body must be visible from head to feet
4. Pure white background with no elements or shadows
5. Character should be centered in frame
6. Maintain the exact same 3D animated cartoon style

{'For back view: Do NOT show any face or front features. Show only the back of the character.' if view == CharacterView.BACK else ''}
"""
        
        # Save debug prompt
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = debug_dir / f"{view.value}_{expression.value}_prompt.txt"
        prompt_file.write_text(prompt)
        
        try:
            logger.info(f"  Generating {view.value}_{expression.value}...")
            
            # Generate image using reference
            image_output = await self.image_generator.generate_single_image(
                prompt=prompt,
                reference_image_paths=[reference_path],
                aspect_ratio="1:1",
            )
            
            # Save the image
            await self._save_image_output(image_output, str(output_path))
            
            if output_path.exists():
                logger.info(f"    Generated: {output_path.name}")
                return GenerationResult(success=True, path=str(output_path))
            else:
                return GenerationResult(success=False, error="Output file not created")
                
        except Exception as e:
            logger.error(f"    Failed to generate {view.value}_{expression.value}: {e}")
            return GenerationResult(success=False, error=str(e))
    
    async def _save_image_output(self, image_output, output_path: str):
        """Save an ImageOutput to a file."""
        import aiohttp
        import aiofiles
        from PIL import Image as PILImage
        from io import BytesIO
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if image_output.fmt == "url":
            async with aiohttp.ClientSession() as session:
                async with session.get(image_output.data) as response:
                    if response.status == 200:
                        async with aiofiles.open(output_path, 'wb') as f:
                            await f.write(await response.read())
                    else:
                        raise RuntimeError(f"Failed to download: {response.status}")
        elif image_output.fmt == "base64":
            import base64
            async with aiofiles.open(output_path, 'wb') as f:
                await f.write(base64.b64decode(image_output.data))
        elif image_output.fmt == "path":
            shutil.copy(image_output.data, output_path)
        elif image_output.fmt == "pil":
            # Handle different image types
            data = image_output.data
            if isinstance(data, PILImage.Image):
                # Standard PIL Image
                data.save(output_path, "PNG")
            elif hasattr(data, '_pil_image'):
                # Google genai Image wrapper - access underlying PIL image
                data._pil_image.save(output_path, "PNG")
            elif hasattr(data, 'save'):
                # Object with save method
                data.save(output_path)
            elif hasattr(data, 'image_bytes'):
                # Google genai Image with image_bytes
                async with aiofiles.open(output_path, 'wb') as f:
                    await f.write(data.image_bytes)
            elif hasattr(data, '_image_bytes'):
                # Google genai Image with private _image_bytes
                async with aiofiles.open(output_path, 'wb') as f:
                    await f.write(data._image_bytes)
            else:
                # Try to convert via string representation or bytes
                try:
                    # Google genai types.Image objects can be converted via BytesIO
                    img_bytes = bytes(data)
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(img_bytes)
                except Exception:
                    raise ValueError(f"Cannot save image of type {type(data)}")
        else:
            raise ValueError(f"Unknown format: {image_output.fmt}")
    
    async def regenerate_character(
        self,
        char_id: str,
        char_info: Dict,
    ) -> Dict[str, str]:
        """Regenerate all views for a single character.
        
        Returns:
            Dict mapping filenames to local paths
        """
        char_dir = self.working_dir / char_id
        reference_path = char_dir / "front_reference.png"
        
        if not reference_path.exists():
            logger.error(f"Reference image not found: {reference_path}")
            return {}
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Regenerating character: {char_id} ({char_info['name']})")
        logger.info(f"Reference: {reference_path}")
        logger.info(f"{'='*60}")
        
        # Copy reference as front_neutral
        front_neutral_path = char_dir / "front_neutral.png"
        shutil.copy(reference_path, front_neutral_path)
        logger.info(f"  Copied reference as front_neutral.png")
        
        generated_files = {
            "front_neutral.png": str(front_neutral_path),
        }
        
        # Generate all other views
        views = [CharacterView.FRONT, CharacterView.SIDE, CharacterView.BACK]
        expressions = [CharacterExpression.NEUTRAL, CharacterExpression.HAPPY, CharacterExpression.SAD]
        
        for view in views:
            for expression in expressions:
                # Skip front_neutral (already have it from reference)
                if view == CharacterView.FRONT and expression == CharacterExpression.NEUTRAL:
                    continue
                
                if self.dry_run:
                    logger.info(f"  [DRY RUN] Would generate {view.value}_{expression.value}")
                    continue
                
                result = await self.generate_single_view(
                    char_id=char_id,
                    char_info=char_info,
                    reference_path=str(reference_path),
                    view=view,
                    expression=expression,
                    output_dir=char_dir,
                )
                
                if result.success and result.path:
                    filename = f"{view.value}_{expression.value}.png"
                    generated_files[filename] = result.path
                
                # Small delay between requests
                await asyncio.sleep(1)
        
        # Create character sheet
        if not self.dry_run and len(generated_files) > 1:
            logger.info("  Creating character sheet...")
            sheet_path = char_dir / "character_sheet.png"
            
            # Build views dict for combining
            views_dict = {}
            for view in CharacterView:
                for expr in CharacterExpression:
                    filename = f"{view.value}_{expr.value}.png"
                    if filename in generated_files:
                        views_dict[(view, expr)] = generated_files[filename]
            
            combined_path = combine_views_to_sheet(views_dict, str(sheet_path))
            if combined_path:
                generated_files["character_sheet.png"] = combined_path
                logger.info(f"    Created: character_sheet.png")
        
        return generated_files
    
    def upload_to_s3_location(
        self,
        char_id: str,
        generated_files: Dict[str, str],
        asset_type: str,
        asset_id: str,
    ) -> Dict[str, str]:
        """Upload generated files to S3.
        
        Returns:
            Dict mapping filenames to public URLs
        """
        public_urls = {}
        
        for filename, local_path in generated_files.items():
            s3_key = f"{S3_PREFIX}/{asset_type}/{asset_id}/Characters/{char_id}/{filename}"
            logger.info(f"  Uploading {filename} to {asset_type}/{asset_id}...")
            
            if self.dry_run:
                logger.info(f"    [DRY RUN] Would upload to: {s3_key}")
                public_urls[filename] = get_s3_public_url(asset_type, asset_id, char_id, filename)
            else:
                if upload_to_s3(local_path, s3_key):
                    url = get_s3_public_url(asset_type, asset_id, char_id, filename)
                    public_urls[filename] = url
                    logger.info(f"    Uploaded: {url[:60]}...")
                else:
                    logger.error(f"    Failed to upload {filename}")
        
        return public_urls
    
    def update_character_json(
        self,
        char_id: str,
        public_urls: Dict[str, str],
        asset_type: str,
        asset_id: str,
    ) -> bool:
        """Update character.json with new public URLs."""
        s3_key = f"{S3_PREFIX}/{asset_type}/{asset_id}/Characters/{char_id}/character.json"
        
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would update character.json at {s3_key}")
            return True
        
        # Download existing
        char_data = download_json_from_s3(s3_key)
        if not char_data:
            logger.warning(f"  Could not download character.json for {char_id}")
            return False
        
        # Update public_urls
        if "public_urls" not in char_data:
            char_data["public_urls"] = {}
        
        for filename, url in public_urls.items():
            if filename == "character_sheet.png":
                char_data["public_urls"]["character_sheet"] = url
                char_data["public_urls"]["sheet"] = url
            else:
                # front_neutral.png -> front_neutral
                key = filename.replace(".png", "")
                char_data["public_urls"][key] = url
        
        # Upload back
        if upload_json_to_s3(char_data, s3_key):
            logger.info(f"  Updated character.json for {char_id}")
            return True
        else:
            logger.error(f"  Failed to update character.json for {char_id}")
            return False
    
    async def process_character(
        self,
        char_id: str,
        char_info: Dict,
    ) -> bool:
        """Process a single character: regenerate, upload to brand and game."""
        
        # Regenerate all views
        generated_files = await self.regenerate_character(char_id, char_info)
        
        if not generated_files:
            logger.warning(f"No files generated for {char_id}")
            return False
        
        # Upload to intelli-verse-x brand
        logger.info(f"\n  Uploading to intelli-verse-x brand...")
        brand_urls = self.upload_to_s3_location(
            char_id, generated_files, "brands", "intelli-verse-x"
        )
        if brand_urls:
            self.update_character_json(char_id, brand_urls, "brands", "intelli-verse-x")
        
        # Replicate to quiz-verse game
        logger.info(f"\n  Replicating to quiz-verse game...")
        game_urls = self.upload_to_s3_location(
            char_id, generated_files, "games", "quiz-verse"
        )
        if game_urls:
            self.update_character_json(char_id, game_urls, "games", "quiz-verse")
        
        return True
    
    async def run(self, selected_characters: Optional[List[str]] = None):
        """Run the regeneration for all or selected characters."""
        
        await self.initialize()
        
        # Filter characters if specified
        chars_to_process = CHARACTERS
        if selected_characters:
            chars_to_process = {
                k: v for k, v in CHARACTERS.items() 
                if k.lower() in [c.lower() for c in selected_characters]
            }
        
        logger.info(f"\n{'='*60}")
        logger.info("CHARACTER SHEET REGENERATION")
        logger.info(f"{'='*60}")
        logger.info(f"Working directory: {self.working_dir}")
        logger.info(f"Characters to process: {list(chars_to_process.keys())}")
        logger.info(f"Dry run: {self.dry_run}")
        
        results = {}
        for char_id, char_info in chars_to_process.items():
            try:
                success = await self.process_character(char_id, char_info)
                results[char_id] = success
            except Exception as e:
                logger.error(f"Error processing {char_id}: {e}")
                import traceback
                traceback.print_exc()
                results[char_id] = False
        
        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("SUMMARY")
        logger.info(f"{'='*60}")
        for char_id, success in results.items():
            status = "SUCCESS" if success else "FAILED"
            logger.info(f"  {char_id}: {status}")
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"\nCompleted: {success_count}/{len(results)} characters")


async def main():
    parser = argparse.ArgumentParser(description="Regenerate character sheets from reference images")
    parser.add_argument("--character", "-c", help="Specific character to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    parser.add_argument("--working-dir", type=Path, default=WORKING_DIR, help="Working directory")
    
    args = parser.parse_args()
    
    regenerator = CharacterSheetRegenerator(
        working_dir=args.working_dir,
        dry_run=args.dry_run,
    )
    
    selected = [args.character] if args.character else None
    await regenerator.run(selected_characters=selected)


if __name__ == "__main__":
    asyncio.run(main())
