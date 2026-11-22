# ResonanceForge

**Situation → leadership-ready readiness report + architecture + starter LangGraph scaffold, shareable with a VP.**

> Demo. Generated code is a scaffold. Not a production certification.

ResonanceForge is an assessment tool for mid-market AI / transformation leads.
You describe one company situation and answer a fixed 15-question checklist.
Four agents run in sequence and return a readiness diagnosis, a proposed
multi-agent architecture, a starter LangGraph scaffold, and a critique. It also
produces a leadership 1-pager and a runnable Docker pilot zip. The UI is a
static navy / teal HTML/CSS/JS app with SSE progress, SQLite history, and
share links.

## What it does: four agents

```
START → diagnostician → architect → code_generator → critic → END
```

| Agent | Output |
|-------|--------|
| **Diagnostician** | ACCESS / ADAPT / ADOPT scores (1–10), top gaps, overall readiness |
| **Architect** | Recommended agent roles, high-level flow, estimated complexity |
| **Code Generator** | LangGraph Python scaffold (`StateGraph`, `TypedDict`, `START`/`END`, `compile()`) |
| **Critic** | Strengths, weaknesses, risks, recommendations, final verdict (go/no-go) |

Orchestration: `app/graphs/resonance_graph.py`. The SSE endpoint runs the same four agents
in the same order. LLM: Groq via `langchain_groq` (default `openai/gpt-oss-120b`).

## Grounded 15-question checklist

Scoring uses three **readiness dimensions**, ACCESS, ADAPT, and ADOPT, with 5
questions each, answered 1–5 (`GET /api/checklist`).

- Dimension score = `round(avg * 2)`, clamped to 1–10
- Overall = mean of the three: Low < 4.5, Medium < 7.5, else High
- When all 15 answers are present, the Diagnostician **skips the LLM** and scores
  deterministically from the rubric (`app/rubric/checklist.py`). The other three agents still use the LLM.

## Outputs

- **Leadership 1-pager.** Executive verdict, scores, top gaps, 90-day plan, cost
  band, and go/no-go (`app/services/one_pager.py`). Shown on the share page and at the top of Markdown exports.
- **Runnable pilot zip.** `GET /api/assessments/{id}/pilot.zip` contains `README.md`,
  `Dockerfile`, `docker-compose.yml`, `app/main.py` (generated scaffold or a stub),
  `app/requirements.txt`, `evals/test_pilot.py`, and `WHAT_BREAKS_FIRST.md`.
- **Share page.** `/r/{id}` is a read-only report, backed by public JSON at `GET /api/reports/{id}`.
- **Scaffold compile badge.** Each report carries `scaffold_check`
  `{ok, error, lines, has_stategraph, has_compile}`. The generated code gets
  markdown fences stripped, then `ast.parse` + `compile(..., "exec")`. It is
  **never executed**. The results page and share page show a PASS/FAIL badge next to the code.
  PASS means "it parses and byte-compiles". It does not mean the code runs or is correct.

## Demo access control

### DEMO_TOKEN

When `DEMO_TOKEN` is set, these endpoints require the header `X-Demo-Token: <token>`.
They return **401** when it is missing or wrong (constant-time compare):

- `POST /assess`
- `POST /api/assessments/stream`
- `GET /api/assessments/{id}/pilot.zip`
- `GET /api/assessments` (history list) and `GET /api/assessments/{id}` (full record)

These stay public: `GET /`, `/health`, `/r/{id}`, `GET /api/checklist`,
`GET /api/reports/{id}`, and `/static/*`.

**In the UI:** paste the token into the **Demo token** field (top right of the main page).
It is saved in this browser's `localStorage` and sent on assessment, history,
and pilot-download requests. The share page reuses the same stored token for its pilot button.

**From curl:**

```bash
curl -N -X POST http://localhost:8000/api/assessments/stream \
  -H "Content-Type: application/json" \
  -H "X-Demo-Token: $DEMO_TOKEN" \
  --data @docs/red-river-intake.json

curl -OJ -H "X-Demo-Token: $DEMO_TOKEN" http://localhost:8000/api/assessments/{id}/pilot.zip
```

### Rate limit

`POST /assess` and `POST /api/assessments/stream` share a per-client-IP,
in-memory sliding window of `RATE_LIMIT_PER_HOUR` (default 5). Over the limit you get
**429** with a `Retry-After` header (seconds).

### Input limits (422)

The situation text (`question`) must be non-empty after trimming and at most
`MAX_SITUATION_CHARS` (default 4000) characters. Otherwise the API returns **422**
before any LLM call.

