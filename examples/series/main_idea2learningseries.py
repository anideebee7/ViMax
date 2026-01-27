"""Entry point for Idea to Learning Series pipeline."""

import asyncio
import logging
from pipelines.series.learning import LearningSeriesPipeline

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Topic: AI for Beginners - with QuizVerse branding and Autocurio character
topic = """
Artificial Intelligence (AI):
A beginner-friendly series introducing AI concepts, tools, and practical
applications for students who want to understand and use AI in their daily lives.
"""

learning_goals = """
- Understand what AI is and how it works at a basic level
- Learn to use AI tools like ChatGPT, Claude, and image generators
- Apply AI to automate daily tasks and improve productivity
- Use AI as a learning assistant for studies and job tasks
"""


async def main():
    pipeline = LearningSeriesPipeline.init_from_config("configs/pipelines/learning_series.yaml")
    
    print("🚀 Starting Learning Series Generation...")
    print("   Topic: AI")
    print("   Episodes: 3")
    print("   Duration: 3 minutes each")
    print("   Audience: Students")
    print("   Skill Level: Beginner")
    print("   🎮 Game Branding: QuizVerse (centered watermark)")
    print("   🤖 Featured Character: Autocurio")
    print("   📍 Watermark: QuizVerse logo (centered, 15-20% opacity)")
    print()
    
    # =========================================================================
    # S3 Integration - QuizVerse branding and Autocurio character
    # =========================================================================
    # The pipeline will:
    # 1. Resolve game "quiz-verse" from S3 and download its icon
    # 2. Resolve character "Autocurio" from S3 
    # 3. Use the icon as a centered watermark on all generated images
    # 4. Use Autocurio character in key teaching moments
    # =========================================================================
    
    # Set brand colors for style guidance
    pipeline.brand_colors = "vibrant purple (#8B5CF6), electric blue (#3B82F6), playful pink accents"
    
    result = await pipeline(
        topic=topic,
        num_episodes=3,  # 3 episodes
        episode_duration_minutes=3,  # 3 minutes per episode
        audience="Students who want to learn about Artificial Intelligence",
        skill_level="beginner",
        learning_goals=learning_goals,
        trendy=False,  # Skip trends for faster generation
        generate_images=True,  # Generate segment images
        generate_videos=True,  # Generate actual video clips
        visual_style="modern educational animation style, vibrant purple and blue colors, friendly robot character Autocurio teaching, QuizVerse watermark centered with low opacity",
        max_episodes_to_generate=1,  # Generate 1 episode for testing
        # S3 Integration - resolve game icon and character from S3
        brand_id="intelli-verse-x",  # Parent brand
        game_id="quiz-verse",  # Game with icon at games/quiz-verse/icon.png
        character_names=["Autocurio"],  # Load Autocurio character from S3
        featured_character="Autocurio",  # Autocurio appears in key teaching moments
    )
    
    print("\n" + "="*60)
    print("📚 LEARNING SERIES COMPLETE")
    print("="*60)
    print(f"Run ID: {result['run_id']}")
    print(f"Course: {result['curriculum']['course_title']}")
    print(f"Total duration: {result['curriculum']['total_duration_minutes']} minutes")
    
    # S3 Integration info
    if result.get('app_name'):
        print(f"\n🎮 Branding: {result['app_name']} (icon in top right)")
    if result.get('featured_character'):
        print(f"🤖 Featured Character: {result['featured_character']}")
    
    print(f"\n📺 Episodes ({len(result['curriculum']['episodes'])}):")
    for ep in result['curriculum']['episodes']:
        print(f"   Episode {ep['episode_number']}: {ep['title']}")
        hook_text = ep.get('hook', '')[:50] if ep.get('hook') else 'N/A'
        print(f"      Duration: {ep['duration_minutes']} min | Hook: {hook_text}...")
    
    if result.get('episode_media'):
        print(f"\n🎬 Generated Media:")
        for media in result['episode_media']:
            if media.get('final_video_path'):
                print(f"   ✅ Episode {media['episode_number']}: {media['final_video_path']}")
            elif media.get('segment_images'):
                print(f"   🖼️ Episode {media['episode_number']}: {len(media['segment_images'])} images generated")
    
    print(f"\n💰 Monetization:")
    print(f"   Primary Platform: {result['monetization_plan']['primary_platform']['platform']}")
    strategy = result['monetization_plan']['primary_platform'].get('strategy', '')[:80]
    print(f"   Strategy: {strategy}...")


if __name__ == "__main__":
    asyncio.run(main())
