#!/usr/bin/env python3
"""
ViMax - Unified Pipeline Runner CLI

A single entry point to run any ViMax pipeline with consistent CLI arguments.

Usage:
    python vimax.py <pipeline> [options]
    
Examples:
    python vimax.py video --idea "A story about..." --style "cinematic"
    python vimax.py movie --premise "A sci-fi drama..." --genre "sci-fi"
    python vimax.py short-movie --premise "..." --duration 15
    python vimax.py content-planner
    python vimax.py list  # List all available pipelines
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vimax")


# Pipeline registry - maps CLI names to pipeline classes and config paths
PIPELINES = {
    "video": {
        "module": "pipelines.base.idea",
        "class": "VideoPipeline",
        "config": "configs/pipelines/video.yaml",
        "description": "Generate video from an idea/script",
    },
    "tvseries": {
        "module": "pipelines.series.tv",
        "class": "TVSeriesPipeline",
        "config": "configs/pipelines/movie.yaml",
        "description": "Generate narrative TV series with seasonal arc",
    },
    "movie": {
        "module": "pipelines.movies.standard",
        "class": "MoviePipeline",
        "config": "configs/pipelines/movie.yaml",
        "description": "Generate full movie script and visuals",
    },
    "short-movie": {
        "module": "pipelines.movies.short",
        "class": "ShortMoviePipeline",
        "config": "configs/pipelines/short_movie.yaml",
        "description": "Generate short film (5-20 min) script",
    },
    "short-movie-video": {
        "module": "pipelines.movies.short_video",
        "class": "ShortMovieVideoPipeline",
        "config": "configs/pipelines/short_video.yaml",
        "description": "Generate complete short film video",
    },
    "kids-movie": {
        "module": "pipelines.movies.kids",
        "class": "KidsMoviePipeline",
        "config": "configs/pipelines/kids_movie.yaml",
        "description": "Generate kids movie script",
    },
    "documentary": {
        "module": "pipelines.content.documentary",
        "class": "DocumentaryPipeline",
        "config": "configs/pipelines/documentary.yaml",
        "description": "Generate documentary script and visuals",
    },
    "learning-series": {
        "module": "pipelines.series.learning",
        "class": "LearningSeriesPipeline",
        "config": "configs/pipelines/learning_series.yaml",
        "description": "Generate educational video series",
    },
    "ad": {
        "module": "pipelines.ads.video",
        "class": "AdPipeline",
        "config": "configs/pipelines/ad.yaml",
        "description": "Generate advertisement video",
    },
    "ad-banners": {
        "module": "pipelines.ads.banners",
        "class": "AdBannersPipeline",
        "config": "configs/pipelines/ad_banners.yaml",
        "description": "Generate ad banners (static images)",
    },
    "lyrics": {
        "module": "pipelines.music.lyrics",
        "class": "LyricsPipeline",
        "config": "configs/pipelines/lyrics.yaml",
        "description": "Generate song lyrics from an idea",
    },
    "song": {
        "module": "pipelines.music.song",
        "class": "SongPipeline",
        "config": "configs/pipelines/song.yaml",
        "description": "Generate song lyrics and composition",
    },
    "music-video": {
        "module": "pipelines.music.video",
        "class": "MusicVideoPipeline",
        "config": "configs/pipelines/song2musicvideo.yaml",
        "description": "Generate complete music video from an idea",
    },
    "song2musicvideo": {
        "module": "pipelines.music.song_to_video",
        "class": "Song2MusicVideoPipeline",
        "config": "configs/pipelines/song2musicvideo.yaml",
        "description": "Generate music video from song/lyrics",
    },
    "script2video": {
        "module": "pipelines.base.script",
        "class": "Script2VideoPipeline",
        "config": "configs/pipelines/script2video.yaml",
        "description": "Generate video from existing script",
    },
    "podcast": {
        "module": "pipelines.content.podcast",
        "class": "Podcast2VideoPipeline",
        "config": "configs/pipelines/podcast2video.yaml",
        "description": "Convert podcast to video",
    },
    "novel2movie": {
        "module": "pipelines.movies.novel",
        "class": "Novel2MoviePipeline",
        "config": "configs/pipelines/movie.yaml",  # Uses movie config
        "description": "Adapt novel to movie script",
    },
}


def list_pipelines():
    """Print available pipelines."""
    print("\n📋 Available ViMax Pipelines:\n")
    print(f"{'Pipeline':<25} {'Description'}")
    print("-" * 60)
    for name, info in sorted(PIPELINES.items()):
        print(f"  {name:<23} {info['description']}")
    print("\nUsage: python vimax.py <pipeline> [options]")
    print("       python vimax.py <pipeline> --help  # Show pipeline-specific options\n")


def load_pipeline(name: str):
    """Dynamically load a pipeline class."""
    if name not in PIPELINES:
        logger.error(f"Unknown pipeline: {name}")
        logger.info("Use 'python vimax.py list' to see available pipelines")
        sys.exit(1)
    
    info = PIPELINES[name]
    
    try:
        import importlib
        module = importlib.import_module(info["module"])
        pipeline_class = getattr(module, info["class"])
        return pipeline_class, info["config"]
    except ImportError as e:
        logger.error(f"Failed to import pipeline {name}: {e}")
        sys.exit(1)


def create_parser():
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="ViMax - AI Video Generation Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vimax.py list
  python vimax.py video --idea "A story about robots" --style "animated"
  python vimax.py movie --premise "A sci-fi epic" --genre "sci-fi" --duration 120
  python vimax.py short-movie-video --premise "..." --brand autocurio
        """
    )
    
    parser.add_argument(
        "pipeline",
        nargs="?",
        help="Pipeline to run (use 'list' to see available pipelines)"
    )
    
    # Common arguments
    parser.add_argument("--idea", "-i", help="The idea/concept for content generation")
    parser.add_argument("--premise", "-p", help="Story premise (for movie pipelines)")
    parser.add_argument("--script", "-s", help="Path to script file (for script2video)")
    parser.add_argument("--style", default="cinematic", help="Visual style (default: cinematic)")
    parser.add_argument("--genre", "-g", help="Genre for the content")
    parser.add_argument("--audience", "-a", help="Target audience")
    parser.add_argument("--duration", "-d", type=int, help="Target duration in minutes")
    parser.add_argument("--trendy", action="store_true", help="Include trending topics")
    parser.add_argument("--format", choices=["animated", "live_action"], default="animated",
                       help="Content format")
    
    # S3/Brand integration
    parser.add_argument("--brand", "-b", help="Brand ID for S3 character loading")
    parser.add_argument("--game", help="Game ID for S3 character loading")
    parser.add_argument("--characters", nargs="+", help="Character names to include")
    
    # Pipeline control
    parser.add_argument("--config", "-c", help="Custom config file path")
    parser.add_argument("--force", "-f", action="store_true", help="Force regeneration")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    
    return parser


