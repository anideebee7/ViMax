# Viral Social Media Pipeline (Shorts/Reels)

The ViMax Viral Social Pipeline is a specialized workflow designed to create high-engagement, short-form content for **YouTube Shorts**, **Instagram Reels**, and **TikTok**. It leverages specialized "Viral Variants" of the core agents to ensure maximum attention capture and retention.

## 1. Specialized Viral Agents

To meet the high demands of social media algorithms, we have introduced dedicated agents that focus exclusively on virality metrics.

### 1.1 Viral Screenwriter (`ViralScreenwriter`)
Located in: `agents/creative/writing/viral.py`
- **Focus:** Psychological hooks and retention loops.
- **Virality Framework:**
    - **The Hook (0-2s):** Verbal or visual shock to stop the scroll.
    - **Retention (2-50s):** Pattern interrupts every 3 seconds to prevent drop-off.
    - **The Loop (58-60s):** Seamless transitions from end to beginning to encourage rewatches.
- **Engagement Bait:** Automatically includes elements designed to trigger comments and shares.

### 1.2 Viral Social Director (`ViralSocialDirector`)
Located in: `agents/directors/social/viral.py`
- **Focus:** High-energy visual language.
- **Visual Language of Virality:**
    - **Aggressive Pacing:** Visual changes/cuts every 1.5-2 seconds.
    - **Dynamic Camera:** Constant movement (zooms, pans, tilts) to keep the eyes engaged.
    - **Aesthetic Mastery:** "Toy-Box" vibrancy for kids' content or "Cinematic High-Contrast" for trending content.

## 2. Pipeline Features
- **Self-Ideation**: Can automatically generate viral ideas using the `IdeationEngine` in `viral` mode.
- **Platform Optimization**: Tailors script and visual direction specifically for TikTok, Reels, or YouTube Shorts.
- **S3 Brand Integration**: Resolves brand/game context to ensure viral content remains on-brand.

## 3. Usage

```python
from pipelines.social import ViralShortsPipeline

# Initialize
pipeline = ViralShortsPipeline.init_from_config("configs/video.yaml")

# Standard Usage (with specific idea)
result = await pipeline(
    idea="3 Life hacks that will save you 100 hours a year",
    platform="TikTok",
    brand_id="intelli-verse-x"
)

# Self-Ideation Mode (auto-generate viral concept)
result = await pipeline(
    auto_ideate=True,
    ideation_mode="viral",
    platform="YouTube Shorts"
)
```

## 4. Output
The pipeline produces:
1. `viral_script.json`: Optimized micro-story with hook and loop details.
2. `director_brief.json`: Pacing and framing instructions for the production engine.
3. `production/`: Complete video output (if `generate_video=True`).
