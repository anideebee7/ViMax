#!/usr/bin/env python3
"""
Basic workflow tests for each ViMax pipeline.

Runs init (from config or with mocks) and a minimal __call__/run to validate
the workflow. Uses trendy=False to avoid trend API when possible. For pipelines
that require image/video/audio, uses mocks where possible or real config when
keys are available.

Pipelines that need real APIs to pass __call__:
  - song: audio_generator (ElevenLabs/PiAPI music). Fails without valid keys.
Pipelines that are slow with mocks (video has many scenes; podcast2video
  runs full video per scene): may need longer timeout.

Usage:
  uv run python scripts/test_pipelines_workflow.py [--filter movie] [--skip-init] [--skip-call]
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import argparse
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Mocks for image/video (used when we bypass init_from_config to avoid API deps)
# ---------------------------------------------------------------------------

from PIL import Image
from interfaces.output.image_output import ImageOutput
from interfaces.output.video_output import VideoOutput

# Minimal valid MP4 (1-frame, 64x64) for video mock. Created once.
_MINIMAL_MP4_BYTES: Optional[bytes] = None


def _get_minimal_mp4_bytes() -> bytes:
    global _MINIMAL_MP4_BYTES
    if _MINIMAL_MP4_BYTES is not None:
        return _MINIMAL_MP4_BYTES
    try:
        from moviepy import ColorClip
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            clip = ColorClip(size=(64, 64), color=(0, 0, 0), duration=0.2)
            clip.write_videofile(
                path, fps=12, codec="libx264", audio=False, logger=None,
                ffmpeg_params=["-movflags", "+faststart"],
            )
            with open(path, "rb") as f:
                _MINIMAL_MP4_BYTES = f.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception as e:
        raise RuntimeError(
            "MockVideoGenerator requires moviepy and ffmpeg to produce valid MP4 for pipeline tests. "
            "Install: pip install moviepy and install ffmpeg. Original error: %s" % e
        ) from e
    return _MINIMAL_MP4_BYTES


class MockImageGenerator:
    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        **kwargs: Any,
    ) -> ImageOutput:
        img = Image.new("RGB", (64, 64), color=(40, 40, 40))
        return ImageOutput("pil", "png", img)


class MockVideoGenerator:
    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> VideoOutput:
        return VideoOutput("bytes", "mp4", _get_minimal_mp4_bytes())


# ---------------------------------------------------------------------------
# Helper: load chat_model, working_dir, trend_analyzer from YAML
# ---------------------------------------------------------------------------

import yaml
from langchain.chat_models import init_chat_model
from utils.pipeline.trend_analyzer import TrendAnalyzer


def _load_config_base(config_path: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))

    def _resolve_env(v: Any) -> Any:
        if not isinstance(v, str):
            return v
        if v.startswith("${") and v.endswith("}"):
            return os.getenv(v[2:-1], "")
        if v.startswith("ENV:"):
            return os.getenv(v[4:], "")
        return v

    def _resolve_path(p: Optional[str]) -> Optional[str]:
        if not p:
            return None
        return p if os.path.isabs(p) else os.path.join(base_dir, p)

    chat_model_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
    chat_model = init_chat_model(**chat_model_args)
    working_dir = _resolve_path(config.get("working_dir")) or config.get("working_dir") or ".working_dir"
    trend_analyzer = None
    if config.get("trend_analyzer"):
        trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])
    return {"chat_model": chat_model, "working_dir": working_dir, "trend_analyzer": trend_analyzer}


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

async def _run_one(
    name: str,
    init_fn,
    call_fn,
    *,
    skip_init: bool = False,
    skip_call: bool = False,
) -> Tuple[bool, Optional[str]]:
    err: Optional[str] = None
    pipeline = None
    try:
        if not skip_init:
            pipeline = init_fn()
        if skip_call or not pipeline:
            return (True, None)
        await call_fn(pipeline)
        return (True, None)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        return (False, err)


def _run_sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if hasattr(asyncio.get_event_loop(), 'run_until_complete') else asyncio.run(coro)


# ---------------------------------------------------------------------------
# Per-pipeline init and call
# ---------------------------------------------------------------------------

def _tests() -> Dict[str, Dict]:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = lambda p: os.path.join(base, "configs", p)

    def movie_init():
        from pipelines.movies.standard import MoviePipeline
        p = MoviePipeline.init_from_config(cfg("movie.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "movie")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def movie_call(p):
        await p(premise="A robot learns to paint.", genre="drama", target_runtime_minutes=70, trendy=False)

    def short_movie_init():
        from pipelines.movies.short import ShortMoviePipeline
        p = ShortMoviePipeline.init_from_config(cfg("short_movie.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "short_movie")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def short_movie_call(p):
        await p(premise="A cat finds a key.", genre="comedy", target_duration_minutes=8, trendy=False)

    def lyrics_init():
        from pipelines.music.lyrics import LyricsPipeline
        p = LyricsPipeline.init_from_config(cfg("lyrics.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "lyrics")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def lyrics_call(p):
        await p(idea="A rainy afternoon.", user_requirement="Calm, introspective.", style="acoustic", trendy=False)

    def documentary_init():
        from pipelines.content.documentary import DocumentaryPipeline
        # Use config; if image/video init fails (missing PIAPI), try minimal
        p = DocumentaryPipeline.init_from_config(cfg("documentary.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "documentary")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def documentary_call(p):
        await p(topic="The history of the pencil.", target_duration_minutes=15, trendy=False)

    def ad_init():
        from pipelines.ads.video import AdPipeline
        b = _load_config_base(cfg("ad.yaml"), base)
        wd = os.path.join(base, ".working_dir", "test_workflow", "ad")
        os.makedirs(wd, exist_ok=True)
        return AdPipeline(
            chat_model=b["chat_model"],
            image_generator=MockImageGenerator(),
            video_generator=MockVideoGenerator(),
            working_dir=wd,
            trend_analyzer=b["trend_analyzer"],
            force_regenerate=True,
        )

    async def ad_call(p):
        await p(brand="TestBrand", product="TestWidget", generate_visuals=False, generate_videos=False)

    def video_init():
        from pipelines.base.idea import VideoPipeline
        # Use movie for chat (gemini); video.yaml may use grok which might not be available
        b = _load_config_base(cfg("movie.yaml"), base)
        wd = os.path.join(base, ".working_dir", "test_workflow", "video")
        os.makedirs(wd, exist_ok=True)
        return VideoPipeline(
            chat_model=b["chat_model"],
            image_generator=MockImageGenerator(),
            video_generator=MockVideoGenerator(),
            working_dir=wd,
            character_portrait_overrides={},
            global_reference_images=[],
            trend_analyzer=b["trend_analyzer"],
            force_regenerate=True,
        )

    async def video_call(p):
        await p(idea="A door opens to a garden.", user_requirement="Short, calm mood.", style="cinematic", trendy=False)

    def script2video_init():
        from pipelines.base.script import Script2VideoPipeline
        # Use movie for chat (gemini); script2video.yaml may use grok which might not be available
        b = _load_config_base(cfg("movie.yaml"), base)
        wd = os.path.join(base, ".working_dir", "test_workflow", "script2video")
        os.makedirs(wd, exist_ok=True)
        return Script2VideoPipeline(
            chat_model=b["chat_model"],
            image_generator=MockImageGenerator(),
            video_generator=MockVideoGenerator(),
            working_dir=wd,
            global_reference_images=[],
            trend_analyzer=b["trend_analyzer"],
            force_regenerate=True,
        )

    async def script2video_call(p):
        script = "Scene 1: A person walks into a sunlit room.\nScene 2: They pause and look out the window."
        await p(script=script, user_requirement="Calm, cinematic.", style="realistic", trendy=False)

    def song_init():
        from pipelines.music.song import SongPipeline
        p = SongPipeline.init_from_config(cfg("song.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "song")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def song_call(p):
        await p(idea="A short jingle about morning coffee.", style="pop", trendy=False)

    def song2musicvideo_init():
        from pipelines.music.song_to_video import Song2MusicVideoPipeline
        p = Song2MusicVideoPipeline.init_from_config(cfg("song2musicvideo.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "song2musicvideo")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def song2musicvideo_call(p):
        await p(
            song_title="Test Song",
            lyrics="Verse: Hello world. Chorus: Sing along.",
            genre="pop",
            mood="upbeat",
            generate_storyboard_images=False,
            trendy=False,
        )

    def kids_movie_init():
        from pipelines.movies.kids import KidsMoviePipeline
        p = KidsMoviePipeline.init_from_config(cfg("kids_movie.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "kids_movie")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def kids_movie_call(p):
        await p(story_idea="A friendly dragon helps a lost bunny.", generate_character_art=False, trendy=False)

    def learning_series_init():
        from pipelines.series.learning import LearningSeriesPipeline
        p = LearningSeriesPipeline.init_from_config(cfg("learning_series.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "learning_series")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def learning_series_call(p):
        await p(topic="Introduction to Python", num_episodes=2, generate_images=False, generate_videos=False, trendy=False)

    def adbanners_init():
        from pipelines.ads.banners import AdBannersPipeline
        p = AdBannersPipeline.init_from_config(cfg("adbanners.yaml"))
        p.force_regenerate = True
        p.base_working_dir = os.path.join(base, ".working_dir", "test_workflow", "adbanners")
        p.working_dir = os.path.join(p.base_working_dir, p.run_id or "run")
        os.makedirs(p.working_dir, exist_ok=True)
        return p

    async def adbanners_call(p):
        await p(brand_or_game="TestGame", entity_type="game", num_concepts=2, sizes=["medium_rectangle"], trendy=False)

    def podcast2video_init():
        from pipelines.content.podcast import Podcast2VideoPipeline, PodcastConfig
        # Use movie for chat (gemini); podcast2video.yaml may use grok which might not be available
        b = _load_config_base(cfg("movie.yaml"), base)
        wd = os.path.join(base, ".working_dir", "test_workflow", "podcast2video")
        os.makedirs(wd, exist_ok=True)
        return Podcast2VideoPipeline(
            chat_model=b["chat_model"],
            image_generator=MockImageGenerator(),
            video_generator=MockVideoGenerator(),
            config=PodcastConfig(working_dir=wd),
            trend_analyzer=b["trend_analyzer"],
        )

    async def podcast2video_call(p):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Test Podcast\n\n## Intro\nHost: Welcome to the show. Today we discuss trees.\n\n## Segment 1\nHost: Trees are important for oxygen.\n")
            path = f.name
        try:
            await p.run(script_path=path, max_scenes=1)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    return {
        "movie": {"init": movie_init, "call": movie_call},
        "short_movie": {"init": short_movie_init, "call": short_movie_call},
        "lyrics": {"init": lyrics_init, "call": lyrics_call},
        "documentary": {"init": documentary_init, "call": documentary_call},
        "ad": {"init": ad_init, "call": ad_call},
        "video": {"init": video_init, "call": video_call},
        "script2video": {"init": script2video_init, "call": script2video_call},
        "song": {"init": song_init, "call": song_call},
        "song2musicvideo": {"init": song2musicvideo_init, "call": song2musicvideo_call},
        "kids_movie": {"init": kids_movie_init, "call": kids_movie_call},
        "learning_series": {"init": learning_series_init, "call": learning_series_call},
        "adbanners": {"init": adbanners_init, "call": adbanners_call},
        "podcast2video": {"init": podcast2video_init, "call": podcast2video_call},
    }


def main():
    ap = argparse.ArgumentParser(description="Run basic workflow tests for ViMax pipelines.")
    ap.add_argument("--filter", "-f", action="append", default=[], help="Run only these pipelines (e.g. -f movie)")
    ap.add_argument("--skip-init", action="store_true", help="Skip init (only for debugging)")
    ap.add_argument("--skip-call", action="store_true", help="Run init only, skip __call__/run")
    args = ap.parse_args()

    tests = _tests()
    if args.filter:
        tests = {k: v for k, v in tests.items() if k in args.filter}
    if not tests:
        print("No pipelines selected.")
        return 1

    ok = 0
    fail = 0
    for name in sorted(tests.keys()):
        t = tests[name]
        print(f"\n--- {name} ---")
        try:
            success, err = asyncio.run(_run_one(name, t["init"], t["call"], skip_init=args.skip_init, skip_call=args.skip_call))
        except Exception as e:
            success, err = False, f"{type(e).__name__}: {e}"
        if success:
            print(f"  OK")
            ok += 1
        else:
            print(f"  FAIL: {err}")
            fail += 1

    print(f"\n--- Done: {ok} passed, {fail} failed ---")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
