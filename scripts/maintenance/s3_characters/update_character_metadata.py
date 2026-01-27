#!/usr/bin/env python3
"""
Update S3 character metadata with official brand descriptions.
Also renames Thinker -> Tinker to match official brand.
"""
import subprocess
import json
import tempfile
import os
from typing import Dict, Optional

S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets/brands/intelli-verse-x"
S3_BASE_URL = f"https://{S3_BUCKET}.s3.us-east-1.amazonaws.com/{S3_PREFIX}"

# Official character details from brand guide
CHARACTER_DETAILS = {
    "AUTOcurio": {
        "name": "AUTOcurio",
        "full_name": "Autocurio",
        "type": "Main Bot",
        "description": "A charming, animated, hyper-curious bot who awakens in the human world with an insatiable desire to understand everything—from toast popping out of a toaster to the meaning of laughter.",
        "appearance": "Metallic and soft-edged design with glowing blue eyes, tiny gears whirring inside, and a holographic chest screen showing emoticons.",
        "voice": "Gentle, curious tone (think Wall-E meets a young Carl Sagan).",
        "personality": "Inquisitive, honest, brave, polite, and sometimes adorably confused.",
        "traits": ["inquisitive", "honest", "brave", "polite", "adorably confused", "curious", "gentle"],
        "role": "main_host",
        "is_visible": True,
        "static_features": "Metallic soft-edged robot with glowing blue eyes, tiny visible gears whirring inside, holographic chest screen displaying emoticons. Gentle and curious demeanor.",
    },
    "DotDot": {
        "name": "DotDot",
        "full_name": "DotDot",
        "type": "Flying Drone Assistant",
        "description": "Autocurio's witty companion who provides explanations and comic relief.",
        "appearance": "Spherical drone with pop-out wings and an emoji face screen.",
        "voice": "Witty and slightly sarcastic.",
        "personality": "Witty, sarcastic, balances Autocurio's earnestness.",
        "traits": ["witty", "sarcastic", "supportive", "comic relief", "explainer"],
        "role": "co_host",
        "is_visible": True,
        "static_features": "Spherical flying drone with pop-out wings and an emoji face screen. Witty expression, compact hovering design.",
    },
    "NanaNova": {
        "name": "Nana Nova",
        "full_name": "Nana Nova",
        "type": "Wise Elder Human",
        "description": "The philosophical voice who teaches lessons through tales and stories about human values.",
        "appearance": "Silver hair, glowing walking stick, warm eyes.",
        "voice": "Warm, wise, storytelling tone.",
        "personality": "Tells stories and human values. The philosophical voice.",
        "traits": ["wise", "warm", "philosophical", "storytelling", "nurturing", "patient"],
        "role": "storyteller",
        "is_visible": True,
        "static_features": "Wise elderly woman with silver hair, a glowing magical walking stick, and warm kind eyes. Wears comfortable, wise-looking robes.",
    },
    "Tinker": {
        "name": "Tinker",
        "full_name": "Tinker",
        "type": "Inventor Kid (Age 10)",
        "description": "A young problem-solver who helps Autocurio interact with human technology.",
        "appearance": "Goggles, backpack with random stuff, always smudged with grease.",
        "voice": "Energetic, enthusiastic kid voice.",
        "personality": "Problem-solver and tinkerer. Resourceful and creative.",
        "traits": ["problem-solver", "resourceful", "creative", "energetic", "enthusiastic", "tinkerer"],
        "role": "expert",
        "is_visible": True,
        "static_features": "10-year-old inventor kid wearing goggles on head, backpack stuffed with random gadgets and tools, face and clothes smudged with grease. Excited expression.",
    },
    "Whispurr": {
        "name": "Whispurr",
        "full_name": "Whispurr",
        "type": "Cat Guide",
        "description": "A silent and mysterious cat who leads Autocurio to hidden wonders, communicating through gestures.",
        "appearance": "Fluffy, white cat with a glowing tail.",
        "voice": "Silent - communicates through gestures and expressions.",
        "personality": "Silent and mysterious, wise and knowing.",
        "traits": ["silent", "mysterious", "wise", "graceful", "knowing", "guide"],
        "role": "guide",
        "is_visible": True,
        "static_features": "Fluffy white cat with a magically glowing tail. Mysterious wise eyes, graceful movements. Communicates through gestures.",
    },
    "Gloop": {
        "name": "Gloop",
        "full_name": "Gloop",
        "type": "Gelatinous Alien Tourist",
        "description": "An alien tourist learning alongside Autocurio, often getting things hilariously wrong.",
        "appearance": "Transparent jelly-like being with items floating inside.",
        "voice": "Speaks in odd metaphors and alien-accented speech.",
        "personality": "Curious, confused, speaks in odd metaphors, gets things hilariously wrong.",
        "traits": ["curious", "confused", "metaphorical", "comedic", "alien", "learning"],
        "role": "co_host",
        "is_visible": True,
        "static_features": "Transparent gelatinous alien being with various small items visibly floating inside the jelly body. Friendly blob-like shape with expressive surface.",
    },
}

