#!/usr/bin/env python3
"""
Main entry point for Podcast to Video generation.

Converts podcast scripts into complete video episodes using
S3-hosted character assets from the Intelli-Verse-X brand.

Usage:
    python main_podcast2video.py --script <path_to_script> [options]

Examples:
    # Generate full podcast video
    python main_podcast2video.py --script ~/Downloads/podcast_script.pdf

    # Generate first 5 scenes only (for testing)
    python main_podcast2video.py --script ~/Downloads/podcast_script.pdf --max-scenes 5

    # Use custom config
    python main_podcast2video.py --script script.pdf --config configs/pipelines/podcast2video.yaml
"""
import argparse
import asyncio
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipelines.content.podcast import Podcast2VideoPipeline, PodcastConfig


def read_script_file(script_path: str) -> str:
    """Read a script file (supports PDF and text formats)"""
    if script_path.endswith('.pdf'):
        try:
            # Try PyPDF2 first
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(script_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                if text.strip():
                    return text
            except ImportError:
                pass
            
            # Try pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(script_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                if text.strip():
                    return text
            except ImportError:
                pass
            
            # Fallback: read as binary and decode
            with open(script_path, 'rb') as f:
                content = f.read()
                # Try to extract text from binary
                import re
                text_parts = re.findall(rb'[\x20-\x7e\n\r]+', content)
                return b' '.join(text_parts).decode('utf-8', errors='ignore')
                
        except Exception as e:
            logging.warning(f"Failed to read PDF: {e}")
            with open(script_path, 'r', errors='ignore') as f:
                return f.read()
    else:
        with open(script_path, 'r') as f:
            return f.read()


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('.working_dir/podcast/podcast2video.log', mode='a')
        ]
    )


async def main():
    parser = argparse.ArgumentParser(
        description="Convert podcast scripts to video using ViMax and S3 characters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage with default config
    python main_podcast2video.py --script ~/Downloads/podcast.pdf

    # Test with limited scenes
    python main_podcast2video.py --script podcast.pdf --max-scenes 3

    # Use custom brand
    python main_podcast2video.py --script podcast.pdf --brand intelli-verse-x

Environment Variables Required:
    XAI_API_KEY      - xAI/Grok API key for chat model
    GEMINI_API_KEY   - Google Gemini API key for image/video generation
    PIAPI_API_KEY    - PiAPI key for fallback generation (optional)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY - For S3 character access
        """
    )
    
    parser.add_argument(
        "--script", "-s",
        required=True,
        help="Path to podcast script file (PDF or TXT)"
    )
    
    parser.add_argument(
        "--config", "-c",
        default="configs/pipelines/podcast2video.yaml",
        help="Path to configuration file (default: configs/pipelines/podcast2video.yaml)"
    )
    
    parser.add_argument(
        "--brand", "-b",
        default="intelli-verse-x",
        help="Brand ID to load characters from (default: intelli-verse-x)"
    )
    
    parser.add_argument(
        "--max-scenes", "-m",
        type=int,
        default=None,
        help="Maximum number of scenes to generate (for testing)"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        default=".working_dir/podcast",
        help="Output directory for generated files"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only parse the script without generating video"
    )
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Verify script file exists
    if not os.path.exists(args.script):
        logger.error(f"Script file not found: {args.script}")
        sys.exit(1)
    
    # Check required environment variables
    required_vars = ["XAI_API_KEY", "GEMINI_API_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.warning(f"Missing environment variables: {missing}")
        logger.info("Some features may not work without these keys")
    
    logger.info("=" * 60)
    logger.info("ViMax Podcast2Video Pipeline")
    logger.info("=" * 60)
    logger.info(f"Script: {args.script}")
    logger.info(f"Brand: {args.brand}")
    logger.info(f"Config: {args.config}")
    logger.info(f"Output: {args.output_dir}")
    if args.max_scenes:
        logger.info(f"Max scenes: {args.max_scenes}")
    logger.info("=" * 60)
    
    # Create podcast config
    podcast_config = PodcastConfig(
        brand_id=args.brand,
        working_dir=args.output_dir
    )
    
    # Initialize pipeline
    logger.info("Initializing pipeline...")
    try:
        pipeline = Podcast2VideoPipeline.init_from_config(
            args.config,
            podcast_config
        )
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        logger.info("Attempting to continue with basic parsing...")
        pipeline = None
    
    if args.parse_only or pipeline is None:
        # Just parse and show structure
        from agents.producers.analysis import PodcastScriptParser
        parser = PodcastScriptParser()
        
        # Read script
        script_text = read_script_file(args.script)
        
        parsed = parser.parse(script_text)
        
        logger.info("\n" + "=" * 60)
        logger.info("PARSED PODCAST STRUCTURE")
        logger.info("=" * 60)
        logger.info(f"Title: {parsed.title}")
        logger.info(f"Part: {parsed.part}")
        logger.info(f"Total Scenes: {len(parsed.scenes)}")
        logger.info(f"Characters: {parsed.all_characters}")
        logger.info(f"Estimated Duration: {parsed.estimated_total_duration}s ({parsed.estimated_total_duration // 60}min)")
        logger.info("")
        
        for scene in parsed.scenes[:10]:  # Show first 10 scenes
            logger.info(f"Scene {scene.scene_id}: {scene.title[:50]}...")
            logger.info(f"  Type: {scene.scene_type.value}")
            logger.info(f"  Characters: {scene.characters_present}")
            logger.info(f"  Duration: ~{scene.duration_estimate_seconds}s")
        
        if len(parsed.scenes) > 10:
            logger.info(f"  ... and {len(parsed.scenes) - 10} more scenes")
        
        # Save parsed structure
        import json
        output_file = os.path.join(args.output_dir, "parsed_podcast.json")
        with open(output_file, 'w') as f:
            json.dump({
                "title": parsed.title,
                "part": parsed.part,
                "scenes": [
                    {
                        "id": s.scene_id,
                        "title": s.title,
                        "type": s.scene_type.value,
                        "setting": s.setting,
                        "characters": s.characters_present,
                        "duration": s.duration_estimate_seconds
                    }
                    for s in parsed.scenes
                ],
                "all_characters": parsed.all_characters,
                "total_duration": parsed.estimated_total_duration
            }, f, indent=2)
        logger.info(f"\nParsed structure saved to: {output_file}")
        
        if pipeline is None:
            logger.info("\nTo generate video, ensure API keys are set and re-run without --parse-only")
        return
    
    # Run full pipeline
    try:
        final_video = await pipeline.run(
            script_path=args.script,
            max_scenes=args.max_scenes
        )
        
        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Final video: {final_video}")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
