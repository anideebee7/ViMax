"""Entry point for Song to Music Video pipeline."""

import asyncio
from pipelines.music.song_to_video import Song2MusicVideoPipeline


# Example usage
song_title = "Neon Dreams"
lyrics = """
[Verse 1]
City lights are calling me tonight
Electric pulse beneath the neon glow
Running through the streets, feeling so alive
Dancing in the shadows, letting go

[Chorus]
Neon dreams, neon dreams
We're living in a world of neon dreams
Colors bleeding through the night
Everything feels so right
Neon dreams, neon dreams

[Verse 2]
Skyscrapers reaching for the stars
Music pumping through my veins
This moment's ours, no matter who we are
Washing away all the pain

[Chorus]
Neon dreams, neon dreams
We're living in a world of neon dreams
"""

song_structure = "Intro (0:00-0:15), Verse 1 (0:15-0:45), Chorus (0:45-1:15), Verse 2 (1:15-1:45), Chorus (1:45-2:15), Bridge (2:15-2:45), Final Chorus (2:45-3:15), Outro (3:15-3:30)"


async def main():
    pipeline = Song2MusicVideoPipeline.init_from_config("configs/pipelines/song2musicvideo.yaml")
    result = await pipeline(
        song_title=song_title,
        lyrics=lyrics,
        genre="Synthwave / Electronic Pop",
        mood="Energetic, Euphoric",
        song_structure=song_structure,
        style="cyberpunk, neon-lit cityscapes",
        audience="young adults, music lovers",
        generate_storyboard_images=True,  # Generate key frames
        trendy=True,  # Include trending visual styles
    )
    print(f"Run ID: {result['run_id']}")
    print(f"Concept: {result['concept']['concept_summary']}")
    print(f"Visual approach: {result['concept']['visual_approach']}")
    print(f"Total shots: {len(result['concept']['shots'])}")
    print(f"Storyboard images: {len(result['storyboard_images'])}")
    print(f"Primary platform: {result['monetization_plan']['primary_platform']['platform']}")


if __name__ == "__main__":
    asyncio.run(main())
