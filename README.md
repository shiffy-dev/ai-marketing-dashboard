# ai-marketing-dashboard

AI marketing dashboard for the UAE market. It shows the top 10 trending YouTube videos and Instagram Reels and explains *why* each one is performing, for ecommerce marketing teams.

```
backend/   FastAPI + SQLAlchemy (SQLite) API
frontend/  React (Vite) + Tailwind UI
data/      SQLite DB (gitignored) and static datasets
scripts/   prewarm.py and other utilities
```

## Setup

Requires Python 3.10+.

```bash
cp .env.example .env          # then fill in YOUTUBE_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL
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

Open http://localhost:5173. Vite proxies `/api` and `/static` to the backend on port 8000 (override with `VITE_BACKEND_URL`). The trending list loads first, then each card fetches its own analysis, so cards fill in one by one. Click a card for the full Hook / Body / CTA and "Why it's performing" breakdown.

Design tokens (colours, type scale, radii, shadows) live in `frontend/tailwind.config.js` and replace Tailwind's defaults, so components can only use the theme.

## Prewarm (offline mode)

```bash
.venv/bin/python scripts/prewarm.py
```

This fetches UAE YouTube trending videos plus their evidence (transcripts, top comments, channel sizes), runs the LLM analysis for every top-10 video, and stores everything in the DB. After it runs, the dashboard serves stored data even if the APIs are unreachable.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/trending?platform=youtube&relevant=true` | Top 10 with metrics, served from the DB. YouTube data older than 24h is refetched first. |
| POST | `/api/refresh/youtube` | Refetch YouTube trending. On failure, returns the last stored data with `cached: true`. |
| GET | `/api/analysis/{platform}/{video_id}` | Cached LLM analysis, or generate it (Claude, model from `LLM_MODEL`) and cache it. |
| GET | `/api/aggregate?platform=youtube` | Counts of hook techniques and format tags across the analyzed top 10. |
| GET | `/api/health` | Health check |

`relevant=true` (the default) hides Music and Gaming videos (`NOISE_CATEGORY_IDS` in `backend/app/config.py`) before taking the top 10.

### LLM analysis

`backend/app/analysis.py` sends Claude the stats, computed metrics, title/description, transcript, top comments, thumbnail (as an image), today's date, the UAE calendar (`backend/app/uae_calendar.py`: Ramadan, Eids, National Day, Dubai Shopping Festival, White Friday) and `data/uae_trends.json` if that file exists. The output is strict JSON validated by `AnalysisResult` (`backend/app/schemas.py`). If validation fails, the request is retried once. At most 5 requests run concurrently. Results are cached in the `analyses` table by `platform:video_id` + `PROMPT_VERSION`; bump `PROMPT_VERSION` to invalidate. If a video has no real transcript, its overall confidence is forced to `low`.

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
