#!/usr/bin/env python3
"""
Fix character side and back views using PiAPI nano-banana-pro (Gemini).
Updates both local files and S3.
"""
import asyncio
import aiohttp
import os
import json
import subprocess
import sys
import tempfile
from typing import Dict, Optional

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Characters to fix (excluding AUTOcurio which is correct)
CHARACTERS_TO_FIX = {
    "DotDot": {
        "description": "Spherical flying drone with pop-out wings and an emoji face screen. Witty expression, compact hovering design.",
        "side_prompt": "Side view of DotDot, a spherical flying drone character with pop-out wings and an emoji face screen displayed on side. 3D animated cartoon style, vibrant colors, kid-friendly, white background. The drone is hovering, shown from a perfect side angle.",
        "back_prompt": "Back view of DotDot, a spherical flying drone character with pop-out wings visible from behind. 3D animated cartoon style, vibrant colors, kid-friendly, white background. The drone is hovering, shown from directly behind, wings and back of spherical body visible."
    },
    "Gloop": {
        "description": "Transparent gelatinous alien being with various small items visibly floating inside the jelly body. Friendly blob-like shape with expressive surface.",
        "side_prompt": "Side view of Gloop, a transparent gelatinous alien character with small items floating inside the jelly body. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Friendly blob-like shape shown from perfect side angle, items visible floating inside.",
        "back_prompt": "Back view of Gloop, a transparent gelatinous alien character with small items floating inside the jelly body. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Blob-like shape shown from directly behind, back surface and floating items visible."
    },
    "NanaNova": {
        "description": "Wise elderly woman with silver hair, a glowing magical walking stick, and warm kind eyes. Wears comfortable, wise-looking robes.",
        "side_prompt": "Side view of Nana Nova, a wise elderly woman with silver hair holding a glowing magical walking stick. Wears comfortable sage robes. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body shown from perfect side angle, warm expression.",
        "back_prompt": "Back view of Nana Nova, a wise elderly woman with silver hair holding a glowing magical walking stick. Wears comfortable sage robes. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body shown from directly behind, robes and silver hair visible."
    },
    "Tinker": {
        "description": "10-year-old inventor kid wearing goggles on head, backpack stuffed with random gadgets and tools, face and clothes smudged with grease. Excited expression.",
        "side_prompt": "Side view of Tinker, a 10-year-old inventor kid wearing goggles on head and a backpack stuffed with gadgets and tools. Clothes smudged with grease. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body shown from perfect side angle, excited pose.",
        "back_prompt": "Back view of Tinker, a 10-year-old inventor kid wearing goggles on head and a backpack stuffed with gadgets and tools visible from behind. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body shown from directly behind, backpack with tools clearly visible."
    },
    "Whispurr": {
        "description": "Fluffy white cat with a magically glowing tail. Mysterious wise eyes, graceful movements.",
        "side_prompt": "Side view of Whispurr, a fluffy white cat with a magically glowing tail. Mysterious wise eyes. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body cat shown from perfect side angle, glowing tail visible, graceful pose.",
        "back_prompt": "Back view of Whispurr, a fluffy white cat with a magically glowing tail. 3D animated cartoon style, vibrant colors, kid-friendly, white background. Full body cat shown from directly behind, fluffy white fur and glowing tail prominently visible."
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
                print(f"  Task created: {task_id}")
                return task_id
            else:
                print(f"  Error creating task: {data}")
                return None
    
    async def poll_task(self, session: aiohttp.ClientSession, task_id: str, timeout: int = 300) -> Optional[str]:
        """Poll task until completion"""
        for i in range(timeout // 5):
            await asyncio.sleep(5)
            async with session.get(
                f"{self.base_url}/{task_id}",
                headers={"X-API-Key": self.api_key}
            ) as resp:
                data = await resp.json()
                status = data["data"]["status"]
                if status == "completed":
                    output = data["data"]["output"]
                    # nano-banana-pro returns images in various formats
                    if "image_urls" in output and output["image_urls"]:
                        return output["image_urls"][0]
                    elif "images" in output and output["images"]:
                        img = output["images"][0]
                        return img.get("url") or img.get("image_url") if isinstance(img, dict) else img
                    elif "image_url" in output:
                        return output["image_url"]
                    print(f"  Completed but no image URL found: {output}")
                    return None
                elif status == "failed":
                    print(f"  Task failed: {data['data'].get('error')}")
                    return None
                print(f"  Polling... ({i*5}s) status: {status}")
        print(f"  Task timed out after {timeout}s")
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
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(await resp.read())
                print(f"  Downloaded to: {local_path}")
                return True
            print(f"  Failed to download: {resp.status}")
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
        print(f"  Uploaded to S3: {s3_path}")
        return True
    print(f"  S3 upload failed: {result.stderr}")
    return False


async def fix_character(generator: NanoBananaProGenerator, char_name: str, char_info: Dict):
    """Fix side and back views for a character"""
    print(f"\n{'='*60}")
    print(f"Fixing {char_name}")
    print(f"{'='*60}")
    
    local_dir = os.path.join(LOCAL_DIR, char_name)
    os.makedirs(local_dir, exist_ok=True)
    
    # Generate and save side view
    print(f"\nGenerating side view for {char_name}...")
    side_url = await generator.generate_image(char_info["side_prompt"])
    if side_url:
        local_side = os.path.join(local_dir, "side.png")
        if await download_image(side_url, local_side):
            s3_key = f"{S3_PREFIX}/{char_name}/side.png"
            upload_to_s3(local_side, s3_key)
    else:
        print(f"  Failed to generate side view for {char_name}")
    
    # Generate and save back view
    print(f"\nGenerating back view for {char_name}...")
    back_url = await generator.generate_image(char_info["back_prompt"])
    if back_url:
        local_back = os.path.join(local_dir, "back.png")
        if await download_image(back_url, local_back):
            s3_key = f"{S3_PREFIX}/{char_name}/back.png"
            upload_to_s3(local_back, s3_key)
    else:
        print(f"  Failed to generate back view for {char_name}")


async def main():
    api_key = os.getenv("PIAPI_API_KEY")
    if not api_key:
        print("Error: PIAPI_API_KEY not set")
        return
    
    generator = NanoBananaProGenerator(api_key)
    
    print("=" * 60)
    print("Fixing Character Side/Back Views using nano-banana-pro")
    print("=" * 60)
    
    for char_name, char_info in CHARACTERS_TO_FIX.items():
        await fix_character(generator, char_name, char_info)
    
    print("\n" + "=" * 60)
    print("All characters processed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
