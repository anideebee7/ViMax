import asyncio
import os
import json
import logging
from dotenv import load_dotenv
from utils.pipeline.generator_factory import create_video_generator
from utils.core.rate_limiter import RateLimiter

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

RUN_DIR = "/Users/devashishbadlani/dev/ViMax/.working_dir/musicvideo/music_video_20260126_060628_9d3dec9f"
LYRICS_PATH = os.path.join(RUN_DIR, "lyrics.txt")

async def implement_extended_lyrics():
    # 1. Read lyrics
    with open(LYRICS_PATH, "r") as f:
        lyrics_text = f.read()
    
    # Split into sections based on bracketed headers
    sections = []
    current_section = None
    current_lines = []
    
    for line in lyrics_text.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("[") and line.endswith("]"):
            if current_section:
                sections.append({"header": current_section, "lines": "\n".join(current_lines)})
            current_section = line[1:-1]
            current_lines = []
        else:
            current_lines.append(line)
    if current_section:
        sections.append({"header": current_section, "lines": "\n".join(current_lines)})

    print(f"Loaded {len(sections)} sections from lyrics.")

    # 2. Initialize unified video generator with fallback chain:
    # Priority (Veo 3.1 - NEVER CHANGE):
    # 1. KieAI veo3_fast (primary)
    # 2. PiAPI veo3.1 (fallback)
    # 3. Google veo-3.1-generate-preview (last resort)
    rate_limiter = RateLimiter(max_requests_per_minute=2)
    generator = create_video_generator(rate_limiter=rate_limiter)

    # 3. Process sections
    output_path = os.path.join(RUN_DIR, "extended_lyrics_output.json")
    all_videos = []
    if os.path.exists(output_path):
        with open(output_path, "r") as f:
            prev_output = json.load(f)
            all_videos = prev_output.get("sections", [])
            print(f"Resuming from {len(all_videos)} completed sections.")

    last_task_id = all_videos[-1]["task_id"] if all_videos else None
    
    # We'll use the character portraits for the first generation to set the style
    portraits = [
        os.path.join(RUN_DIR, "character_portraits/Captain_Cookie/front.png"),
        os.path.join(RUN_DIR, "character_portraits/Leo_Licorice/front.png"),
        os.path.join(RUN_DIR, "character_portraits/Marshmallow_Giant/front.png")
    ]
    portraits = [p for p in portraits if os.path.exists(p)]

    for i, section in enumerate(sections):
        if i < len(all_videos):
            continue
            
        header = section["header"]
        content = section["lines"]
        print(f"\n🚀 Processing section {i+1}/{len(sections)}: {header}")
        
        prompt = f"Style: Colorful 3D kids animation. Content: {content}. "
        if "Chorus" in header:
            prompt += "Show the Candy Planet and Marshmallow Mountain."
        elif "Giant" in header or "marshmallow giant" in content.lower():
            prompt += "Show the friendly Marshmallow Giant."
        
        video_output = None
        for attempt in range(5):
            try:
                if last_task_id is None:
                    print(f"Generating initial video for: {header} (Attempt {attempt+1})")
                    video_output = await generator.generate_single_video(
                        prompt=prompt,
                        reference_image_paths=portraits,
                        aspect_ratio="16:9"
                    )
                else:
                    print(f"Extending video for: {header} (Task ID: {last_task_id}, Attempt {attempt+1})")
                    video_output = await generator.extend_video(
                        task_id=last_task_id,
                        prompt=prompt
                    )
                break # Success!
            except Exception as e:
                if "HIGH_TRAFFIC" in str(e) and attempt < 4:
                    wait_time = (attempt + 1) * 30
                    print(f"⚠️ High traffic detected. Retrying in {wait_time}s... Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        if not video_output:
            print(f"❌ Failed to process section {header}")
            break

        last_task_id = video_output.metadata.get("task_id")
        video_url = video_output.data
        all_videos.append({"header": header, "url": video_url, "task_id": last_task_id})
        
        # Save intermediate progress
        output_data = {
            "run_id": "extended_lyrics_run",
            "sections": all_videos,
            "final_video_url": all_videos[-1]["url"]
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
            
        print(f"✅ Section {header} completed. URL: {video_url}")

    # 4. Final output
    output_data = {
        "run_id": "extended_lyrics_run",
        "sections": all_videos,
        "final_video_url": all_videos[-1]["url"] if all_videos else None
    }
    
    output_path = os.path.join(RUN_DIR, "extended_lyrics_output.json")
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n🎬 EXTENDED VIDEO COMPLETE!")
    print(f"Final Extended Video URL: {output_data['final_video_url']}")
    print(f"Full metadata saved to: {output_path}")

if __name__ == "__main__":
    asyncio.run(implement_extended_lyrics())
