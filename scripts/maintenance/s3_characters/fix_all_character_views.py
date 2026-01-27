#!/usr/bin/env python3
"""
Fix ALL character side and back views using PiAPI nano-banana-pro (Gemini).
Uses detailed character-specific prompts for consistency.
Updates both local files and S3.
"""
import asyncio
import aiohttp
import os
import json
import subprocess
import sys
from typing import Dict, Optional

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# All characters that need fixing - with detailed descriptions for consistency
CHARACTERS_TO_FIX = {
    "DotDot": {
        "type": "Flying Drone",
        "features": "spherical white/silver drone body, pop-out angular wings, LED emoji face screen showing expressions, small antenna on top, hover jets underneath",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
        "side_prompt": """Full body side view portrait of DotDot, a cute spherical flying drone character.
Key features that MUST be visible:
- Spherical white/silver metallic body
- Pop-out angular wings extending from sides
- Small antenna on top
- Hover jets/thrusters visible underneath
- Shown from PERFECT 90-degree side angle
- Hovering in mid-air
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows
The character should look EXACTLY like a drone, NOT a human or animal.""",
        "back_prompt": """Full body back view portrait of DotDot, a cute spherical flying drone character.
Key features that MUST be visible:
- Back of spherical white/silver metallic body
- Pop-out angular wings visible from behind
- Small antenna on top visible from back
- Hover jets/thrusters underneath
- Shown from DIRECTLY behind (180-degree view)
- Hovering in mid-air
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows
The character should look EXACTLY like a drone, NOT a human or animal. NO face visible."""
    },
    "Gloop": {
        "type": "Gelatinous Alien",
        "features": "transparent/translucent jelly-like blob body, various small objects floating inside (coins, keys, buttons), friendly face with dot eyes and smile on surface, wobbly blob shape",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
        "side_prompt": """Full body side view portrait of Gloop, a friendly gelatinous alien blob character.
Key features that MUST be visible:
- Transparent/translucent jelly-like blob body
- Various small objects visibly floating INSIDE the jelly (coins, keys, buttons, small toys)
- Blob-like rounded shape (NOT human shaped)
- Shown from PERFECT 90-degree side angle
- Slight wobble texture on surface
Style: 3D animated cartoon, vibrant colors, kid-friendly, transparent/see-through body
Background: Pure white, no shadows
The character is a BLOB/SLIME shape, NOT humanoid.""",
        "back_prompt": """Full body back view portrait of Gloop, a friendly gelatinous alien blob character.
Key features that MUST be visible:
- Back of transparent/translucent jelly-like blob body
- Various small objects visibly floating INSIDE the jelly (coins, keys, buttons, small toys)
- Blob-like rounded shape from behind
- Shown from DIRECTLY behind (180-degree view)
- Slight wobble texture on surface
Style: 3D animated cartoon, vibrant colors, kid-friendly, transparent/see-through body
Background: Pure white, no shadows
The character is a BLOB/SLIME shape, NOT humanoid. NO face visible."""
    },
    "NanaNova": {
        "type": "Wise Elderly Woman",
        "features": "elderly woman with silver/white long flowing hair, purple/blue wise robes, glowing magical walking stick/staff, warm kind face, wrinkles showing wisdom",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
        "side_prompt": """Full body side view portrait of Nana Nova, a wise elderly woman character.
Key features that MUST be visible:
- Elderly woman with silver/white long flowing hair
- Wearing comfortable purple/blue sage robes
- Holding a glowing magical walking stick/staff
- Warm posture, slightly hunched with age
- Shown from PERFECT 90-degree side angle
- Full body from head to feet
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows
She should look like a kind grandmother wizard/sage.""",
        "back_prompt": """Full body back view portrait of Nana Nova, a wise elderly woman character.
Key features that MUST be visible:
- Back of elderly woman with silver/white long flowing hair visible
- Back of purple/blue sage robes
- Holding glowing magical walking stick/staff (visible from behind)
- Shown from DIRECTLY behind (180-degree view)
- Full body from head to feet
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows
NO face visible, only back of head and robes."""
    },
    "Tinker": {
        "type": "Inventor Kid",
        "features": "10-year-old boy, goggles on forehead, messy brown hair, grease-smudged face and clothes, oversized backpack stuffed with tools and gadgets, excited expression, work gloves",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
        "side_prompt": """Full body side view portrait of Tinker, a 10-year-old inventor kid character.
Key features that MUST be visible:
- Young boy around 10 years old
- Goggles pushed up on forehead
- Messy brown hair
- Grease smudges on face and clothes
- Large backpack STUFFED with tools, gadgets, wrenches sticking out
- Casual work clothes (overalls or cargo pants)
- Shown from PERFECT 90-degree side angle
- Full body from head to feet
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows""",
        "back_prompt": """Full body back view portrait of Tinker, a 10-year-old inventor kid character.
Key features that MUST be visible:
- Back of young boy around 10 years old
- Back of messy brown hair
- Large backpack STUFFED with tools, gadgets, wrenches, screwdrivers sticking out (main focus)
- Goggles strap visible on back of head
- Shown from DIRECTLY behind (180-degree view)
- Full body from head to feet
Style: 3D animated cartoon, vibrant colors, kid-friendly
Background: Pure white, no shadows
NO face visible, focus on the tool-filled backpack."""
    },
    "Whispurr": {
        "type": "Magical Cat",
        "features": "fluffy white cat, long fur, magical glowing tail (blue/purple glow), mysterious wise green eyes, graceful sitting or standing pose, ethereal/mystical appearance",
        "style": "3D animated cartoon style, vibrant colors, kid-friendly, pure white background",
        "side_prompt": """Full body side view portrait of Whispurr, a magical fluffy white cat character.
Key features that MUST be visible:
- Fluffy white cat with long soft fur
- Magically GLOWING tail (blue/purple ethereal glow)
- Graceful cat body shape
- All four paws visible
- Shown from PERFECT 90-degree side angle
- Sitting or standing gracefully
Style: 3D animated cartoon, vibrant colors, kid-friendly, mystical/ethereal feel
Background: Pure white, no shadows
This is a CAT, not a human. The glowing tail is the key magical feature.""",
        "back_prompt": """Full body back view portrait of Whispurr, a magical fluffy white cat character.
Key features that MUST be visible:
- Back view of fluffy white cat with long soft fur
- Magically GLOWING tail (blue/purple ethereal glow) - main focus
- Fluffy white fur on back
- Pointed cat ears visible from behind
- Shown from DIRECTLY behind (180-degree view)
Style: 3D animated cartoon, vibrant colors, kid-friendly, mystical/ethereal feel
Background: Pure white, no shadows
This is a CAT, not a human. NO face visible. The glowing tail should be prominent."""
    }
}

