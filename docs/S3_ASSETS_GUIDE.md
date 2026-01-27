S3 Assets Guide (Brands, Games, Characters)
===========================================

This guide documents how to store and reference brand/game data and character
assets in S3 for all ViMax pipelines.

Primary bucket root
-------------------
- `s3://intelli-verse-x-media/agent-assets/`

Required S3 layout
------------------
```
agent-assets/
  brands/
    <brand_id>/
      brand.json
      Logo.png
      Characters/
        <CharacterName>/
          character.json
          front.png
          side.png
          back.png
          voice.mp3 | voice.m4a (optional)
        characters_mapping.json (optional)
      images/
      svgs/
      sounds/
      animations/
  games/
    <game_id>/
      game.json
      icon.png
      Characters/
        <CharacterName>/  # same structure as brand character
```

Brand data (`brand.json`)
-------------------------
Common fields (example from `intelli-verse-x`):
- `id`: brand identifier (folder name)
- `name`: display name
- `description`: short summary
- `media`: references to Logo and assets (relative paths in brand folder)
- `characters`: list of character IDs (folder names)
- `series_name`, `series_concept`, `look_and_feel`
- Optional metadata fields (recommended):
  - `brand_story`
  - `brand_story_sources` (list of URLs)
  - `links` (website, stores, social, etc.)

Game data (`game.json`)
-----------------------
Common fields (example `quiz-verse`):
- `id`, `name`, `description`
- `brand`: brand id
- `platforms`: `["android","ios"]`
- `app_store_links`: e.g. `google_play`, `apple`
- `media.icon.primary`: `icon.png`
- `characters`: list of character IDs (folder names)
- `shared_from_brand`: `true|false`
- Optional enrichment fields (recommended):
  - `genre`: trivia | puzzle | runner | arcade | survival (or custom)
  - `gameplay_summary`: 1–2 sentence overview
  - `engagement_improvements`: list of engagement ideas

Character data (`character.json`)
---------------------------------
Each character folder should contain:
- `character.json` with at least:
  - `id`, `name`, `identifier_in_scene`
  - `public_urls` with keys for `front`, `side`, `back`
- `front.png`, `side.png`, `back.png` (views)
- Optional `voice.*`

Alias mapping (optional)
------------------------
If you use multiple names for the same character in scripts, add:
```
agent-assets/brands/<brand_id>/Characters/characters_mapping.json
{
  "mapping": {
    "AUTOcurio": "autocurio",
    "Autocurio": "autocurio"
  }
}
```

Prompt references (brand/game/character)
----------------------------------------
Pipelines can resolve S3 entities from text using:
- `@brand:intelli-verse-x`
- `@game:quiz-verse`
- `@character:autocurio`

Brand and game names are also matched if they appear in the prompt/script.

Brand/game logos as reference images
------------------------------------
When a brand or game is resolved, the pipeline will download:
- `brands/<brand_id>/<logo.primary>` as a brand logo reference image
- `games/<game_id>/<icon.primary>` as a game icon reference image

These are added to `global_reference_images` so image generation can reuse
logos without manual wiring. If logo/icon paths are missing, the pipeline
falls back gracefully and still generates characters from the script.

How pipelines load assets
-------------------------

1) S3 loader utilities
- `utils/s3_character_loader.py` is the source of truth for S3 structure.
- It can discover characters by listing folders even if `brand.json` is missing.
- It supports aliases via `characters_mapping.json`.

2) Podcast pipeline
- `pipelines/podcast2video_pipeline.py` uses `S3CharacterLoader` and prefers
  public URLs for character portraits; falls back to local downloads.

3) Script/Idea pipelines
- `pipelines/script2video_pipeline.py` and `pipelines/video_pipeline.py`
  accept `characters` and `character_portraits_registry` explicitly.
- For S3-driven runs, use the helper in `utils/s3_character_loader.py`.

Recommended usage patterns
--------------------------

