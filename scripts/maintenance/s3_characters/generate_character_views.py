#!/usr/bin/env python3
"""
Generate side and back views for all characters using nano-banana-pro via PiAPI.
Then upload to S3.
"""

import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
PIAPI_API_KEY = os.getenv("PIAPI_API_KEY", "43277131d16e3b95f3c854343db74a57b14dd4c019d8a196173670e3200a2ad6")
PIAPI_BASE_URL = "https://api.piapi.ai"
S3_BUCKET = "intelli-verse-x-media"
S3_BASE_PATH = "agent-assets/brands/intelli-verse-x/Characters"

# Working directory
WORKING_DIR = Path("/Users/devashishbadlani/dev/ViMax/.working_dir/podcast/character_portraits")

# Character definitions with detailed prompts
CHARACTERS = {
    "autocurio": {
        "type": "Robot",
        "features": "Metallic soft-edged robot with glowing blue eyes, tiny visible gears whirring inside, holographic chest screen displaying emoticons",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
    "DotDot": {
        "type": "Flying Drone",
        "features": "Spherical white/silver drone body, pop-out angular wings, LED emoji face screen showing expressions, small antenna on top, hover jets underneath",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
    "Gloop": {
        "type": "Slime Creature",
        "features": "Translucent green gelatinous blob body, friendly googly eyes floating inside, can form pseudopods and change shape slightly",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
    "NanaNova": {
        "type": "Elderly Wise Character",
        "features": "Grandmotherly figure with silver hair in a bun, warm glowing aura, wears a starry shawl/cape, kind wrinkled face, holding a glowing orb or staff",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
    "Tinker": {
        "type": "Small Inventor Robot",
        "features": "Small boxy robot with multiple tool arms, welding goggles on head, utility belt with gadgets, wheels or tank treads for movement",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
    "Whispurr": {
        "type": "Magical Cat",
        "features": "Ethereal glowing cat with cosmic fur patterns (stars and galaxies), large expressive eyes, flowing wispy tail that trails stardust",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
    },
}


def create_image_task(prompt: str) -> str:
    """Create a nano-banana-pro image generation task."""
    url = f"{PIAPI_BASE_URL}/api/v1/task"
    headers = {
        "x-api-key": PIAPI_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gemini",
        "task_type": "nano-banana-pro",
        "input": {
            "prompt": prompt,
            "output_format": "png",
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "safety_level": "high"
        }
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    if data.get("code") != 200:
        raise Exception(f"API error: {data.get('message', 'Unknown error')}")
    
    return data["data"]["task_id"]


def poll_task(task_id: str, timeout: int = 300) -> str:
    """Poll task until completion and return image URL."""
    url = f"{PIAPI_BASE_URL}/api/v1/task/{task_id}"
    headers = {"x-api-key": PIAPI_API_KEY}
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 200:
            raise Exception(f"API error: {data.get('message', 'Unknown error')}")
        
        task_data = data.get("data", {})
        status = task_data.get("status", "unknown")
        
        elapsed = int(time.time() - start_time)
        print(f"    Polling... ({elapsed}s) status: {status}", flush=True)
        
        if status == "completed":
            output = task_data.get("output", {})
            # Handle different response formats
            if "image_urls" in output and output["image_urls"]:
                return output["image_urls"][0]
            elif "images" in output and output["images"]:
                return output["images"][0].get("url", "")
            elif "image_url" in output:
                return output["image_url"]
            else:
                raise Exception(f"Completed but no image URL found in output: {output}")
        elif status == "failed":
            error = task_data.get("error", {})
            raise Exception(f"Task failed: {error}")
        
        time.sleep(5)
    
    raise Exception(f"Timeout waiting for task {task_id}")


def download_image(url: str, output_path: Path) -> bool:
    """Download image from URL to local path."""
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return True
    except Exception as e:
        print(f"    Error downloading: {e}", flush=True)
        return False


def upload_to_s3(local_path: Path, s3_key: str) -> bool:
    """Upload file to S3 with public-read ACL."""
    try:
        cmd = [
            "aws", "s3", "cp",
            str(local_path),
            f"s3://{S3_BUCKET}/{s3_key}",
            "--acl", "public-read"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"    S3 upload error: {result.stderr}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"    S3 upload exception: {e}", flush=True)
        return False


def generate_view(char_name: str, char_info: dict, view: str) -> bool:
    """Generate a specific view (side or back) for a character."""
    char_dir = WORKING_DIR / char_name
    output_path = char_dir / f"{view}.png"
    s3_key = f"{S3_BASE_PATH}/{char_name}/{view}.png"
    
    # Build prompt based on view
    if view == "side":
        prompt = f"""Full body SIDE VIEW portrait of {char_name}, a {char_info['type']} character.

Key features:
- {char_info['features']}

IMPORTANT:
- Show the character from a PERFECT 90-degree side angle (profile view)
- The character should be facing LEFT or RIGHT, NOT toward the camera
- Full body visible from head to feet/base
- {char_info['style']}
- Pure white background, no shadows, no other objects
- High quality, detailed 3D render"""
    else:  # back
        prompt = f"""Full body BACK VIEW portrait of {char_name}, a {char_info['type']} character.

Key features:
- {char_info['features']}

IMPORTANT:
- Show the character from DIRECTLY BEHIND (180-degree view)
- The character's back should face the camera
- NO face visible - only the back of the character
- Full body visible from head to feet/base
- {char_info['style']}
- Pure white background, no shadows, no other objects
- High quality, detailed 3D render"""
    
    try:
        print(f"  Generating {view.upper()} view for {char_name}...", flush=True)
        
        # Create task
        task_id = create_image_task(prompt)
        print(f"    Task created: {task_id}", flush=True)
        
        # Poll for completion
        image_url = poll_task(task_id)
        print(f"    Image ready: {image_url[:80]}...", flush=True)
        
        # Download locally
        if not download_image(image_url, output_path):
            return False
        print(f"    Downloaded to: {output_path}", flush=True)
        
        # Upload to S3
        if not upload_to_s3(output_path, s3_key):
            return False
        print(f"    Uploaded to S3: {s3_key}", flush=True)
        
        return True
        
    except Exception as e:
        print(f"    ERROR: {e}", flush=True)
        return False


def main():
    print("=" * 60, flush=True)
    print("GENERATING SIDE AND BACK VIEWS FOR ALL CHARACTERS", flush=True)
    print("=" * 60, flush=True)
    print(f"Working directory: {WORKING_DIR}", flush=True)
    print(f"Characters: {list(CHARACTERS.keys())}", flush=True)
    print("", flush=True)
    
    results = {}
    
    for char_name, char_info in CHARACTERS.items():
        print("", flush=True)
        print("=" * 60, flush=True)
        print(f"Processing {char_name} ({char_info['type']})", flush=True)
        print("=" * 60, flush=True)
        
        results[char_name] = {"side": False, "back": False}
        
        # Generate side view
        results[char_name]["side"] = generate_view(char_name, char_info, "side")
        
        # Small delay between requests
        time.sleep(2)
        
        # Generate back view
        results[char_name]["back"] = generate_view(char_name, char_info, "back")
        
        # Delay between characters
        time.sleep(2)
    
    # Print summary
    print("", flush=True)
    print("=" * 60, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 60, flush=True)
    
    for char_name, views in results.items():
        side_status = "✓" if views["side"] else "✗"
        back_status = "✓" if views["back"] else "✗"
        print(f"  {char_name}: side={side_status} back={back_status}", flush=True)
    
    print("", flush=True)
    print("Done!", flush=True)


if __name__ == "__main__":
    main()
