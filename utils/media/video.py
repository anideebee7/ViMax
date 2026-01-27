import logging
import os
import subprocess
import tempfile
from typing import List

import requests
from tenacity import retry


@retry
def download_video(url, save_path):
    try:
        logging.info(f"Downloading video from {url} to {save_path}")

        response = requests.get(url, stream=True)
        response.raise_for_status()  # 检查请求是否成功
    
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info(f"Video downloaded successfully to {save_path}")
    
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        raise e


def concat_videos(video_paths: List[str], output_path: str) -> str:
    """
    Concatenate multiple video files into a single video using MoviePy.
    Best for smaller numbers of clips or when resizing/composition is needed.
    """
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")
    
    if len(video_paths) == 1:
        # Just copy if only one video
        import shutil
        shutil.copy(video_paths[0], output_path)
        return output_path
    
    try:
        from moviepy import VideoFileClip, concatenate_videoclips
        
        logging.info(f"Concatenating {len(video_paths)} videos via MoviePy...")
        
        # Load all video clips
        clips = []
        for path in video_paths:
            if os.path.exists(path):
                try:
                    clip = VideoFileClip(path)
                    clips.append(clip)
                except Exception as e:
                    logging.warning(f"Failed to load video {path}: {e}")
            else:
                logging.warning(f"Video file not found: {path}")
        
        if not clips:
            raise RuntimeError("No valid video clips to concatenate")
        
        # Concatenate clips
        final_clip = concatenate_videoclips(clips, method="compose")
        
        # Check if clips have audio
        has_audio = any(clip.audio is not None for clip in clips)
        
        # Write output
        if has_audio:
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
        else:
            # No audio in input clips - save without audio (caller should add audio if needed)
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio=False,
                logger=None,
            )
            logging.warning(f"Concatenated video has no audio. Consider adding audio track to {output_path}")
        
        # Clean up
        for clip in clips:
            clip.close()
        final_clip.close()
        
        logging.info(f"Concatenated video saved to {output_path}")
        return output_path
        
    except ImportError:
        logging.warning("MoviePy not found, falling back to ffmpeg_concat_videos")
        return ffmpeg_concat_videos(video_paths, output_path)
    except Exception as e:
        logging.error(f"MoviePy concatenation failed: {e}. Falling back to ffmpeg.")
        return ffmpeg_concat_videos(video_paths, output_path)


def ffmpeg_concat_videos(video_paths: List[str], output_path: str) -> str:
    """
    Concatenate multiple video files into a single video using ffmpeg's concat demuxer.
    Extremely memory efficient and fast. Ideal for long movies (200+ mins).
    """
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")
    
    if len(video_paths) == 1:
        import shutil
        shutil.copy(video_paths[0], output_path)
        return output_path

    # Filter out non-existent files
    valid_paths = [p for p in video_paths if os.path.exists(p)]
    if not valid_paths:
        raise RuntimeError("No valid video files found for ffmpeg concatenation")

    # Create a temporary file for the ffmpeg concat list
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for path in valid_paths:
            # Escape single quotes and format for ffmpeg
            escaped_path = path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
        list_file_path = f.name

    try:
        logging.info(f"Concatenating {len(valid_paths)} videos via ffmpeg concat demuxer...")
        # -f concat: use concat demuxer
        # -safe 0: allow absolute paths
        # -c copy: stream copy (no re-encoding, extremely fast)
        # Note: stream copy only works if all videos have identical encoding/resolution.
        # If they don't, we'd need -filter_complex, but our pipeline ensures consistency.
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.warning(f"ffmpeg stream copy failed, attempting with re-encoding: {result.stderr}")
            # Fallback to re-encoding if stream copy fails (e.g. slight mismatch in parameters)
            # Check if input videos have audio streams
            # Note: ffmpeg will preserve audio if present, or create silent audio if -c:a is specified
            # We use -c:a aac to ensure audio codec compatibility even if input has no audio
            cmd_reencode = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file_path,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",  # Match video duration
                output_path
            ]
            result_re = subprocess.run(cmd_reencode, capture_output=True, text=True)
            if result_re.returncode != 0:
                raise RuntimeError(f"ffmpeg concatenation failed even with re-encoding: {result_re.stderr}")

        logging.info(f"ffmpeg concatenation successful: {output_path}")
        return output_path
    finally:
        if os.path.exists(list_file_path):
            os.remove(list_file_path)
