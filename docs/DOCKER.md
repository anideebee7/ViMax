# ViMax – Docker

ViMax is dockerized as two services: **API** (FastAPI) and **Frontend** (Vue + Vite API Explorer).

## Prerequisites

- Docker and Docker Compose
- `.env` at the ViMax repo root (copy from `.env.example`; set API keys, S3, etc.)

## Quick start

```bash
# From the ViMax repo root
cp .env.example .env
# Edit .env (XAI/GEMINI/PIAPI, ElevenLabs, AWS S3, etc.)

docker compose up --build
```

- **API**: http://localhost:8000  
- **Frontend**: http://localhost:5173  

The frontend expects `VITE_API_URL=http://localhost:8000` (set in `docker-compose`); the browser uses that to call the API.

## Services

| Service    | Image                 | Port | Description                         |
|-----------|------------------------|------|-------------------------------------|
| `api`     | vimax-api:latest       | 8000 | FastAPI – brands, games, characters, pipelines |
| `frontend`| vimax-frontend:latest  | 5173 | Vue API Explorer (Vite dev server)  |

## Development

The default `docker compose` setup uses **dev** commands and **bind mounts**:

- API: `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload` with the repo root mounted at `/app`
- Frontend: `npm run dev` with `./frontend` mounted at `/app` and a `node_modules` volume

## Build only

```bash
docker compose build
```

## Run in background

```bash
docker compose up -d --build
```

## Dockerfiles

- **API**: `Dockerfile` in the repo root — Python 3.12, `pip install -r requirements.txt`, `uvicorn api.main:app`. The `requirements.txt` mirrors `pyproject.toml` deps for Docker; for local dev you can use `uv sync` and `uv run uvicorn api.main:app`.
- **Frontend**: `frontend/Dockerfile` — Node 22, `npm install`, `npm run dev` on port 5173.

## .dockerignore

- **Root (API image)**: `frontend/`, `.git/`, `.venv/`, `__pycache__/`, `.env`, `.tmp_s3/`, `.tmp_s3games/`, etc.
- **frontend/**: `node_modules/`, `dist/`, `.env`, etc.

## Production

For production, build the frontend (`npm run build`) and serve `dist/` with nginx or another static server, and run the API with `uvicorn` (no `--reload`). You can override the `command` in `docker-compose` or use a separate `docker-compose.prod.yml`.
