#!/usr/bin/env python
"""
Generate a 14-minute short movie featuring Autocurio and friends.

Characters:
- Autocurio (Main Bot): Metallic, soft-edged, glowing blue eyes, holographic chest screen
- DotDot (Flying Drone): Spherical, emoji face, witty and sarcastic
- Nana Nova (Wise Elder): Silver hair, glowing walking stick, philosophical
- Tinker (Inventor Kid): 10 years old, goggles, backpack, greasy
- Whispurr (Cat Guide): Fluffy white cat, glowing tail, mysterious
- Gloop (Alien Tourist): Transparent jelly, items floating inside, odd metaphors

Usage:
    uv run python scripts/generate_autocurio_movie.py
"""
import asyncio
import json
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Character definitions to include in the premise
CHARACTERS = """
MAIN CHARACTERS (must appear in the story):

1. **Autocurio** (Protagonist - Curious Robot)
   - Appearance: Metallic and soft-edged design with glowing blue eyes, tiny gears whirring inside, and a holographic chest screen showing emoticons
   - Voice: Gentle, curious tone (think Wall-E meets a young Carl Sagan)
   - Personality: Inquisitive, honest, brave, polite, and sometimes adorably confused
   - Role: Main character discovering and learning about the world

2. **DotDot** (Flying Drone Companion)
   - Appearance: Spherical body, wings that pop out, emoji face screen
   - Personality: Witty, sarcastic, balances Autocurio's earnestness
   - Role: Companion, explainer, comic relief

3. **Nana Nova** (Wise Elder Human)
   - Appearance: Silver hair, glowing walking stick, warm eyes
   - Personality: Tells stories and teaches human values
   - Role: The philosophical voice. Teaches lessons through tales

4. **Tinker** (Inventor Kid, Age 10)
   - Appearance: Goggles on head, backpack full of random gadgets, always smudged with grease
   - Personality: Problem-solver and tinkerer, energetic
   - Role: Helps Autocurio interact with human technology

5. **Whispurr** (Mysterious Cat Guide)
   - Appearance: Fluffy, white fur, glowing magical tail
   - Personality: Silent and mysterious, communicates through gestures and expressions
   - Role: Leads Autocurio to hidden wonders

6. **Gloop** (Gelatinous Alien Tourist)
   - Appearance: Transparent jelly-like being with random items floating inside (keys, buttons, a rubber duck)
   - Personality: Speaks in odd metaphors, gets things hilariously wrong
   - Role: Learns alongside Autocurio, provides comic misunderstandings
"""

