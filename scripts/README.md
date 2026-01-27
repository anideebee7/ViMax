# ViMax Scripts

Utility scripts for testing, maintenance, and development.

## Test Scripts

| Script | Description |
|--------|-------------|
| `test_api_smoke.py` | Smoke tests for API endpoints |
| `test_pipelines_workflow.py` | End-to-end pipeline workflow tests |
| `test_content_planner.py` | Content planner tests |
| `validate_content_planner.py` | Content planner validation suite |

## Utility Scripts

| Script | Description |
|--------|-------------|
| `generate_autocurio_movie.py` | Generate sample Autocurio movie |
| `rerun_shortmovie_video.py` | Re-run short movie generation with existing data |

## S3 Character Scripts

Scripts for managing S3 character assets are in `s3_characters/`:

| Script | Description |
|--------|-------------|
| `check_s3_characters.py` | Check S3 character asset status |
| `complete_s3_characters.py` | Complete missing character assets |
| `complete_s3_characters_piapi.py` | Complete assets using PiAPI |
| `fix_character_views.py` | Fix character side/back views |
| `fix_all_character_views.py` | Fix all character views |
| `fix_s3_character_structure.py` | Fix S3 folder structure |
| `generate_character_views.py` | Generate character views |
| `generate_character_views_with_reference.py` | Generate views with reference |
| `update_character_metadata.py` | Update character metadata |

## Running Scripts

```bash
# From project root
cd /path/to/ViMax

# Run a test script
python scripts/test_api_smoke.py

# Run S3 character scripts
python scripts/s3_characters/check_s3_characters.py
```

## Environment

Scripts may require environment variables:

```bash
export OPENAI_API_KEY="your-key"
export PIAPI_API_KEY="your-key"
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

See `docs/API_KEYS_SETUP.md` for complete setup instructions.
