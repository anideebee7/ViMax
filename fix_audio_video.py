#!/usr/bin/env python3
"""Script to regenerate final video with audio for existing run."""
import asyncio
import os
import sys
sys.path.insert(0, '.')

async def fix_audio():
    run_dir = ".working_dir/video/viral_shorts_20260126_222626_fc38fd78/production/scene_0"
    
    if not os.path.exists(run_dir):
        print(f"❌ Run directory not found: {run_dir}")
        return
    
    # Load shot descriptions
    import json
    shots_dir = os.path.join(run_dir, "shots")
    shot_descriptions = []
    for shot_idx in sorted([int(d) for d in os.listdir(shots_dir) if d.isdigit()]):
        shot_desc_path = os.path.join(shots_dir, str(shot_idx), "shot_description.json")
        if os.path.exists(shot_desc_path):
            with open(shot_desc_path, 'r') as f:
                from interfaces.shot_description import ShotDescription
                shot_desc = ShotDescription.model_validate(json.load(f))
                shot_descriptions.append(shot_desc)
    
    print(f"📹 Found {len(shot_descriptions)} shot descriptions")
    
    # Regenerate final video with audio
    final_video_path = os.path.join(run_dir, "final_video.mp4")
    if os.path.exists(final_video_path):
        os.remove(final_video_path)
        print(f"🗑️  Removed old final video")
    
    # Use the concatenation logic from the pipeline
    from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, concatenate_audioclips
    
    video_clips = []
    for shot_description in shot_descriptions:
        s_path = os.path.join(run_dir, "shots", f"{shot_description.idx}", "video.mp4")
        if os.path.exists(s_path):
            video_clips.append(VideoFileClip(s_path))
    
    if video_clips:
        print(f"🎬 Concatenating {len(video_clips)} video clips...")
        final_video = concatenate_videoclips(video_clips)
        
        # Generate audio
        audio_path = os.path.join(run_dir, "final_audio.mp3")
        if not os.path.exists(audio_path):
            print("🎵 Generating audio track...")
            audio_descriptions = []
            for shot_description in shot_descriptions:
                if shot_description.audio_desc and shot_description.audio_desc.strip():
                    audio_descriptions.append(shot_description.audio_desc)
            
            try:
                from tools.audio_generator_elevenlabs import AudioGeneratorElevenLabs
                elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
                if elevenlabs_key:
                    audio_gen = AudioGeneratorElevenLabs(api_key=elevenlabs_key)
                    audio_prompt = " ".join(audio_descriptions) if audio_descriptions else "energetic, upbeat background music for viral short video"
                    total_duration_ms = int(final_video.duration * 1000)
                    await audio_gen.compose_music(
                        prompt=audio_prompt[:500],
                        music_length_ms=total_duration_ms,
                        output_path=audio_path,
                        force_instrumental=len(audio_descriptions) == 0,
                    )
                    print(f"✅ Generated audio: {audio_path}")
                else:
                    print("⚠️  ELEVENLABS_API_KEY not set, skipping audio")
                    audio_path = None
            except Exception as e:
                print(f"⚠️  Audio generation failed: {e}")
                audio_path = None
        
        # Add audio to video
        if audio_path and os.path.exists(audio_path):
            print("🔊 Adding audio to video...")
            audio_clip = AudioFileClip(audio_path)
            if audio_clip.duration > final_video.duration:
                audio_clip = audio_clip.subclip(0, final_video.duration)
            elif audio_clip.duration < final_video.duration:
                loops_needed = int(final_video.duration / audio_clip.duration) + 1
                audio_clips = [audio_clip] * loops_needed
                audio_clip = concatenate_audioclips(audio_clips).subclip(0, final_video.duration)
            
            final_video = final_video.set_audio(audio_clip)
            final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac", preset="medium")
            audio_clip.close()
            print(f"✅ Final video with audio saved: {final_video_path}")
        else:
            final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
            print(f"⚠️  Final video saved without audio: {final_video_path}")
        
        for c in video_clips: c.close()
        final_video.close()
    else:
        print("❌ No video clips found")

if __name__ == "__main__":
    asyncio.run(fix_audio())
