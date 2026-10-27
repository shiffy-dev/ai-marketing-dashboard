# ai-marketing-dashboard

AI marketing dashboard for the UAE market. It shows the top 10 trending YouTube videos and Instagram Reels and explains *why* each one is performing, for ecommerce marketing teams.

```
backend/   FastAPI + SQLAlchemy (SQLite) API
frontend/  React (Vite) + Tailwind UI
data/      SQLite DB (gitignored) and static datasets
scripts/   prewarm.py and other utilities
```

## Setup

Requires Python 3.10+, Node 20+, and [Claude Code](https://docs.claude.com/en/docs/claude-code) logged in with a Claude subscription. Analyses run through the CLI in headless mode (`claude -p`) — no API key, no per-token billing.

```bash
npm install -g @anthropic-ai/claude-code
claude                      # first run: sign in with your Claude (Pro/Max) account, then /exit
claude -p "say ok"          # sanity check — should print "ok"
```

Create a `.env` file in the repo root:

```bash
YOUTUBE_API_KEY=...
LLM_PROVIDER=claude_cli     # or "mock" for UI development / tests
# LLM_MODEL=sonnet          # optional: override the CLI's default model
# CLAUDE_CLI_BIN=claude     # optional: path to the claude binary
```

`ANTHROPIC_API_KEY` must **not** be set — the backend strips it from the CLI's environment anyway, so the subscription is always used.

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

## Instagram dataset

Instagram is a static dataset — the app never scrapes Instagram live. On startup the backend loads `data/instagram_reels.json` into the DB (idempotent upsert: re-runs don't duplicate, and a new stats snapshot is only added when plays/likes/comments changed). If that file is missing it loads `data/seed_reels.json` instead — 10 clearly-labeled placeholder reels — and the UI shows a **Sample data** badge. With a real dataset the UI shows "Trending among tracked UAE accounts. Data as of <scraped_at>. Reviewed by our team."

Thumbnails and frames are served from `data/static/` at `/static/...`.

To build the dataset from an Apify Instagram Reels export:

```bash
# put the export at data/raw_apify_reels.json, then:
.venv/bin/python scripts/apify_import.py     # writes data/instagram_reels.json + data/static/reels/*.jpg
```

Per-reel fields: `id, url, account, followers, caption, hashtags[], audio, plays, likes, comments, posted_at, top_comments[], transcript, frames[], thumbnail, reviewer_notes`. File-level: `scraped_at, source`.

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
| POST | `/api/analysis/{platform}/{video_id}` | Generate the analysis now via the Claude Code CLI and cache it. |
| GET | `/api/aggregate?platform=youtube` | Counts of hook techniques and format tags across the analyzed top 10. |
| GET | `/api/health` | Health check |

`relevant=true` (the default) hides Music and Gaming videos (`NOISE_CATEGORY_IDS` in `backend/app/config.py`) before taking the top 10.

### LLM analysis

`backend/app/analysis.py` runs `claude -p --output-format json` as a subprocess (`ClaudeCLIProvider`), passing the prompt on stdin. The evidence is text-only: stats, computed metrics, title/description, transcript (first 3,000 chars), top 10 comments, today's date, the UAE calendar (`backend/app/uae_calendar.py`: Ramadan, Eids, National Day, Dubai Shopping Festival, White Friday) and `data/uae_trends.json` if that file exists. The reply is validated by `AnalysisResult` (`backend/app/schemas.py`) and retried once on failure. Analyses run strictly one at a time with a 5-minute timeout. If `claude` is missing or not logged in, the error says so. Results are cached in the `analyses` table by `platform:video_id` + `PROMPT_VERSION`; bump `PROMPT_VERSION` to invalidate. If a video has no real transcript, its overall confidence is forced to `low`.

Only `POST /api/analysis/...` and `scripts/prewarm.py` ever invoke the CLI. Page loads are read-only and show "Analysis pending" until an analysis is stored.

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
