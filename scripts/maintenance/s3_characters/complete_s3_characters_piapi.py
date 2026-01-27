#!/usr/bin/env python3
"""
Complete S3 character assets using unified image generator.
- Generate side/back portraits for characters missing them
- All voices are now complete

Uses unified image generator with fallback chain:
1. Gemini API (primary)
2. PiAPI nano-banana-pro (fallback)
3. KieAI nano-banana-pro (last resort)

NEVER change the image model - always use nano-banana-pro.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.pipeline.generator_factory import create_image_generator
S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets/brands/intelli-verse-x/Characters"
S3_BASE_URL = f"https://{S3_BUCKET}.s3.amazonaws.com/{S3_PREFIX}"

CHARACTERS = {
    "C2": {"name": "Dot Dot", "front_ext": "png"},
    "C3": {"name": "Gloop", "front_ext": "png"},
    "C4": {"name": "NanaNova", "front_ext": "png"},
    "C5": {"name": "Thinker", "front_ext": "png"},
    "C6": {"name": "Whispurr", "front_ext": "png"},
}


def s3_exists(s3_path: str) -> bool:
    """Check if S3 object exists."""
    result = subprocess.run(
        ["aws", "s3", "ls", s3_path],
        capture_output=True, text=True
    )
    return result.returncode == 0 and len(result.stdout.strip()) > 0


# Global image generator instance (initialized lazily)
_image_generator = None


def get_image_generator():
    """Get or create the unified image generator.
    
    Uses the unified generator with fallback chain:
    1. Gemini API (primary)
    2. PiAPI nano-banana-pro (fallback)
    3. KieAI nano-banana-pro (last resort)
    """
    global _image_generator
    if _image_generator is None:
        _image_generator = create_image_generator()
    return _image_generator


async def generate_portrait(char_id: str, char_info: dict, view: str, work_dir: Path) -> Optional[str]:
    """Generate a side or back portrait using unified image generator.
    
    Uses the unified generator with fallback chain:
    1. Gemini API (primary)
    2. PiAPI nano-banana-pro (fallback)
    3. KieAI nano-banana-pro (last resort)
    
    NEVER change the image model - always use nano-banana-pro.
    """
    front_url = f"{S3_BASE_URL}/{char_id}/character.{char_info['front_ext']}"
    
    # Download front image as reference
    front_local = work_dir / f"{char_id}_front.{char_info['front_ext']}"
    result = subprocess.run(["curl", "-s", front_url, "-o", str(front_local)], capture_output=True)
    if result.returncode != 0:
        print(f"  Failed to download front image from {front_url}")
        return None
    
    if view == "side":
        prompt = f"Generate a full-body, side-view portrait of this character with a pure white background. The character should be facing left. Standing with arms relaxed at sides."
    else:  # back
        prompt = f"Generate a full-body, back-view portrait of this character with a pure white background. The character should be facing away from camera. No facial features should be visible."
    
    print(f"  Generating {view} portrait for {char_id}...")
    
    image_generator = get_image_generator()
    image_output = await image_generator.generate_single_image(
        prompt=prompt,
        reference_image_paths=[str(front_local)],
        aspect_ratio="1:1"
    )
    
    # Save the generated image
    output_path = work_dir / f"{char_id}_{view}.png"
    image_output.save(str(output_path))
    
    print(f"  Generated {view} portrait saved to {output_path}")
    return str(output_path)


def upload_to_s3(local_path: str, s3_path: str) -> bool:
    """Upload a local file to S3."""
    result = subprocess.run(["aws", "s3", "cp", local_path, s3_path], capture_output=True)
    if result.returncode != 0:
        print(f"  Failed to upload to {s3_path}")
        return False
    return True


async def process_character(char_id: str, char_info: dict, work_dir: Path):
    """Process a single character - generate missing portraits.
    
    Uses unified image generator with fallback chain:
    1. Gemini API (primary)
    2. PiAPI nano-banana-pro (fallback)
    3. KieAI nano-banana-pro (last resort)
    """
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}"
    
    # Check what exists
    has_side = s3_exists(f"{s3_base}/side.png")
    has_back = s3_exists(f"{s3_base}/back.png")
    
    print(f"\n{char_id} ({char_info['name']}):")
    print(f"  Side: {'exists' if has_side else 'MISSING'}")
    print(f"  Back: {'exists' if has_back else 'MISSING'}")
    
    # Generate missing portraits
    if not has_side:
        try:
            local_path = await generate_portrait(char_id, char_info, "side", work_dir)
            if local_path:
                success = upload_to_s3(local_path, f"{s3_base}/side.png")
                if success:
                    print(f"  ✓ Side portrait uploaded")
        except Exception as e:
            print(f"  ✗ Failed to generate side portrait: {e}")
    
    if not has_back:
        try:
            local_path = await generate_portrait(char_id, char_info, "back", work_dir)
            if local_path:
                success = upload_to_s3(local_path, f"{s3_base}/back.png")
                if success:
                    print(f"  ✓ Back portrait uploaded")
        except Exception as e:
            print(f"  ✗ Failed to generate back portrait: {e}")


async def update_character_json(char_id: str):
    """Update character.json with public URLs."""
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}"
    
    # Download current character.json
    result = subprocess.run(
        ["aws", "s3", "cp", f"{s3_base}/character.json", "/tmp/char.json"],
        capture_output=True
    )
    if result.returncode != 0:
        return
    
    with open("/tmp/char.json", "r") as f:
        char_data = json.load(f)
    
    # Update public URLs
    char_data["public_urls"] = {
        "portrait_front": f"{S3_BASE_URL}/{char_id}/character.png",
        "portrait_side": f"{S3_BASE_URL}/{char_id}/side.png",
        "portrait_back": f"{S3_BASE_URL}/{char_id}/back.png",
        "voice": f"{S3_BASE_URL}/{char_id}/voice.mp3"
    }
    
    # Update media paths
    if "media" in char_data and "portraits" in char_data["media"]:
        char_data["media"]["portraits"]["2d"]["side"] = {
            "path": "side.png",
            "description": f"Side view portrait of {char_data.get('name', char_id)}"
        }
        char_data["media"]["portraits"]["2d"]["back"] = {
            "path": "back.png",
            "description": f"Back view portrait of {char_data.get('name', char_id)}"
        }
    
    with open("/tmp/char.json", "w") as f:
        json.dump(char_data, f, indent=2)
    
    subprocess.run(["aws", "s3", "cp", "/tmp/char.json", f"{s3_base}/character.json"], capture_output=True)
    print(f"  Updated character.json for {char_id}")


async def main():
    print("=" * 60)
    print("Completing S3 Character Assets with Unified Image Generator")
    print("=" * 60)
    print("\nUsing unified generator with fallback chain:")
    print("  1. Gemini API (primary)")
    print("  2. PiAPI nano-banana-pro (fallback)")
    print("  3. KieAI nano-banana-pro (last resort)")
    print("\nNEVER change the image model - always use nano-banana-pro.\n")
    
    # Create working directory
    work_dir = Path(tempfile.mkdtemp(prefix="s3_chars_"))
    print(f"Working directory: {work_dir}")
    
    # Process each character
    for char_id, char_info in CHARACTERS.items():
        await process_character(char_id, char_info, work_dir)
    
    # Update character.json files
    print("\n--- Updating character.json files ---")
    for char_id in list(CHARACTERS.keys()) + ["C1"]:
        await update_character_json(char_id)
    
    print("\n" + "=" * 60)
    print("Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