S3_BUCKET = "intelli-verse-x-media"
S3_PREFIX = "agent-assets/brands/intelli-verse-x/Characters"
LOCAL_DIR = ".working_dir/podcast/character_portraits"


class NanoBananaProGenerator:
    """Generate images using PiAPI nano-banana-pro (Gemini)"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.piapi.ai/api/v1/task"
    
    async def create_task(self, session: aiohttp.ClientSession, prompt: str) -> Optional[str]:
        """Create an image generation task"""
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
        
        try:
            async with session.post(
                self.base_url,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                json=payload
            ) as resp:
                data = await resp.json()
                if data.get("code") == 200:
                    task_id = data["data"]["task_id"]
                    print(f"    Task created: {task_id}")
                    return task_id
                else:
                    print(f"    Error creating task: {data}")
                    return None
        except Exception as e:
            print(f"    Exception creating task: {e}")
            return None
    
    async def poll_task(self, session: aiohttp.ClientSession, task_id: str, timeout: int = 300) -> Optional[str]:
        """Poll task until completion"""
        for i in range(timeout // 5):
            await asyncio.sleep(5)
            try:
                async with session.get(
                    f"{self.base_url}/{task_id}",
                    headers={"X-API-Key": self.api_key}
                ) as resp:
                    data = await resp.json()
                    status = data["data"]["status"]
                    if status == "completed":
                        output = data["data"]["output"]
                        # Handle various response formats
                        if "image_urls" in output and output["image_urls"]:
                            return output["image_urls"][0]
                        elif "images" in output and output["images"]:
                            img = output["images"][0]
                            return img.get("url") or img.get("image_url") if isinstance(img, dict) else img
                        elif "image_url" in output:
                            return output["image_url"]
                        print(f"    Completed but no image URL: {output}")
                        return None
                    elif status == "failed":
                        error = data["data"].get("error", {})
                        print(f"    Task failed: {error}")
                        return None
                    print(f"    Polling... ({i*5}s) status: {status}")
            except Exception as e:
                print(f"    Poll error: {e}")
        print(f"    Task timed out after {timeout}s")
        return None
    
    async def generate_image(self, prompt: str) -> Optional[str]:
        """Generate an image and return the URL"""
        async with aiohttp.ClientSession() as session:
            task_id = await self.create_task(session, prompt)
            if not task_id:
                return None
            return await self.poll_task(session, task_id)


async def download_image(url: str, local_path: str) -> bool:
    """Download image from URL to local path"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(await resp.read())
                    print(f"    Downloaded: {local_path}")
                    return True
                print(f"    Download failed: HTTP {resp.status}")
                return False
    except Exception as e:
        print(f"    Download error: {e}")
        return False


