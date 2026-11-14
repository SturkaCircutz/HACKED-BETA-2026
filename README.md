# HACKED-BETA-2026
This is a repository for the hackathon

## Eco311: map-based environment / 311 reporting with an AI agent

A resident picks a spot or area on the map and describes the problem, optionally with photos.
An AI agent then works out who to contact and drafts an email or a call script. The resident
approves it, and the pin is tracked until the problem is gone.

The case view is a **reference-pinned split workspace**. On the LEFT, the main agent
conversation stays fixed in place. On the RIGHT, branches are side conversations, each
anchored to one step on the left (for example "why this contact?"). They let you ask
about a step without cluttering the main answer.

```
frontend/   Vite + React + TypeScript + MapLibre (OSM tiles)
backend/    FastAPI + LangGraph agent + SQLAlchemy (SQLite dev / Postgres prod)
docs/       AWS deployment guide
docker-compose.yml   Postgres + API + worker + web (nginx), production-like
```

### Run locally (dev)

```bash
# backend (Python 3.12, uv)
cd backend
cp .env.example .env            # optional: set LLM_MODEL, API keys
uv sync --extra openai          # or --extra anthropic
uv run python -m app.seed       # sample contacts (stored as UNVERIFIED)
uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

No API keys are needed to try it. When `LLM_MODEL` is empty, every agent step falls back to
deterministic output (keyword classification, template drafts, hashing embeddings).
Set `LLM_MODEL=openai:gpt-4o-mini` or `LLM_MODEL=anthropic:claude-sonnet-5-5` to switch
the provider. The code doesn't depend on any one provider.

Tests: `cd backend && uv run pytest`
(If ROS or another tool puts things on `PYTHONPATH`, run `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest`.)

Production-like stack: `docker compose up --build` → http://localhost:8080

### Agent graph (LangGraph)

```
intake ─► geo_resolve ─┬─► retrieve_contacts (RAG first, official-site web search fallback) ─┐
                       └─► nearby_reports (duplicates)                                         ├─► draft_action ─► human_review (interrupt)
                                                                                               ┘        ▲                │
                                                                     edit ─────────────────────────────┘   approve ─► deliver ─► track ─► END
                                                                                                         reject ──► END
```

- Fixed pipeline, not plan-and-execute: every request has the same shape, so a fixed graph is
  cheaper, easier to test, and can't wander off course.
- `human_review` pauses through `interrupt()`. The checkpointer (SQLite in dev, Postgres in prod)
  saves the run, so the user can come back later. `send_email` refuses to run unless the
  run has been approved. The agent never places phone calls; the UI shows the number and a script.
- System prompts live in `backend/app/agent/prompts/*.txt`. `agent/context.py` (the
  context engineer) decides which state fields each LLM call can see.

### API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/reports?bbox=&status=&category=&mine=` | pins in viewport |
| POST | `/api/reports` | create pin (GeoJSON Point/Polygon, story, category) |
| GET / PATCH / DELETE | `/api/reports/{id}` | detail / edit or change status / soft delete (archive) |
| GET | `/api/reports/{id}/events` | status timeline |
| POST | `/api/reports/{id}/confirm` | "still_there" / "gone" vote |
| POST | `/api/reports/{id}/subscribe` | follow a pin |
| POST / GET | `/api/reports/{id}/photos` | attach uploaded photo (before/after) / list |
| POST | `/api/uploads/presign` | presigned upload URL (S3 in prod, local in dev) |
| GET | `/api/geo/reverse?lat=&lng=` · `/api/geo/search?q=` | reverse / forward geocoding |
| POST | `/api/agent/runs` | start run (report_id, or geometry + story + photo_ids) |
| GET | `/api/agent/runs?report_id=` · `/api/agent/runs/{id}` | list runs for a pin / run with steps |
| GET | `/api/agent/runs/{id}/stream?after=` | SSE step stream |
| POST | `/api/agent/runs/{id}/resume` | approve / edit / reject at human_review |
| POST | `/api/agent/runs/{id}/cancel` | stop |
| POST | `/api/agent/threads/{id}/messages` | follow-up chat on the main thread |
| GET / POST | `/api/agent/runs/{id}/branches` | list / create branch anchored to a step |
| POST | `/api/agent/branches/{id}/messages` | continue a branch |
| PATCH | `/api/agent/branches/{id}?closed=` | close / reopen (close ≠ delete) |
| POST | `/api/actions/email` · `/api/actions/call-log` | send approved draft / log a call |
| GET | `/api/actions/{id}` | delivery status |
| POST | `/api/webhooks/email` | delivered / bounced / replied events |
| POST | `/api/kb/search` | RAG query → ranked contacts |
| GET / POST | `/api/kb/contacts` | browse / add or update contact |
| POST · GET | `/api/kb/ingest` · `/api/kb/ingest/{job}` | ingest a URL (async) |
| POST | `/api/kb/contacts/{id}/flag` | report wrong email / number |
| GET | `/api/me` · `/healthz` | profile + notifications / health |

The sample contacts in `backend/seed/contacts.json` are imported as **unverified**.
Check each one against its `source_url` before you rely on it.