async def run_pipeline(pipeline_name: str, args: argparse.Namespace) -> Dict[str, Any]:
    """Run the specified pipeline with given arguments."""
    
    PipelineClass, default_config = load_pipeline(pipeline_name)
    config_path = args.config or default_config
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    logger.info(f"🚀 Running {pipeline_name} pipeline...")
    logger.info(f"   Config: {config_path}")
    
    # Initialize pipeline
    pipeline = PipelineClass.init_from_config(config_path)
    
    if args.force:
        pipeline.force_regenerate = True
    
    # Build kwargs based on pipeline type
    kwargs = {}
    
    # Common kwargs
    if args.style:
        kwargs["style"] = args.style
    if args.audience:
        kwargs["audience"] = args.audience
    if args.trendy:
        kwargs["trendy"] = True
    
    # Content-specific kwargs
    if args.idea:
        kwargs["idea"] = args.idea
    if args.premise:
        kwargs["premise"] = args.premise
    if args.genre:
        kwargs["genre"] = args.genre
    if args.duration:
        # Different pipelines use different parameter names
        if "movie" in pipeline_name:
            kwargs["target_runtime_minutes"] = args.duration
        elif "shortmovie" in pipeline_name:
            kwargs["target_duration_minutes"] = args.duration
    
    # S3 integration
    if args.brand:
        kwargs["brand_id"] = args.brand
    if args.game:
        kwargs["game_id"] = args.game
    if args.characters:
        kwargs["character_names"] = args.characters
    
    # Format
    if args.format:
        kwargs["content_format"] = args.format
    
    # Run pipeline
    try:
        result = await pipeline(**kwargs)
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def print_result(result: Dict[str, Any], as_json: bool = False):
    """Print pipeline result."""
    if as_json:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        return
    
    print("\n" + "=" * 60)
    print("✅ Pipeline completed successfully!")
    print("=" * 60)
    
    # Print common fields
    if "run_id" in result:
        print(f"\n📁 Run ID: {result['run_id']}")
    
    if "story" in result:
        print(f"\n📖 Story Preview:\n{result['story'][:500]}...")
    
    if "characters" in result:
        chars = result["characters"]
        if isinstance(chars, list):
            names = [c.get("identifier_in_scene", c.get("name", "?")) for c in chars[:5]]
            print(f"\n👥 Characters: {', '.join(names)}")
    
    if "script" in result:
        script = result["script"]
        if isinstance(script, list):
            print(f"\n🎬 Scenes: {len(script)}")
    
    if "video_path" in result or "final_video" in result:
        video = result.get("video_path") or result.get("final_video")
        print(f"\n🎥 Video: {video}")
    
    if "monetization_plan" in result:
        mp = result["monetization_plan"]
        if isinstance(mp, dict):
            platform = mp.get("primary_platform", {})
            if isinstance(platform, dict):
                print(f"\n💰 Platform: {platform.get('platform', 'N/A')}")


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle special commands
    if not args.pipeline or args.pipeline == "list":
        list_pipelines()
        return
    
    if args.pipeline == "help":
        parser.print_help()
        return
    
    # Validate input
    pipeline_name = args.pipeline.lower().replace("_", "-")
    
    if pipeline_name not in PIPELINES:
        logger.error(f"Unknown pipeline: {args.pipeline}")
        list_pipelines()
        sys.exit(1)
    
    # Check required arguments
    needs_idea = pipeline_name in ["video", "lyrics", "song", "music-video",
                                    "ad", "ad-banners", "learning-series", "tvseries"]
    needs_premise = pipeline_name in ["movie", "short-movie", "short-movie-video",
                                       "kids-movie", "documentary", "tvseries"]
    
    if needs_idea and not args.idea:
        logger.error(f"Pipeline {pipeline_name} requires --idea argument")
        sys.exit(1)
    
    if needs_premise and not args.premise:
        logger.error(f"Pipeline {pipeline_name} requires --premise argument")
        sys.exit(1)
    
    # Run pipeline
    result = asyncio.run(run_pipeline(pipeline_name, args))
    print_result(result, as_json=args.json)


if __name__ == "__main__":
    main()
