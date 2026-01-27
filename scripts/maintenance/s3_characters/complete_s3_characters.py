#!/usr/bin/env python3
"""
Complete S3 character assets:
- Generate side/back portraits for characters missing them
- Generate voice for characters missing voice
- Upload all assets to S3
- Update character.json files
"""

import asyncio
import json
import os
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from interfaces import CharacterInScene
from agents.producers.visuals import CharacterPortraitsGenerator
from utils.pipeline.generator_factory import create_image_generator


S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets/brands/intelli-verse-x/Characters"
S3_BASE_URL = f"https://{S3_BUCKET}.s3.amazonaws.com"

CHARACTERS = {
    "C1": {"name": "AutoCurio", "identifier": "AUTOcurio"},
    "C2": {"name": "Dot Dot", "identifier": "DotDot"},
    "C3": {"name": "Gloop", "identifier": "Gloop"},
    "C4": {"name": "NanaNova", "identifier": "NanaNova"},
    "C5": {"name": "Thinker", "identifier": "Thinker"},
    "C6": {"name": "Whispurr", "identifier": "Whispurr"},
}


def s3_download(s3_path: str, local_path: str) -> bool:
    """Download file from S3."""
    result = subprocess.run(
        ["aws", "s3", "cp", s3_path, local_path],
        capture_output=True, text=True
    )
    return result.returncode == 0


def s3_upload(local_path: str, s3_path: str) -> bool:
    """Upload file to S3."""
    result = subprocess.run(
        ["aws", "s3", "cp", local_path, s3_path],
        capture_output=True, text=True
    )
    return result.returncode == 0


def s3_exists(s3_path: str) -> bool:
    """Check if S3 object exists."""
    result = subprocess.run(
        ["aws", "s3", "ls", s3_path],
        capture_output=True, text=True
    )
    return result.returncode == 0 and len(result.stdout.strip()) > 0


def get_character_json(char_id: str) -> Dict:
    """Download and parse character.json from S3."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}/character.json"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    
    if s3_download(s3_path, temp_path):
        with open(temp_path, 'r') as f:
            data = json.load(f)
        os.unlink(temp_path)
        return data
    return {}


def update_character_json(char_id: str, data: Dict) -> bool:
    """Upload updated character.json to S3."""
    s3_path = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}/character.json"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
        json.dump(data, f, indent=2)
        temp_path = f.name
    
    success = s3_upload(temp_path, s3_path)
    os.unlink(temp_path)
    return success


async def generate_voice_elevenlabs(text: str, voice_name: str = "Rachel") -> Optional[bytes]:
    """Generate voice using ElevenLabs API."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("ELEVENLABS_API_KEY not set")
        return None
    
    # Get voice ID for the voice name
    async with aiohttp.ClientSession() as session:
        # List voices to find ID
        async with session.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key}
        ) as resp:
            if resp.status != 200:
                print(f"Failed to list voices: {resp.status}")
                return None
            voices_data = await resp.json()
        
        voice_id = None
        for voice in voices_data.get("voices", []):
            if voice["name"].lower() == voice_name.lower():
                voice_id = voice["voice_id"]
                break
        
        if not voice_id:
            # Use first available voice
            if voices_data.get("voices"):
                voice_id = voices_data["voices"][0]["voice_id"]
                print(f"Using default voice: {voices_data['voices'][0]['name']}")
            else:
                print("No voices available")
                return None
        
        # Generate speech
        async with session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
        ) as resp:
            if resp.status != 200:
                print(f"Failed to generate voice: {resp.status}")
                return None
            return await resp.read()


async def generate_missing_portraits(char_id: str, char_info: Dict, work_dir: Path):
    """Generate missing side/back portraits for a character."""
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}"
    
    # Check what exists
    has_front = s3_exists(f"{s3_base}/character.jpg") or s3_exists(f"{s3_base}/character.png")
    has_side = s3_exists(f"{s3_base}/side.png")
    has_back = s3_exists(f"{s3_base}/back.png")
    
    if has_side and has_back:
        print(f"  {char_id}: All portraits exist, skipping")
        return
    
    if not has_front:
        print(f"  {char_id}: No front portrait, cannot generate side/back")
        return
    
    # Download front portrait
    front_ext = "jpg" if s3_exists(f"{s3_base}/character.jpg") else "png"
    front_local = work_dir / f"{char_id}_front.{front_ext}"
    s3_download(f"{s3_base}/character.{front_ext}", str(front_local))
    
    # Get character data
    char_data = get_character_json(char_id)
    if not char_data:
        print(f"  {char_id}: No character.json found")
        return
    
    # Create CharacterInScene object
    character = CharacterInScene(
        idx=int(char_id[1:]) - 1,
        identifier_in_scene=char_data.get("identifier_in_scene", char_info["identifier"]),
        is_visible=True,
        static_features=char_data.get("static_features", ""),
        dynamic_features=char_data.get("dynamic_features", "None"),
    )
    
    # Initialize unified image generator with fallback chain:
    # 1. Gemini API (primary)
    # 2. PiAPI nano-banana-pro (fallback)
    # 3. KieAI nano-banana-pro (last resort)
    # NEVER change the image model - always use nano-banana-pro
    image_generator = create_image_generator()
    portrait_generator = CharacterPortraitsGenerator(image_generator=image_generator)
    
    # Generate side portrait if missing
    if not has_side:
        print(f"  {char_id}: Generating side portrait...")
        try:
            side_output = await portrait_generator.generate_side_portrait(
                character=character,
                front_image_path=str(front_local),
            )
            side_local = work_dir / f"{char_id}_side.png"
            side_output.save(str(side_local))
            s3_upload(str(side_local), f"{s3_base}/side.png")
            print(f"  {char_id}: Side portrait uploaded")
        except Exception as e:
            print(f"  {char_id}: Failed to generate side portrait: {e}")
    
    # Generate back portrait if missing
    if not has_back:
        print(f"  {char_id}: Generating back portrait...")
        try:
            back_output = await portrait_generator.generate_back_portrait(
                character=character,
                front_image_path=str(front_local),
            )
            back_local = work_dir / f"{char_id}_back.png"
            back_output.save(str(back_local))
            s3_upload(str(back_local), f"{s3_base}/back.png")
            print(f"  {char_id}: Back portrait uploaded")
        except Exception as e:
            print(f"  {char_id}: Failed to generate back portrait: {e}")