Load brand characters and portrait registry
```
from utils.pipeline.s3_character_loader import load_brand_characters_for_vimax

characters, portrait_registry = load_brand_characters_for_vimax(
    brand_id="intelli-verse-x",
    selected_identifiers=["autocurio", "NanaNova", "Tinker"]
)
```

Pass portraits into Script2VideoPipeline
```
pipeline = Script2VideoPipeline.init_from_config("configs/video_shorts.yaml")
await pipeline(
    script=script,
    user_requirement=user_requirement,
    style=style,
    characters=characters,
    character_portraits_registry=portrait_registry,
)
```

Add brands, games, characters via API
-------------------------------------
The FastAPI service in `api/main.py` supports both manual creation and
AI-assisted generation. All API writes ultimately store data in S3 using the
same folder layout described above.

Start the API server:
```
uv run python -m api.main
```

Manual create (no AI calls):
```
curl -X POST http://localhost:8000/brands \
  -H "Content-Type: application/json" \
  -d '{"name":"My Brand","description":"Short description","tagline":"Tagline"}'

curl -X POST http://localhost:8000/games \
  -H "Content-Type: application/json" \
  -d '{"name":"My Game","description":"Short description","brand_id":"my-brand"}'

curl -X POST "http://localhost:8000/brands/my-brand/characters?generate_images=false&generate_voice=false" \
  -H "Content-Type: application/json" \
  -d '{"name":"Hero","identifier_in_scene":"hero","static_features":"Red jacket"}'
```

AI-assisted generation (requires XAI + PiAPI keys):
```
curl -X POST http://localhost:8000/brands/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A playful edtech brand","generate_logo":true,"num_characters":3}'

curl -X POST http://localhost:8000/games/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A fast trivia game","brand_id":"my-brand","generate_icon":true,"num_characters":3}'

curl -X POST http://localhost:8000/brands/my-brand/characters/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A curious sidekick","generate_images":true,"generate_voice":true}'
```

Validation endpoints:
```
curl http://localhost:8000/validate/brand/my-brand
curl http://localhost:8000/validate/game/my-game
```

Manual add checklist (no API)
-----------------------------
- Create the S3 folder under `brands/<brand_id>/` or `games/<game_id>/`.
- Add `brand.json` or `game.json` with the required fields.
- Add `Logo.png` (brand) or `icon.png` (game).
- Add characters under `Characters/<CharacterName>/` with
  `character.json` and front/side/back images.
- If you use multiple aliases, update `characters_mapping.json`.

Ensure game characters mirror brand characters
```
aws s3 sync \
  s3://intelli-verse-x-media/agent-assets/brands/intelli-verse-x/Characters/ \
  s3://intelli-verse-x-media/agent-assets/games/quiz-verse/Characters/
```

Mirror brand logo as game icon (default policy)
------------------------------------------------
- If a game icon is missing, copy `brands/<brand_id>/Logo.png` to
  `games/<game_id>/icon.png`.
- If an app-store icon is available, prefer that and keep `Logo.png` as fallback.

Env variables
-------------
Set in `.env`:
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- `AWS_S3_BUCKET_NAME=intelli-verse-x-media`
- `S3_ASSET_PREFIX=agent-assets`

Operational scripts (S3 maintenance)
------------------------------------
Located in `scripts/`:
- `check_s3_characters.py`: audit character folders/assets
- `complete_s3_characters.py`: fill missing views for characters
- `complete_s3_characters_piapi.py`: same using PiAPI
- `generate_character_views*.py`: generate views from reference images
- `fix_*`: structure/metadata repair
- `update_character_metadata.py`: update character.json fields

Best practices
--------------
- Keep folder names stable; use `characters_mapping.json` for aliases.
- Always include `character.json` + front/side/back images.
- Store public URLs in `character.json` if you want pipelines to avoid downloads.
- Keep `brand.json` and `game.json` aligned with S3 folder names.