def upload_to_s3(local_path: str, s3_key: str) -> bool:
    """Upload file to S3"""
    s3_path = f"s3://{S3_BUCKET}/{s3_key}"
    result = subprocess.run(
        ["aws", "s3", "cp", local_path, s3_path, "--acl", "public-read"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print(f"    Uploaded to S3: {s3_key}")
        return True
    print(f"    S3 upload failed: {result.stderr}")
    return False


async def fix_character(generator: NanoBananaProGenerator, char_name: str, char_info: Dict) -> Dict[str, bool]:
    """Fix side and back views for a character"""
    print(f"\n{'='*60}")
    print(f"Fixing {char_name} ({char_info['type']})")
    print(f"{'='*60}")
    
    local_dir = os.path.join(LOCAL_DIR, char_name)
    os.makedirs(local_dir, exist_ok=True)
    
    results = {"side": False, "back": False}
    
    # Generate side view
    print(f"\n  Generating SIDE view for {char_name}...")
    side_url = await generator.generate_image(char_info["side_prompt"])
    if side_url:
        local_side = os.path.join(local_dir, "side.png")
        if await download_image(side_url, local_side):
            s3_key = f"{S3_PREFIX}/{char_name}/side.png"
            if upload_to_s3(local_side, s3_key):
                results["side"] = True
                print(f"  ✓ Side view COMPLETE")
    else:
        print(f"  ✗ Failed to generate side view")
    
    # Small delay between requests
    await asyncio.sleep(2)
    
    # Generate back view
    print(f"\n  Generating BACK view for {char_name}...")
    back_url = await generator.generate_image(char_info["back_prompt"])
    if back_url:
        local_back = os.path.join(local_dir, "back.png")
        if await download_image(back_url, local_back):
            s3_key = f"{S3_PREFIX}/{char_name}/back.png"
            if upload_to_s3(local_back, s3_key):
                results["back"] = True
                print(f"  ✓ Back view COMPLETE")
    else:
        print(f"  ✗ Failed to generate back view")
    
    return results


async def main():
    api_key = os.getenv("PIAPI_API_KEY")
    if not api_key:
        print("Error: PIAPI_API_KEY not set")
        return
    
    generator = NanoBananaProGenerator(api_key)
    
    print("=" * 60)
    print("Fixing ALL Character Side/Back Views")
    print("Using PiAPI nano-banana-pro (Gemini)")
    print("=" * 60)
    print(f"Characters to fix: {list(CHARACTERS_TO_FIX.keys())}")
    print(f"Total images to generate: {len(CHARACTERS_TO_FIX) * 2}")
    
    all_results = {}
    
    for char_name, char_info in CHARACTERS_TO_FIX.items():
        results = await fix_character(generator, char_name, char_info)
        all_results[char_name] = results
        
        # Delay between characters to avoid rate limits
        await asyncio.sleep(3)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_success = 0
    total_failed = 0
    
    for char_name, results in all_results.items():
        side_status = "✓" if results["side"] else "✗"
        back_status = "✓" if results["back"] else "✗"
        print(f"  {char_name}: side={side_status} back={back_status}")
        total_success += sum(1 for v in results.values() if v)
        total_failed += sum(1 for v in results.values() if not v)
    
    print(f"\nTotal: {total_success} succeeded, {total_failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