async def generate_missing_voice(char_id: str, char_info: Dict, work_dir: Path):
    """Generate voice sample for character if missing."""
    s3_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}"
    
    # Check if voice exists
    has_voice = (
        s3_exists(f"{s3_base}/voice.mp3") or 
        s3_exists(f"{s3_base}/voice.m4a") or
        s3_exists(f"{s3_base}/voice.wav")
    )
    
    if has_voice:
        print(f"  {char_id}: Voice exists, skipping")
        return
    
    print(f"  {char_id}: Generating voice sample...")
    
    # Get character data for voice generation
    char_data = get_character_json(char_id)
    char_name = char_data.get("name", char_info["name"])
    static_features = char_data.get("static_features", "")
    
    # Generate a sample voice line
    sample_text = f"Hello, I am {char_name}. {static_features[:100] if static_features else 'Nice to meet you!'}"
    
    voice_data = await generate_voice_elevenlabs(sample_text)
    if voice_data:
        voice_local = work_dir / f"{char_id}_voice.mp3"
        with open(voice_local, 'wb') as f:
            f.write(voice_data)
        s3_upload(str(voice_local), f"{s3_base}/voice.mp3")
        
        # Update character.json
        if char_data:
            if "media" not in char_data:
                char_data["media"] = {}
            if "voice" not in char_data["media"]:
                char_data["media"]["voice"] = {}
            char_data["media"]["voice"]["sample"] = "voice.mp3"
            char_data["media"]["voice"]["format"] = "mp3"
            update_character_json(char_id, char_data)
        
        print(f"  {char_id}: Voice uploaded")
    else:
        print(f"  {char_id}: Failed to generate voice")


async def update_character_json_with_urls(char_id: str):
    """Update character.json with public URLs."""
    char_data = get_character_json(char_id)
    if not char_data:
        return
    
    s3_base = f"{S3_BASE_URL}/{S3_PREFIX}/{char_id}"
    
    # Add public URLs
    if "public_urls" not in char_data:
        char_data["public_urls"] = {}
    
    # Check and add URLs for all assets
    s3_check_base = f"s3://{S3_BUCKET}/{S3_PREFIX}/{char_id}"
    
    # Portrait URLs
    if s3_exists(f"{s3_check_base}/character.jpg"):
        char_data["public_urls"]["portrait_front"] = f"{s3_base}/character.jpg"
    elif s3_exists(f"{s3_check_base}/character.png"):
        char_data["public_urls"]["portrait_front"] = f"{s3_base}/character.png"
    
    if s3_exists(f"{s3_check_base}/side.png"):
        char_data["public_urls"]["portrait_side"] = f"{s3_base}/side.png"
    
    if s3_exists(f"{s3_check_base}/back.png"):
        char_data["public_urls"]["portrait_back"] = f"{s3_base}/back.png"
    
    # Voice URLs
    if s3_exists(f"{s3_check_base}/voice.mp3"):
        char_data["public_urls"]["voice"] = f"{s3_base}/voice.mp3"
    elif s3_exists(f"{s3_check_base}/voice.m4a"):
        char_data["public_urls"]["voice"] = f"{s3_base}/voice.m4a"
    
    update_character_json(char_id, char_data)
    print(f"  {char_id}: Updated character.json with public URLs")


async def main():
    print("=" * 60)
    print("Completing S3 Character Assets")
    print("=" * 60)
    
    work_dir = Path(tempfile.mkdtemp(prefix="s3_chars_"))
    print(f"Working directory: {work_dir}")
    
    print("\n--- Checking/Generating Portraits ---")
    for char_id, char_info in CHARACTERS.items():
        print(f"\nProcessing {char_id} ({char_info['name']})...")
        await generate_missing_portraits(char_id, char_info, work_dir)
    
    print("\n--- Checking/Generating Voices ---")
    for char_id, char_info in CHARACTERS.items():
        print(f"\nProcessing {char_id} ({char_info['name']})...")
        await generate_missing_voice(char_id, char_info, work_dir)
    
    print("\n--- Updating character.json with Public URLs ---")
    for char_id in CHARACTERS.keys():
        await update_character_json_with_urls(char_id)
    
    print("\n" + "=" * 60)
    print("Done! All characters updated.")
    print("=" * 60)
    
    # Print summary
    print("\nPublic URLs:")
    for char_id, char_info in CHARACTERS.items():
        print(f"\n{char_id} ({char_info['name']}):")
        print(f"  Front: {S3_BASE_URL}/{S3_PREFIX}/{char_id}/character.jpg")
        print(f"  Side:  {S3_BASE_URL}/{S3_PREFIX}/{char_id}/side.png")
        print(f"  Back:  {S3_BASE_URL}/{S3_PREFIX}/{char_id}/back.png")
        print(f"  Voice: {S3_BASE_URL}/{S3_PREFIX}/{char_id}/voice.mp3")


if __name__ == "__main__":
    asyncio.run(main())
