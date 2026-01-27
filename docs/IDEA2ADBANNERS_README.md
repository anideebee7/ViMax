# Idea to Ad Banners Pipeline

Generates **high-converting ad banner images** for brands and games, built for **25%+ CTR** and ready for Google Display, Meta, and programmatic campaigns.

## Features

- **AdBannerIdeator agent**: Banner concepts with headline, CTA, visual prompt, emotional hook, and CTR rationale
- **Three variant styles**: `creative`, `trend`, `high_converting`
- **S3 integration**: Resolve brand/game from `brand_id` / `game_id`; use logos and metadata
- **Trend-aware**: Optional `trendy=True` to feed current trends into ideation
- **Standard ad sizes** (IAB, Google, Meta):

| Size Name           | Dimensions  | Use Case              |
|---------------------|-------------|------------------------|
| medium_rectangle    | 300×250     | IAB, Display           |
| large_rectangle     | 336×280     | Display                |
| leaderboard         | 728×90      | IAB                    |
| wide_skyscraper     | 160×600     | Skyscraper             |
| half_page           | 300×600     | Half-page              |
| mobile_banner       | 320×50      | Mobile                 |
| billboard           | 970×250     | Large leaderboard      |
| facebook_landscape  | 1200×628    | Meta/Google landscape  |
| square_social       | 1080×1080   | Feed square            |
| portrait_story      | 1080×1350   | Stories / Reels        |

## Usage

### From config (recommended)

```python
from pipelines.ads.adbanners_pipeline import AdBannersPipeline

pipeline = AdBannersPipeline.init_from_config("configs/adbanners.yaml")

result = await pipeline(
    brand_or_game="QuizVerse",
    entity_type="game",
    brief="Promote trivia game for app installs. Highlight daily challenges.",
    audience="Mobile gamers 18–35",
    campaign_goal="App installs",
    platforms="Google Display, Meta, TikTok",
    trendy=True,
    game_id="quiz-verse",
    brand_id="intelli-verse-x",
    num_concepts=4,
    sizes=["medium_rectangle", "facebook_landscape", "square_social", "portrait_story"],
)
```

### CLI

```bash
uv run python main_adbanners.py
```

### Output

- `ideation.json`: Banner concepts (headline, CTA, visual_prompt, ctr_rationale, etc.)
- `banners/<style>/`: Images per style (`creative`, `trend`, `high_converting`)
- `adbanners_output.json`: `manifest`, `by_size`, `by_style`, `banners`

## Config

- `configs/adbanners.yaml`: `chat_model`, `image_generator`, `trend_analyzer`, `working_dir`
- Env: `GEMINI_API_KEY`, `PIAPI_API_KEY`, `PIAPI_IMAGE_MODEL`

## Agent: AdBannerIdeator

- **Input**: `brand_or_game`, `entity_type`, `entity_context` (from S3), `brief`, `audience`, `campaign_goal`, `platforms`, `trend_context`, `num_concepts`
- **Output**: `BannerIdeationResult` with `concepts: List[BannerConcept]`
- **BannerConcept**: `style`, `headline`, `subheadline`, `cta_copy`, `visual_prompt`, `emotional_hook`, `urgency_element`, `ctr_rationale`, `recommended_sizes`, `color_direction`
