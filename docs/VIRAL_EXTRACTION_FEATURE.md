# Automatic Viral Short Extraction

All long-form pipelines in ViMax now feature an automatic **Viral Extraction** system. This feature is designed to help creators repurpose their long-form content (movies, documentaries, series, music videos) for social media platforms like **YouTube Shorts**, **Instagram Reels**, and **TikTok**.

## 1. How it Works

The system automatically triggers at the end of any pipeline run where the final video duration exceeds **2 minutes**.

### 1.1 Viral Identification (`ViralFinder` Agent)
- **Agent:** `agents/producers/analysis/viral_finder.py`
- **Logic:** The agent analyzes the full script or scene breakdown of the generated content.
- **Criteria:** It searches for "gold nuggets" based on:
    - **High Conflict:** Dramatic arguments or reveals.
    - **Extreme Beauty:** Visually stunning or highly aesthetic moments.
    - **Shocking Facts:** "I never knew that" moments (especially for documentaries).
    - **Humor:** Unexpected jokes or witty banter.
- **Output:** Identifies 1-3 segments, each **20-40 seconds** long, with specific timestamps and hook recommendations.

### 1.2 Automated Editing (`ViralEditor` Utility)
- **Utility:** `utils/media/viral_editor.py`
- **Actions:**
    - **Extraction:** Trims the identified segments from the master video.
    - **Vertical Optimization:** Automatically applies a **9:16 vertical center-crop** to landscape source material.
    - **Resolution Scaling:** Ensures the output is social-ready (standard 1080px height).
    - **Metadata:** Saves a JSON file for each clip explaining the rationale and suggesting a hook.

## 2. Output Location

All viral clips are stored within the run's working directory in a dedicated folder:
`.working_dir/[pipeline_path]/[run_id]/shorts_viral/`

### 2.1 File Structure:
- `viral_analysis.json`: The full report from the ViralFinder agent.
- `viral_clip_1.mp4`: The first social-ready clip.
- `viral_clip_1_metadata.json`: Context, rationale, and hook text for the clip.
- `viral_clip_2.mp4`: ...and so on.

## 3. Supported Pipelines
The feature is integrated into:
- **Movies:** `MoviePipeline`, `ShortMovieVideoPipeline`.
- **Content:** `DocumentaryPipeline`.
- **Music:** `MusicVideoPipeline`.
- **Series:** `LearningSeriesPipeline`, `TVSeriesPipeline`.
- **Base:** `VideoPipeline`.

## 4. Usage
No extra steps are required. Simply run any of the supported pipelines with a target duration > 2 minutes, and the `shorts_viral` folder will be populated automatically upon completion.
