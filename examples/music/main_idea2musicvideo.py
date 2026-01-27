import asyncio
import argparse
import os
from pipelines.music.video import MusicVideoPipeline
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Generate a complete music video from an idea.")
    parser.add_argument("--idea", type=str, help="The idea for the song/video")
    parser.add_argument("--style", type=str, default="pop", help="Music and visual style (pop, rock, etc.)")
    parser.add_argument("--audience", type=str, help="Target audience")
    parser.add_argument("--brand_id", type=str, help="S3 brand ID for consistency")
    parser.add_argument("--game_id", type=str, help="S3 game ID for consistency")
    parser.add_argument("--character_names", type=str, nargs="+", help="S3 character names to include")
    parser.add_argument("--trendy", action="store_true", help="Incorporate real-time trends")
    parser.add_argument("--auto_ideate", action="store_true", help="Automatically generate the idea")
    parser.add_argument("--config", type=str, default="configs/pipelines/song2musicvideo.yaml", help="Path to config file")
    
    args = parser.parse_args()

    if not args.idea and not args.auto_ideate:
        print("❌ Error: Please provide an --idea or use --auto_ideate")
        return

    print(f"🚀 Starting Idea2MusicVideo Pipeline...")
    pipeline = MusicVideoPipeline.init_from_config(args.config)
    
    result = await pipeline(
        idea=args.idea,
        style=args.style,
        audience=args.audience,
        trendy=args.trendy,
        auto_ideate=args.auto_ideate,
        brand_id=args.brand_id,
        game_id=args.game_id,
        character_names=args.character_names
    )
    
    print(f"\n✅ Music Video Generation Complete!")
    print(f"🎬 Video Path: {result['video_path']}")
    print(f"🎵 Audio Path: {result['audio_path']}")
    print(f"📂 Working Directory: {pipeline.working_dir}")

if __name__ == "__main__":
    asyncio.run(main())