# Legacy mapping (for reference and parsed_podcast.json compatibility)
LEGACY_MAPPING = {
    "C1": "AUTOcurio",
    "C2": "DotDot", 
    "C3": "Gloop",
    "C4": "NanaNova",
    "C5": "Tinker",  # Was Thinker, now Tinker
    "C6": "Whispurr",
    "Thinker": "Tinker",  # Alias for scripts that use Thinker
}


def run_s3_cmd(*args) -> tuple:
    """Run AWS S3 command."""
    result = subprocess.run(
        ["aws", "s3", *args],
        capture_output=True,
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


def rename_folder(old_name: str, new_name: str) -> bool:
    """Rename a character folder in S3."""
    old_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{old_name}/"
    new_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{new_name}/"
    
    if not s3_exists(old_path):
        print(f"  {old_name}: Does not exist, skipping rename")
        return False
    
    if s3_exists(new_path):
        print(f"  {new_name}: Already exists")
        return True
    
    print(f"  Renaming {old_name} -> {new_name}...")
    success, _, _ = run_s3_cmd("cp", old_path, new_path, "--recursive", "--acl", "public-read")
    if success:
        run_s3_cmd("rm", old_path, "--recursive")
        return True
    return False


def update_character_json(char_id: str) -> bool:
    """Update character.json with official brand details."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{char_id}/character.json"
    
    details = CHARACTER_DETAILS.get(char_id)
    if not details:
        print(f"  {char_id}: No details found, skipping")
        return False
    
    # Get existing data to preserve public_urls
    existing = get_json_from_s3(s3_path) or {}
    
    # Build updated character data
    char_data = {
        "id": char_id,
        "name": details["name"],
        "full_name": details["full_name"],
        "identifier_in_scene": char_id,
        "type": details["type"],
        "description": details["description"],
        "appearance": details["appearance"],
        "voice": details["voice"],
        "personality": details["personality"],
        "traits": details.get("traits", []),
        "role": details["role"],
        "is_visible": details["is_visible"],
        "static_features": details["static_features"],
        "dynamic_features": "None",
    }
    
    # Add aliases for backward compatibility
    if char_id == "Tinker":
        char_data["aliases"] = ["Thinker", "C5"]
    
    # Build public URLs
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/{char_id}"
    url_base = f"{S3_BASE_URL}/Characters/{char_id}"
    
    public_urls = existing.get("public_urls", {})
    
    # Check for portraits
    for img_name, url_key in [
        ("front.png", "front"), ("character.png", "front"), ("character.jpg", "front"),
        ("side.png", "side"), ("back.png", "back")
    ]:
        if s3_exists(f"{s3_base}/{img_name}"):
            public_urls[url_key] = f"{url_base}/{img_name}"
            public_urls[f"portrait_{url_key}"] = f"{url_base}/{img_name}"
    
    # Check for voice
    for ext in ["m4a", "mp3", "wav"]:
        if s3_exists(f"{s3_base}/voice.{ext}"):
            public_urls["voice"] = f"{url_base}/voice.{ext}"
            break
    
    char_data["public_urls"] = public_urls
    
    return upload_json_to_s3(char_data, s3_path)


def update_brand_json():
    """Update brand.json with series concept."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/brand.json"
    
    brand_data = get_json_from_s3(s3_path) or {}
    
    brand_data["id"] = "intelli-verse-x"
    brand_data["name"] = "Intelli-Verse-X"
    brand_data["series_name"] = "Autocurio"
    brand_data["series_concept"] = "Autocurio is a charming, animated, hyper-curious bot who awakens in the human world with an insatiable desire to understand everything—from toast popping out of a toaster to the meaning of laughter. Each episode is a quick, vibrant, engaging YouTube Short (30–60 seconds) aimed to teach, amuse, and inspire curiosity for all age groups."
    brand_data["look_and_feel"] = {
        "visuals": "Vibrant, high-contrast colors; subtle sci-fi glow; everyday objects made magical through lighting and framing.",
        "pacing": "Snappy, punchy, with quick humor, one question explored per episode.",
        "soundtrack": "Light chimes, synths, whimsical strings."
    }
    brand_data["characters"] = list(CHARACTER_DETAILS.keys())
    
    return upload_json_to_s3(brand_data, s3_path)


def update_mapping_json():
    """Update characters_mapping.json with legacy mappings."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/characters_mapping.json"
    
    mapping_data = {
        "description": "Maps legacy character IDs and aliases to actual character names",
        "mapping": LEGACY_MAPPING,
        "characters": {
            char_id: {
                "name": details["name"],
                "type": details["type"],
                "role": details["role"],
                "folder": f"Characters/{char_id}/",
            }
            for char_id, details in CHARACTER_DETAILS.items()
        }
    }
    
    return upload_json_to_s3(mapping_data, s3_path)


def main():
    print("=" * 60)
    print("Updating Character Metadata with Official Brand Info")
    print("=" * 60)
    
    # Step 1: Rename Thinker to Tinker
    print("\n--- Step 1: Rename Thinker -> Tinker ---")
    if s3_exists(f"s3://{S3_BUCKET}/{S3_PREFIX}/Characters/Thinker/"):
        rename_folder("Thinker", "Tinker")
    else:
        print("  Thinker folder not found (may already be Tinker)")
    
    # Step 2: Update all character.json files
    print("\n--- Step 2: Update character.json files ---")
    for char_id in CHARACTER_DETAILS.keys():
        print(f"  Updating {char_id}...")
        if update_character_json(char_id):
            print(f"    {char_id}: Updated ✓")
        else:
            print(f"    {char_id}: Failed ✗")
    
    # Step 3: Update brand.json
    print("\n--- Step 3: Update brand.json ---")
    if update_brand_json():
        print("  brand.json: Updated ✓")
    else:
        print("  brand.json: Failed ✗")
    
    # Step 4: Update mapping
    print("\n--- Step 4: Update characters_mapping.json ---")
    if update_mapping_json():
        print("  characters_mapping.json: Updated ✓")
    else:
        print("  characters_mapping.json: Failed ✗")
    
    # Summary
    print("\n" + "=" * 60)
    print("Character Summary (Official Brand)")
    print("=" * 60)
    
    for char_id, details in CHARACTER_DETAILS.items():
        print(f"\n{char_id} - {details['type']} ({details['role']})")
        print(f"  Appearance: {details['appearance']}")
        print(f"  Personality: {details['personality']}")
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
    print("\nNOTE: The parsed_podcast.json uses 'Thinker' which now maps to 'Tinker'.")
    print("The pipeline's CHARACTER_MAP should handle this alias.")


if __name__ == "__main__":
    main()
