"""Example of running the Idea to Podcast Series Pipeline."""

import asyncio
import os
import logging
from dotenv import load_dotenv

from pipelines.series.podcast import PodcastSeriesPipeline

# Load environment variables
load_dotenv()

async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Path to the config file
    config_path = "configs/pipelines/podcast_series.yaml"
    
    # Initialize the pipeline from config
    pipeline = PodcastSeriesPipeline.init_from_config(config_path)
    
    # Define the series parameters
    topic = "The Future of AI and Human Creativity"
    num_episodes = 3
    episode_duration_minutes = 15
    audience = "Tech enthusiasts and creators"
    series_goals = "Explore how AI is changing art, music, and writing while highlighting the human element."
    visual_style = "futuristic podcast studio with neon accents, sleek and professional"
    
    # Run the pipeline
    print(f"🚀 Starting Idea to Podcast Series Pipeline for topic: {topic}")
    result = await pipeline(
        topic=topic,
        num_episodes=num_episodes,
        episode_duration_minutes=episode_duration_minutes,
        audience=audience,
        series_goals=series_goals,
        visual_style=visual_style,
        trendy=True,  # Incorporate real-time trends
        brand_id="intelli-verse-x",  # Optional: use S3 brand characters
    )
    
    print("\n✅ Podcast Series Generation Complete!")
    print(f"Run ID: {result['run_id']}")
    print(f"Series Title: {result['series_plan']['series_title']}")
    print(f"Number of episodes: {len(result['episode_results'])}")
    
    for ep in result['episode_results']:
        if "error" in ep:
            print(f"❌ Episode {ep['episode_number']}: {ep['error']}")
        else:
            print(f"🎥 Episode {ep['episode_number']}: {ep['title']}")
            print(f"   Video: {ep['video_path']}")
            print(f"   Duration: {ep['duration_seconds']} seconds")

if __name__ == "__main__":
    asyncio.run(main())
