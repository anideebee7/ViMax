#!/usr/bin/env python
"""
Rerun the shortmovie_video pipeline using existing script and characters.
"""
import asyncio
import json
import logging
import os
import sys
import shutil
import re
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.movies.short_video import ShortMovieVideoPipeline
from interfaces import CharacterInScene
from utils.core.run_id import generate_run_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def rerun_pipeline(
    characters_path: str,
    run_path: str,
    script_path: str,
    config_path: str = "configs/pipelines/short_video.yaml"
):
    # 1. Load data
    logger.info(f"Loading characters from {characters_path}")
    with open(characters_path, 'r') as f:
        characters_data = json.load(f)
        characters = [CharacterInScene.model_validate(c) for c in characters_data]

    logger.info(f"Loading run data from {run_path}")
    with open(run_path, 'r') as f:
        run_data = json.load(f)

    logger.info(f"Loading script from {script_path}")
    with open(script_path, 'r') as f:
        script_scenes = json.load(f)

    # 2. Initialize pipeline
    logger.info(f"Initializing pipeline from {config_path}")
    pipeline = ShortMovieVideoPipeline.init_from_config(config_path)
    
    # Create a new run ID for the rerun
    new_run_id = generate_run_id("rerun_shortmovie_video")
    pipeline.working_dir = os.path.join(pipeline.base_working_dir, new_run_id)
    os.makedirs(pipeline.working_dir, exist_ok=True)
    logger.info(f"New working directory: {pipeline.working_dir}")

    # 3. Copy original files to new working directory for consistency
    shutil.copy(characters_path, os.path.join(pipeline.working_dir, "characters.json"))
    shutil.copy(script_path, os.path.join(pipeline.working_dir, "script.json"))
    
    # Also check for character_portraits_registry.json in the original directory
    orig_dir = os.path.dirname(characters_path)
    registry_path = os.path.join(orig_dir, "character_portraits_registry.json")
    character_portraits_registry = None
    if os.path.exists(registry_path):
        logger.info(f"Loading character portraits registry from {registry_path}")
        shutil.copy(registry_path, os.path.join(pipeline.working_dir, "character_portraits_registry.json"))
        with open(registry_path, 'r') as f:
            character_portraits_registry = json.load(f)

    # 4. Extract parameters from run_data or use defaults
    premise = run_data.get("premise", "No premise found")
    genre = run_data.get("genre", "drama")
    target_duration_minutes = run_data.get("target_duration_minutes", 15)
    audience = run_data.get("audience", "General")
    style = run_data.get("style", "cinematic")
    content_format = run_data.get("content_format", "animated")
    is_s3_characters = run_data.get("is_s3_characters", False)

    # 5. Manually trigger the visual generation phases
    from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
    
    # Director brief
    logger.info("Generating director brief...")
    director_brief = await pipeline.short_movie_director.direct(
        premise=premise,
        genre=genre,
        target_duration_minutes=target_duration_minutes,
        style=style,
        audience=audience,
        additional_context=f"Rerunning with existing script. Format: {content_format}",
    )

    # Phase 1 reasoning
    write_phase1_reasoning(
        working_dir=pipeline.working_dir,
        pipeline_name="short_video",
        phase_label="Phase 1: Rerun with existing script",
        content_type="script",
        rationale="Rerunning pipeline with a pre-existing script and character set to fix inconsistencies or regenerate visuals.",
        inputs={"premise": premise, "script_scenes_count": len(script_scenes)},
        outputs={"script.json": "Loaded existing script", "characters.json": "Loaded existing characters"}
    )

    # Director reasoning
    write_director_reasoning(
        working_dir=pipeline.working_dir,
        pipeline_name="short_video",
        director_name="ShortMovieDirector",
        rationale="Director brief for the rerun.",
        inputs={"style": style, "genre": genre},
        outputs={"director_brief": "Generated for the rerun"}
    )

    # PHASE 2 & 3: Storyboard and Video Generation
    scene_outputs = []
    scenes_dir = os.path.join(pipeline.working_dir, "scenes")
    os.makedirs(scenes_dir, exist_ok=True)

    for i, scene_script in enumerate(script_scenes):
        scene_num = i + 1
        logger.info(f"Processing scene {scene_num}/{len(script_scenes)}...")
        
        scene_dir = os.path.join(scenes_dir, f"scene_{scene_num:02d}")
        os.makedirs(scene_dir, exist_ok=True)

        scene_output = {
            "scene_number": scene_num,
            "script": scene_script,
            "storyboard_frames": [],
            "video_path": None,
        }

        # Generate storyboard
        try:
            storyboard_response = await pipeline.storyboard_artist.design_storyboard(
                script=scene_script,
                characters=characters,
            )
            shots = (storyboard_response or [])[:10]
            
            shot_video_paths = []
            for j, shot in enumerate(shots):
                frame_num = j + 1
                frame_path = os.path.join(scene_dir, f"frame_{frame_num:02d}.png")
                shot_video_path = os.path.join(scene_dir, f"shot_{frame_num:02d}.mp4")
                
                frame_prompt = getattr(shot, "visual_desc", None) or getattr(shot, "visual_description", None) or str(shot)[:500]
                
                # Character consistency logic
                visible_characters = []
                for c in characters:
                    name = c.identifier_in_scene or ""
                    if not name: continue
                    pattern = rf"(?i)\b({re.escape(name)}|<{re.escape(name)}>)\b"
                    if re.search(pattern, frame_prompt):
                        visible_characters.append(c)
                
                char_appearances = [f"{c.identifier_in_scene}: {c.static_features}" for c in visible_characters if c.static_features]
                if char_appearances:
                    frame_prompt = f"{frame_prompt}. Character appearances: {'; '.join(char_appearances)}"
                
                # ONLY add reference images for characters visible in THIS shot
                shot_reference_images = list(pipeline.global_reference_images)
                if character_portraits_registry:
                    for char in visible_characters:
                        char_id = char.identifier_in_scene
                        if char_id in character_portraits_registry:
                            views = character_portraits_registry[char_id]
                            if "front" in views and views["front"]:
                                portrait_info = views["front"]
                                portrait_path = portrait_info.get("path") if isinstance(portrait_info, dict) else str(portrait_info)
                                if portrait_path and (os.path.exists(portrait_path) or portrait_path.startswith("http")):
                                    shot_reference_images.append({"path": portrait_path, "description": f"{char_id} character reference"})
                
                style_suffix = f", {style} style, {content_format.replace('_', ' ')}"
                ref_paths = pipeline._resolve_ref_paths(shot_reference_images)
                
                # 1. Generate Frame
                image_output = await pipeline.image_generator.generate_single_image(
                    prompt=frame_prompt + style_suffix,
                    reference_image_paths=ref_paths,
                )
                if image_output:
                    image_output.save(frame_path)
                    if character_portraits_registry and visible_characters:
                        pipeline._composite_s3_characters_on_frame(
                            frame_path=frame_path,
                            visible_characters=visible_characters,
                            frame_desc=frame_prompt,
                            character_portraits_registry=character_portraits_registry,
                        )
                    scene_output["storyboard_frames"].append(frame_path)
                    logger.info(f"    Generated frame {frame_num}")

                # 2. Generate Video for this Shot
                if os.path.exists(frame_path):
                    audio_desc = getattr(shot, "audio_desc", "") or ""
                    visual_desc = getattr(shot, "visual_desc", "") or ""
                    
                    # Identify speaking character and their traits
                    speaking_instruction = ""
                    for c in visible_characters:
                        if c.identifier_in_scene and c.identifier_in_scene.lower() in audio_desc.lower():
                            speaking_instruction = f" {c.identifier_in_scene} is speaking their lines with matching mouth movements and expressions. Voice/Tone: {c.voice_description or 'natural'}. Personality: {c.personality or 'expressive'}."
                            break
                    
                    if not speaking_instruction and (":" in audio_desc or "'" in audio_desc):
                        speaking_instruction = " Ensure the character is speaking their lines with matching mouth movements and expressions."
                    
                    video_prompt = f"{visual_desc}. {audio_desc}.{speaking_instruction} {style} style, cinematic motion."
                    
                    # Clamp duration to 4-8 seconds for Veo compatibility
                    duration = shot.duration_seconds or 5
                    if duration < 4:
                        duration = 4
                    elif duration > 8:
                        duration = 8
                    
                    try:
                        video_output = await pipeline.video_generator.generate_single_video(
                            prompt=video_prompt,
                            reference_image_paths=[frame_path],
                            duration=int(duration),
                        )
                        if video_output:
                            video_output.save(shot_video_path)
                            shot_video_paths.append(shot_video_path)
                            logger.info(f"    Generated video for shot {frame_num}")
                    except Exception as e:
                        logger.warning(f"    Video failed for shot {frame_num}: {e}")

            # 3. Concatenate shot videos into scene video
            if shot_video_paths:
                scene_video_path = os.path.join(scene_dir, "scene_video.mp4")
                try:
                    from utils.media.video import concat_videos
                    concat_videos(shot_video_paths, scene_video_path)
                    scene_output["video_path"] = scene_video_path
                    logger.info(f"  Assembled scene {scene_num} video from {len(shot_video_paths)} shots")
                except Exception as e:
                    logger.warning(f"  Failed to assemble scene {scene_num} video: {e}")
                    if shot_video_paths:
                        scene_output["video_path"] = shot_video_paths[0]

        except Exception as e:
            logger.warning(f"  Storyboard failed for scene {scene_num}: {e}")

        scene_outputs.append(scene_output)

    # Phase 4: Concatenate
    from utils.media.video import concat_videos
    final_video_path = os.path.join(pipeline.working_dir, "final_video.mp4")
    video_paths = [s["video_path"] for s in scene_outputs if s["video_path"]]
    if video_paths:
        logger.info(f"Concatenating {len(video_paths)} videos...")
        try:
            concat_videos(video_paths, final_video_path)
            logger.info(f"Final video: {final_video_path}")
        except Exception as e:
            logger.error(f"Concat failed: {e}")

    # Phase 5: Monetization
    monetization_plan = await pipeline.monetization_advisor.advise_for_video(
        title=f"Short Film Rerun",
        description=premise[:500],
        audience=audience,
        duration_seconds=target_duration_minutes * 60,
        genre=genre,
        is_shorts=False,
    )

    # Final output
    result = {
        "run_id": new_run_id,
        "final_video_path": final_video_path,
        "scene_outputs": scene_outputs,
        "monetization_plan": monetization_plan.model_dump(),
    }
    with open(os.path.join(pipeline.working_dir, "shortmovie_video_output.json"), "w") as f:
        json.dump(result, f, indent=2)
    
    logger.info("Rerun complete!")
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rerun shortmovie_video pipeline")
    parser.add_argument("--characters", required=True, help="Path to characters.json")
    parser.add_argument("--run", required=True, help="Path to run.json")
    parser.add_argument("--script", required=True, help="Path to script.json")
    args = parser.parse_args()

    asyncio.run(rerun_pipeline(args.characters, args.run, args.script))
