"""Viral Editor: extracts and optimizes video clips for social media."""

import os
import logging
from typing import List, Dict, Any
from moviepy import VideoFileClip, vfx
import moviepy.video.fx as fx

logger = logging.getLogger(__name__)

def extract_viral_clip(
    source_video_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    target_aspect_ratio: str = "9:16",
    add_hook_text: bool = False,
    hook_text: str = ""
) -> bool:
    """
    Extracts a portion of a video and optimizes it for social media (vertical crop).
    """
    if not os.path.exists(source_video_path):
        logger.error(f"Source video not found: {source_video_path}")
        return False

    try:
        with VideoFileClip(source_video_path) as video:
            # 1. Trim the clip
            clip = video.subclipped(start_time, end_time)
            
            # 2. Handle Aspect Ratio (Crop to Vertical if landscape)
            w, h = clip.size
            if target_aspect_ratio == "9:16":
                target_w = int(h * 9 / 16)
                if w > target_w:
                    # Center crop
                    x_center = w / 2
                    clip = clip.cropped(
                        x1=x_center - target_w / 2,
                        y1=0,
                        x2=x_center + target_w / 2,
                        y2=h
                    )
                elif h < w * 16 / 9:
                    # Tall crop if weird aspect
                    target_h = int(w * 16 / 9)
                    y_center = h / 2
                    clip = clip.cropped(
                        x1=0,
                        y1=max(0, y_center - target_h / 2),
                        x2=w,
                        y2=min(h, y_center + target_h / 2)
                    )

            # 3. Resize to standard social width (1080px height usually)
            if clip.h > 1080:
                clip = clip.resized(height=1080)
            
            # 4. Save
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
            return True
            
    except Exception as e:
        logger.error(f"Failed to extract viral clip: {e}")
        return False

def process_viral_segments(
    source_video_path: str,
    output_dir: str,
    segments: List[Dict[str, Any]]
) -> List[str]:
    """
    Processes multiple viral segments.
    """
    created_paths = []
    for i, seg in enumerate(segments):
        out_path = os.path.join(output_dir, f"viral_clip_{i+1}.mp4")
        success = extract_viral_clip(
            source_video_path=source_video_path,
            output_path=out_path,
            start_time=seg["start_time_seconds"],
            end_time=seg["end_time_seconds"],
            hook_text=seg.get("hook_text", "")
        )
        if success:
            created_paths.append(out_path)
            
            # Write metadata for reference
            meta_path = out_path.replace(".mp4", "_metadata.json")
            with open(meta_path, "w") as f:
                import json
                json.dump(seg, f, indent=2)
                
    return created_paths
