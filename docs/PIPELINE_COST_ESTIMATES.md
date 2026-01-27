# ViMax Pipeline Cost Estimates

This document provides a detailed breakdown of the estimated costs for each content generation pipeline in ViMax. Costs are calculated based on standard API pricing (as of Jan 2026) and typical content length/density.

## Cost Assumptions (Unit Prices)

| Service Type | Provider/Model | Unit | Estimated Cost (USD) |
| :--- | :--- | :--- | :--- |
| **LLM (Efficient)** | Gemini 2.0 Flash | 1M Tokens | $0.25 (avg in/out) |
| **LLM (Premium)** | Grok-3 Beta / GPT-4o | 1M Tokens | $10.00 (avg in/out) |
| **Image Generation** | PiAPI (Flux / Midjourney) | 1 Image | $0.08 |
| **Video Generation** | PiAPI (Veo 3.1 / Luma / Kling) | 5-10s Clip | $0.45 |
| **Voiceover / TTS** | ElevenLabs / OpenAI TTS | 1,000 Chars | $0.15 |

---

## Pipeline Duration & Cost Matrix (Min/Max)

This table shows the minimum and maximum ranges for both duration and total production cost (including visuals and AI reasoning).

| Pipeline | Min Duration | Max Duration | Min Cost (USD) | Max Cost (USD) |
| :--- | :--- | :--- | :--- | :--- |
| **Idea to Movie** | 60 min | 200 min | $145.00 | $480.00 |
| **Short Movie** | 5 min | 20 min | $16.50 | $66.00 |
| **Kids Movie** | 5 min | 90 min | $22.10 | $390.00 |
| **Podcast to Video** | 5 min | 60 min | $22.00 | $265.00 |
| **Viral Shorts** | 15 sec | 60 sec | $4.00 | $16.00 |
| **Idea to Ad (Video)** | 6 sec | 60 sec | $2.00 | $15.00 |
| **Ad Banners** | (Static) | (Static) | $0.50 | $5.00 |
| **Documentary** | 10 min | 60 min | $27.00 | $160.00 |
| **Learning Series** | 1 ep (5m) | 10 eps (20m) | $11.00 | $440.00 |
| **TV Series** | 1 ep (10m) | 10 eps (60m) | $25.00 | $1,350.00 |
| **Music Video** | 2 min | 7 min | $18.00 | $62.00 |

---

## Detailed Series Breakdowns

### 1. TV Series (`tv_series`)
Episodic narrative content with recurring characters and multi-episode arcs.
*   **Structure:** Typically 30-60 minutes per episode.
*   **Complexity:** High (requires multi-scene narrative consistency and character state management).
*   **Cost Drivers:** High shot density (10-12 shots/min) and Grok-3/GPT-4o reasoning for script arcs.
*   **Est. Cost:** ~$2.25 per minute of finished video.

### 2. Learning Series (`learning_series`)
Educational courses structured into lessons and modules.
*   **Structure:** 5-15 minute episodes.
*   **Visuals:** Mix of teacher "talking head" (consistent), b-roll, and diagrams.
*   **Cost Drivers:** Number of episodes and density of educational graphics/diagrams.
*   **Est. Cost:** ~$2.20 per minute of finished video.

### 3. Podcast Series (`podcast2video`)
Dialogue-driven episodes with characters in a fixed studio setting.
*   **Structure:** 15-60 minute conversations.
*   **Visuals:** Consistent background; multi-cam style switching (wide, medium, close-up).
*   **Cost Drivers:** Length of dialogue. Since characters and backgrounds are reused, per-minute cost decreases slightly for longer episodes.
*   **Est. Cost:** ~$4.40 per minute (higher shot density for engagement during dialogue).

### 4. Viral Shorts (`video_shorts`)
Ultra-short content (15-60s) optimized for TikTok/YouTube Shorts.
*   **Duration:** Max 60 seconds.
*   **Visuals:** Very high energy, rapid cuts (0.5s - 1.5s per shot).
*   **Est. Cost:** ~$8.00 - $16.00 per produced short.

---

## Output Metrics & Typical Assets

| Output Type | Avg. LLM Tokens | Avg. Images | Avg. Video Clips |
| :--- | :--- | :--- | :--- |
| **10 min Video** | 150k - 300k | 60 - 80 | 60 - 80 |
| **30 min Episode** | 400k - 800k | 180 - 240 | 180 - 240 |
| **Ad Campaign** | 50k | 15 | - |

---

## Cost Optimization Strategies

1.  **Cache LLM Prompts:** Use prompt caching where available to reduce LLM costs by 50-80%.
2.  **Scene Batching:** Generate multiple image frames in a single grid to save on image generation costs.
3.  **Low-Res Previews:** Generate low-resolution video/images for review before final 4K/HQ rendering.
4.  **Character Reuse:** Use S3-hosted characters (pre-generated portraits) to avoid re-generating character reference images for every shot.
