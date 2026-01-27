#!/usr/bin/env python3
"""
Fix S3 Character Structure

Renames C2-C6 folders to actual character names and creates a mapping file.
This ensures no redundancy and proper character identification.

Character Mapping:
- C1 -> AUTOcurio (already done)
- C2 -> DotDot
- C3 -> Gloop
- C4 -> NanaNova
- C5 -> Thinker
- C6 -> Whispurr
"""
import subprocess
import json
import tempfile
import os
from typing import Dict, Optional

S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets/brands/intelli-verse-x"
S3_BASE_URL = f"https://{S3_BUCKET}.s3.us-east-1.amazonaws.com/{S3_PREFIX}"

# Character mapping: old_id -> new_id (actual name)
CHARACTER_MAPPING = {
    "C1": "AUTOcurio",  # Already renamed
    "C2": "DotDot",
    "C3": "Gloop",
    "C4": "NanaNova",
    "C5": "Thinker",
    "C6": "Whispurr",
}

# Character details
CHARACTER_DETAILS = {
    "AUTOcurio": {
        "name": "AUTOcurio",
        "description": "A friendly black robot with cyan glowing eyes, antenna, headphones, and an X on its chest. The charismatic, energetic AI host with a warm, engaging, and highly motivational voice.",
        "role": "main_host",
        "is_visible": True,
        "static_features": "The charismatic, energetic AI host. Voice is warm, engaging, and highly motivational. Can appear as a digital avatar that winks.",
    },
    "DotDot": {
        "name": "DotDot",
        "description": "A small floating dot character, curious and observant. Often adds commentary and asks follow-up questions.",
        "role": "co_host",
        "is_visible": True,
        "static_features": "A small floating dot character with expressive eyes. Curious and observant.",
    },
    "Gloop": {
        "name": "Gloop",
        "description": "A friendly blob/slime character, playful and bouncy. Provides comic relief and fun facts.",
        "role": "co_host",
        "is_visible": True,
        "static_features": "A friendly blob/slime character, playful and bouncy. Often jiggles when excited.",
    },
    "NanaNova": {
        "name": "NanaNova",
        "description": "A wise grandmother-like figure with a warm voice. Tells stories and shares wisdom.",
        "role": "storyteller",
        "is_visible": True,
        "static_features": "A wise grandmother-like figure with kind eyes and a warm smile. Wears cozy clothes.",
    },
    "Thinker": {
        "name": "Thinker",
        "description": "A thoughtful character who loves science and facts. Often wears glasses and carries books.",
        "role": "expert",
        "is_visible": True,
        "static_features": "A thoughtful character who loves science. Wears glasses and often has a thinking pose.",
    },
    "Whispurr": {
        "name": "Whispurr",
        "description": "A quiet, mysterious cat character who leads silent wonder moments. Moves gracefully.",
        "role": "guide",
        "is_visible": True,
        "static_features": "A quiet, mysterious cat character. Moves gracefully and silently. Has wise, knowing eyes.",
    },
}


