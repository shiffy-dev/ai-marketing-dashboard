# ai-marketing-dashboard

AI marketing dashboard for the UAE market. It shows the top 10 trending YouTube videos and Instagram Reels and explains *why* each one is performing, for ecommerce marketing teams.

```
backend/   FastAPI + SQLAlchemy (SQLite) API
frontend/  React (Vite) + Tailwind UI
data/      SQLite DB (gitignored) and static datasets
scripts/   prewarm.py and other utilities
```

## Setup

Requires Python 3.10+, Node 20+, and [Ollama](https://ollama.com) for local LLM analysis (no paid APIs).

```bash
ollama pull qwen3:8b        # one-time model download (~5 GB)
ollama serve                # starts the local model server on http://localhost:11434
```

Create a `.env` file in the repo root:

```bash
YOUTUBE_API_KEY=...
LLM_PROVIDER=ollama                    # or "mock" for offline UI development
LLM_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

`.env` is gitignored. Never commit real keys.

## Run the backend

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

The SQLite database is created at `data/dashboard.db` on first start.

## Run the frontend

Requires Node 20+.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/static` to the backend on port 8000 (override with `VITE_BACKEND_URL`). The trending list loads instantly; cards show "Analysis pending" until an analysis has been generated (page loads never trigger local inference). Open a card and click **Analyze now**, or run `prewarm.py` to analyze everything offline. Click a card for the full Hook / Body / CTA and "Why it's performing" breakdown.

Design tokens (colours, type scale, radii, shadows) live in `frontend/tailwind.config.js` and replace Tailwind's defaults, so components can only use the theme.

## Prewarm (offline mode)

```bash
.venv/bin/python scripts/prewarm.py
```

This fetches UAE YouTube trending videos plus their evidence (transcripts, top comments, channel sizes), then runs the local LLM analysis for every top-10 video on both platforms — one at a time, logging progress per video. It is resumable: videos that already have a stored analysis are skipped, so you can stop and rerun it freely. After it runs, the dashboard serves stored data even if the APIs are unreachable.

`LLM_PROVIDER=mock` returns a realistic hardcoded analysis for every video — handy for building the UI without a model installed.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/trending?platform=youtube&relevant=true` | Top 10 with metrics, served from the DB. YouTube data older than 24h is refetched first. |
| POST | `/api/refresh/youtube` | Refetch YouTube trending. On failure, returns the last stored data with `cached: true`. |
| GET | `/api/analysis/{platform}/{video_id}` | Stored analysis, or `{"status": "pending"}`. Read-only — never generates. |
| POST | `/api/analysis/{platform}/{video_id}` | Generate the analysis now (local Ollama model from `LLM_MODEL`) and cache it. |
| GET | `/api/aggregate?platform=youtube` | Counts of hook techniques and format tags across the analyzed top 10. |
| GET | `/api/health` | Health check |

`relevant=true` (the default) hides Music and Gaming videos (`NOISE_CATEGORY_IDS` in `backend/app/config.py`) before taking the top 10.

### LLM analysis

`backend/app/analysis.py` sends a local Ollama model (`LLM_PROVIDER=ollama`, model from `LLM_MODEL`, default `qwen3:8b`) the stats, computed metrics, title/description, transcript (first 3,000 chars), top 10 comments, today's date, the UAE calendar (`backend/app/uae_calendar.py`: Ramadan, Eids, National Day, Dubai Shopping Festival, White Friday) and `data/uae_trends.json` if that file exists. It is text-only — no images are sent, tuned for CPU-only machines. The request uses Ollama's `/api/chat` with `format` set to the Pydantic JSON schema and `think: false`; output is validated by `AnalysisResult` (`backend/app/schemas.py`) and retried once on failure. Analyses run strictly one at a time with a 10-minute timeout. Results are cached in the `analyses` table by `platform:video_id` + `PROMPT_VERSION`; bump `PROMPT_VERSION` to invalidate. If a video has no real transcript, its overall confidence is forced to `low`.

### Metrics

- `velocity` = views / hours since published
- `engagement_rate` = (likes + comments) / views
- `outlier_ratio` = views / channel subscribers
- `score` (0–100) = average of the percentile ranks of velocity and outlier_ratio within the current chart. The top 10 are ranked by this score.

## Tests and lint

```bash
.venv/bin/python -m pytest backend/tests
.venv/bin/ruff check backend scripts && .venv/bin/ruff format --check backend scripts
cd frontend && npm run lint && npm run build
```