PREMISE = f"""
"The City of Hums and Whys"

In a whimsical futuristic city where technology and nature coexist, Autocurio—a gentle, curious robot with glowing blue eyes and a heart full of questions—embarks on a journey to understand what makes humans truly happy.

When Autocurio discovers a mysterious glowing map inside Nana Nova's antique shop, it reveals locations of "The Five Wonders of Joy"—hidden places in the city where humans have experienced their greatest moments of happiness. With the help of friends old and new, Autocurio must visit each wonder before the map's glow fades at sunset.

The adventure takes Autocurio and friends through:
- The Forgotten Garden (where abandoned things find new purpose)
- The Echo Bridge (where whispered wishes come true)
- The Tinker's Workshop (where broken things become extraordinary)
- The Starlight Observatory (where dreams are stored)
- The Heart of the City (where the biggest wonder awaits)

Along the way, Autocurio learns that happiness isn't found in destinations, but in the connections made during the journey—through laughter with DotDot, wisdom from Nana Nova, creativity with Tinker, mystery guided by Whispurr, and the delightful confusion shared with Gloop.

This is a heartwarming animated adventure about friendship, curiosity, and discovering that the best wonders are the friends who help us see them.

{CHARACTERS}
"""


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Autocurio short movie")
    parser.add_argument("--video", action="store_true", help="Generate full video (not just script)")
    parser.add_argument("--max-scenes", type=int, default=None, help="Limit number of scenes (for testing)")
    args = parser.parse_args()
    
    if args.video:
        # Use the end-to-end video pipeline
        from pipelines.movies.short_video import ShortMovieVideoPipeline
        
        logger.info("Initializing Idea2ShortMovieVideo Pipeline (end-to-end with video)...")
        pipeline = ShortMovieVideoPipeline.init_from_config("configs/pipelines/short_video.yaml")
        pipeline.force_regenerate = True
        
        logger.info("Generating 14-minute short movie VIDEO: 'The City of Hums and Whys'")
        logger.info("Characters: Autocurio, DotDot, Nana Nova, Tinker, Whispurr, Gloop")
        
        result = await pipeline(
            premise=PREMISE,
            genre="animated family adventure",
            target_duration_minutes=14,
            audience="family (ages 5+)",
            style="whimsical 3D animation, Pixar-inspired, colorful and warm",
            trendy=False,
            content_format="animated",
            generate_storyboard_images=True,
            generate_videos=True,
            max_scenes=args.max_scenes,
            # S3 Character Integration for consistent character appearance
            # All 6 characters are in S3 (autocurio folder exists)
            brand_id="intelli-verse-x",
            character_names=["autocurio", "DotDot", "NanaNova", "Tinker", "Whispurr", "Gloop"],
        )
    else:
        # Use script-only pipeline (faster)
        from pipelines.movies.standard import MoviePipeline
        
        logger.info("Initializing Idea2Movie Pipeline (script only)...")
        pipeline = MoviePipeline.init_from_config("configs/pipelines/movie.yaml")
        pipeline.force_regenerate = True
        
        logger.info("Generating 14-minute short movie SCRIPT: 'The City of Hums and Whys'")
        logger.info("Characters: Autocurio, DotDot, Nana Nova, Tinker, Whispurr, Gloop")
        logger.info("Tip: Use --video flag to generate full video")
        
        result = await pipeline(
            premise=PREMISE,
            genre="animated family adventure",
            target_runtime_minutes=14,
            audience="family (ages 5+)",
            style="whimsical 3D animation, Pixar-inspired, colorful and warm",
            trendy=False,
            content_format="animated",
        )
    
    logger.info(f"Movie generated! Run ID: {result.get('run_id')}")
    logger.info(f"Output directory: {pipeline.working_dir}")
    
    # Print summary
    print("\n" + "="*80)
    print("SHORT MOVIE GENERATED: 'The City of Hums and Whys'")
    print("="*80)
    print(f"\nGenre: {result.get('genre')}")
    print(f"Duration: {result.get('target_duration_minutes')} minutes")
    print(f"Format: {result.get('content_format')}")
    print(f"Audience: {result.get('audience')}")
    
    # Characters
    print(f"\nCharacters ({len(result.get('characters', []))}):")
    for char in result.get("characters", []):
        print(f"  - {char.get('name', 'Unknown')}: {char.get('role', 'N/A')}")
    
    # Script scenes
    script = result.get("script", [])
    scenes = script if isinstance(script, list) else script.get("scenes", [])
    print(f"\nScript: {len(scenes)} scenes")
    for i, scene in enumerate(scenes[:5], 1):
        if isinstance(scene, dict):
            title = scene.get("title", scene.get("location", scene.get("scene_heading", f"Scene {i}")))
        else:
            title = str(scene)[:50]
        print(f"  {i}. {title}")
    if len(scenes) > 5:
        print(f"  ... and {len(scenes) - 5} more scenes")
    
    # Monetization
    monetization = result.get("monetization_plan", {})
    print(f"\nMonetization Strategy: {monetization.get('primary_strategy', 'N/A')}")
    
    # Video output (if generated)
    if result.get("final_video_path"):
        print(f"\nFinal Video: {result['final_video_path']}")
    elif result.get("scene_outputs"):
        video_count = sum(1 for s in result["scene_outputs"] if s.get("video_path"))
        print(f"\nScene Videos: {video_count} videos generated")
    
    print(f"\nFull output saved to: {pipeline.working_dir}")
    print("="*80)
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