def run_s3_cmd(*args, capture=True) -> tuple:
    """Run AWS S3 command."""
    result = subprocess.run(
        ["aws", "s3", *args],
        capture_output=capture,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr


def s3_exists(s3_path: str) -> bool:
    """Check if S3 path exists."""
    success, stdout, _ = run_s3_cmd("ls", s3_path)
    return success and len(stdout.strip()) > 0


def get_json_from_s3(s3_path: str) -> Optional[Dict]:
    """Download and parse JSON from S3."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    try:
        success, _, _ = run_s3_cmd("cp", s3_path, temp_path)
        if not success:
            return None
        with open(temp_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {s3_path}: {e}")
        return None
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def upload_json_to_s3(data: Dict, s3_path: str) -> bool:
    """Upload JSON to S3."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
        json.dump(data, f, indent=2)
        temp_path = f.name
    try:
        success, _, stderr = run_s3_cmd("cp", temp_path, s3_path, "--acl", "public-read")
        if not success:
            print(f"Error uploading to {s3_path}: {stderr}")
        return success
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def rename_character_folder(old_id: str, new_id: str) -> bool:
    """Rename a character folder in S3 (copy + delete)."""
    if old_id == new_id:
        print(f"  {old_id}: Already using correct name")
        return True
    
    old_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{old_id}/"
    new_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{new_id}/"
    
    # Check if old folder exists
    if not s3_exists(old_path):
        print(f"  {old_id}: Source folder does not exist, skipping")
        return False
    
    # Check if new folder already exists
    if s3_exists(new_path):
        print(f"  {new_id}: Destination folder already exists!")
        # Check if it has content
        success, stdout, _ = run_s3_cmd("ls", new_path)
        if success and stdout.strip():
            print(f"  {new_id}: Using existing folder")
            # Delete old folder to avoid redundancy
            print(f"  {old_id}: Removing redundant folder...")
            run_s3_cmd("rm", old_path, "--recursive")
            return True
    
    # Copy all files to new location
    print(f"  {old_id} -> {new_id}: Copying files...")
    success, _, stderr = run_s3_cmd("cp", old_path, new_path, "--recursive", "--acl", "public-read")
    if not success:
        print(f"  Error copying: {stderr}")
        return False
    
    # Delete old folder
    print(f"  {old_id}: Removing old folder...")
    run_s3_cmd("rm", old_path, "--recursive")
    
    return True


def update_character_json(char_id: str) -> bool:
    """Update character.json with proper identifier and public URLs."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{char_id}/character.json"
    
    char_data = get_json_from_s3(s3_path)
    if not char_data:
        # Create new character.json
        char_data = {}
    
    details = CHARACTER_DETAILS.get(char_id, {})
    
    # Update fields
    char_data["id"] = char_id
    char_data["name"] = details.get("name", char_id)
    char_data["identifier_in_scene"] = char_id  # Used by pipeline
    char_data["description"] = details.get("description", "")
    char_data["role"] = details.get("role", "character")
    char_data["is_visible"] = details.get("is_visible", True)
    char_data["static_features"] = details.get("static_features", "")
    
    # Build public URLs based on what exists
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{char_id}"
    url_base = f"{S3_BASE_URL}/Characters/{char_id}"
    
    public_urls = {}
    
    # Check for front portrait
    if s3_exists(f"{s3_base}/front.png"):
        public_urls["front"] = f"{url_base}/front.png"
        public_urls["portrait_front"] = f"{url_base}/front.png"
    elif s3_exists(f"{s3_base}/character.png"):
        public_urls["front"] = f"{url_base}/character.png"
        public_urls["portrait_front"] = f"{url_base}/character.png"
    elif s3_exists(f"{s3_base}/character.jpg"):
        public_urls["front"] = f"{url_base}/character.jpg"
        public_urls["portrait_front"] = f"{url_base}/character.jpg"
    
    # Check for side portrait
    if s3_exists(f"{s3_base}/side.png"):
        public_urls["side"] = f"{url_base}/side.png"
        public_urls["portrait_side"] = f"{url_base}/side.png"
    
    # Check for back portrait
    if s3_exists(f"{s3_base}/back.png"):
        public_urls["back"] = f"{url_base}/back.png"
        public_urls["portrait_back"] = f"{url_base}/back.png"
    
    # Check for voice
    for ext in ["m4a", "mp3", "wav"]:
        if s3_exists(f"{s3_base}/voice.{ext}"):
            public_urls["voice"] = f"{url_base}/voice.{ext}"
            break
    
    char_data["public_urls"] = public_urls
    
    # Upload updated character.json
    return upload_json_to_s3(char_data, s3_path)


def create_brand_json():
    """Create/update brand.json with character list."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/brand.json"
    
    brand_data = get_json_from_s3(s3_path) or {}
    
    # Update character list to use actual names
    brand_data["id"] = "intelli-verse-x"
    brand_data["name"] = "Intelli-Verse-X"
    brand_data["characters"] = list(CHARACTER_DETAILS.keys())
    
    return upload_json_to_s3(brand_data, s3_path)


def create_characters_mapping():
    """Create a characters_mapping.json file for reference."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/characters_mapping.json"
    
    mapping_data = {
        "description": "Maps legacy character IDs (C1, C2, etc.) to actual character names",
        "mapping": CHARACTER_MAPPING,
        "characters": {
            char_id: {
                "name": details["name"],
                "role": details["role"],
                "folder": f"Characters/{char_id}/",
            }
            for char_id, details in CHARACTER_DETAILS.items()
        }
    }
    
    return upload_json_to_s3(mapping_data, s3_path)


def main():
    print("=" * 60)
    print("Fixing S3 Character Structure")
    print("=" * 60)
    
    # Step 1: Rename folders
    print("\n--- Step 1: Renaming Character Folders ---")
    for old_id, new_id in CHARACTER_MAPPING.items():
        if old_id != new_id:  # Skip already renamed (C1 -> AUTOcurio)
            rename_character_folder(old_id, new_id)
    
    # Step 2: Update character.json files
    print("\n--- Step 2: Updating character.json Files ---")
    for char_id in CHARACTER_DETAILS.keys():
        print(f"  Updating {char_id}...")
        if update_character_json(char_id):
            print(f"  {char_id}: Updated")
        else:
            print(f"  {char_id}: Failed to update")
    
    # Step 3: Create mapping file
    print("\n--- Step 3: Creating characters_mapping.json ---")
    if create_characters_mapping():
        print("  Created characters_mapping.json")
    else:
        print("  Failed to create characters_mapping.json")
    
    # Step 4: Update brand.json
    print("\n--- Step 4: Updating brand.json ---")
    if create_brand_json():
        print("  Updated brand.json")
    else:
        print("  Failed to update brand.json")
    
    # Final summary
    print("\n" + "=" * 60)
    print("Character Structure Summary")
    print("=" * 60)
    
    for char_id, details in CHARACTER_DETAILS.items():
        print(f"\n{char_id} ({details['role']}):")
        print(f"  Folder: s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{char_id}/")
        print(f"  URL Base: {S3_BASE_URL}/Characters/{char_id}/")
    
    print("\n" + "=" * 60)
    print("Done! Run the podcast pipeline to verify.")
    print("=" * 60)


if __name__ == "__main__":
    main()
