# ViMax Frontend — Migrated to Director

The ViMax API Explorer UI has been **merged into Director’s frontend** as a single deployable app.

## Use the unified app

- **Director frontend**: `Director/frontend`
- Run it and open: **ViMax** → **Home**, **Brands & Games**, **Characters**, **Pipelines**, **Tasks**, **Utilities**
- Set **ViMax API URL** in the header when in the ViMax section (or via `VITE_VIMAX_API_URL`).

## What’s in Director

- **Director** (/) — Chat interface
- **S3** (/s3) — Browse intelli-verse-x-media (videos, images, audio, other files) with copyable public URLs
- **ViMax** (/vimax) — Full ViMax API Explorer: brands, games, characters, 14 pipelines, tasks, utilities

## This folder

This ViMax-only frontend is kept for reference or standalone runs. For new work, use **Director/frontend**.