## Configuration

Set these as environment variables or in `.env` (see `.env.example`; never commit `.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | *(empty)* | Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Model id |
| `TEMPERATURE` | `0.2` | LLM temperature |
| `DEMO_TOKEN` | *(empty)* | Enables the token gate when set |
| `RATE_LIMIT_PER_HOUR` | `5` | Assessments per IP per hour |
| `MAX_SITUATION_CHARS` | `4000` | Max situation length |
| `DATA_DIR` | `./data` | SQLite DB + `pilots/` (relative paths resolve from the repo root) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ENV` | `development` | With `production`, startup fails if `GROQ_API_KEY` or `DEMO_TOKEN` is missing |

Logs contain one line per agent run, `assessment_id=... agent=... latency_ms=... ok=...`.
The token and API key are never logged.

### Health

`GET /health` returns `{"status":"ok","env":"...","db_ok":true,"model":"..."}`.
`db_ok` comes from a `SELECT 1` against the SQLite file. No secrets.

## Quick start

```bash
git clone https://github.com/sai0610-red/ResonanceForge1.git ResonanceForge
cd ResonanceForge
cp .env.example .env
# Edit .env: set GROQ_API_KEY, and optionally DEMO_TOKEN

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**, paste the demo token if you set one, answer the checklist, and run.

### Docker (with persistent data volume)

```bash
docker compose up --build
```

`docker-compose.yml` mounts `./data:/app/data`, and the image sets `DATA_DIR=/app/data`,
so the SQLite DB and pilot zips survive container restarts.

### Deploying

See [`docs/deploy.md`](docs/deploy.md) for Fly.io and Railway, and the optional
[`fly.toml`](fly.toml). Nothing is deployed automatically.

### Demo case

[`docs/demo-case.md`](docs/demo-case.md) is a fully fictional case (Red River
Components, CMMS work-order exception triage). It has the exact intake and checklist answers, so the run is reproducible.
The same payload is in `docs/red-river-intake.json`.

### CLI

```bash
python -m app.main "How ready is a mid-size retail company with poor data quality and no AI strategy for adopting multi-agent systems?" \
  --industry Retail --company-size Mid-size --company-name "Acme Retail" \
  --role-title "Head of AI" --format markdown
```

## Tests

```bash
python -m pytest tests/ -q
```

- `tests/test_checklist.py`: rubric scoring
- `tests/test_scaffold_check.py`: compile-check (valid, syntax error, fences, empty, flags, never executes)
- `tests/test_demo_gate.py`: 401 / public endpoints / 422 / 429 / production startup guard (LLM calls monkeypatched, temp `DATA_DIR`)

No test makes a live Groq call.

## API summary

| Method | Path | Auth when `DEMO_TOKEN` set | Description |
|--------|------|---------------------------|-------------|
| `GET` | `/` | public | Main UI |
| `GET` | `/static/*` | public | Static assets |
| `GET` | `/health` | public | `{status, env, db_ok, model}` |
| `GET` | `/api/checklist` | public | 15-question checklist |
| `GET` | `/api/reports/{id}` | public | Completed report JSON (share page) |
| `GET` | `/r/{id}` | public | Share page HTML |
| `POST` | `/assess` | token + rate limit | Sync assessment (`X-Assessment-Id` header) |
| `POST` | `/api/assessments/stream` | token + rate limit | SSE (`event: step` / `complete` / `error`) |
| `GET` | `/api/assessments` | token | History list |
| `GET` | `/api/assessments/{id}` | token | Full record |
| `GET` | `/api/assessments/{id}/pilot.zip` | token | Runnable Docker pilot |

## Limitations

- **Scaffold, not certification.** Generated code is a starting point. The compile
  badge only proves it parses. It is not tested against your systems and is not a
  security or production review.
- **LLM variance.** Architect, Code Generator, and Critic output (including the
  go/no-go verdict) can change between runs with the same input. Only the checklist scores are deterministic.
- **Single-instance SQLite.** One process, one volume. No horizontal scaling.
- **In-memory rate limit** resets on restart and is per process. Behind some
  proxies every client can share one IP bucket (see `docs/deploy.md`).
- **Share links are public.** Anyone with a `/r/{id}` link can view that report.
  IDs are random UUID4s, but they are not access-controlled.
- **Demo token is a shared secret**, not per-user auth. No SSO, no multi-tenant isolation.
- No RAG grounding, no human-in-the-loop UI, no billing.
- Requires a valid Groq API key.

## License

MIT © 2026 Sairam Reddy Dornala
