# ResonanceForge

**Situation → leadership-ready readiness report + architecture + starter LangGraph — shareable with a VP.**

ResonanceForge is a B2B assessment product for mid-market AI / transformation leads. It runs a four-agent LangGraph pipeline (Diagnostician → Architect → Code Generator → Critic) and presents results in a professional dark navy / teal web UI, with persisted history, SSE live progress, and shareable report links.

## Phase 1 product features

- **Structured intake** — company name, role, primary systems, constraints, success metric (plus industry / size / situation).
- **SSE streaming** — real per-agent progress via `POST /api/assessments/stream` (UI advances only on step events).
- **SQLite history** — assessments stored in `data/resonanceforge.db`; sidebar loads recent runs.
- **Share links** — `/r/{id}` read-only report page for VP sharing; public JSON at `/api/reports/{id}`.
- **Sync compat** — `POST /assess` still works for CLI and fallback; results are persisted.


## Grounded checklist + runnable pilot

ResonanceForge is not a ChatGPT memo. Assessments are grounded in a fixed **15-question ACCESS / ADAPT / ADOPT checklist** (deterministic 1–10 scoring) and produce a **runnable Docker pilot** zip.

### Checklist scoring

- 5 questions per dimension (ACCESS / ADAPT / ADOPT), answers 1–5
- Dimension score = `round(avg * 2)` clamped to 1–10
- Overall: mean of three dimensions → Low <4.5, Medium <7.5, else High
- `GET /api/checklist` returns the questions for the UI
- When all 15 answers are present, the diagnostician **skips the LLM** and uses the rubric

### Runnable pilot package

After each assessment, a zip is written under `data/pilots/{id}.zip` containing:

- `README.md`, `Dockerfile`, `docker-compose.yml`
- `app/main.py` (generated LangGraph or a solid stub)
- `app/requirements.txt`, `evals/test_pilot.py`, `WHAT_BREAKS_FIRST.md`

Download via **Download runnable pilot (Docker)** in the UI, or:

```bash
curl -OJ http://localhost:8000/api/assessments/{id}/pilot.zip
```

### Leadership brief

Share pages and Markdown downloads lead with a stakeholder 1-pager: executive verdict, scores, top gaps, 90-day plan, cost band, and go/no-go.

## How companies use it

1. Describe a company situation and fill optional structured intake fields.
2. Run an assessment (live pipeline steps).
3. Review ACCESS / ADAPT / ADOPT scores, multi-agent architecture, LangGraph scaffold, and critique.
4. Copy the share link (`/r/{id}`) for leadership review, or download JSON / Markdown.
5. Re-open past assessments from History.

## Quick start

```bash
git clone https://github.com/sai0610-red/ResonanceForge1.git ResonanceForge
cd ResonanceForge
cp .env.example .env
# Edit .env and set GROQ_API_KEY=...

# Option A — Docker
docker compose up --build

# Option B — Local
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**

Default model: `openai/gpt-oss-120b` (`GROQ_MODEL`).

### Example test question

> How ready is a mid-size retail company with poor data quality and no AI strategy for adopting multi-agent systems?

### CLI

```bash
python -m app.main "How ready is a mid-size retail company with poor data quality and no AI strategy for adopting multi-agent systems?" \
  --industry Retail --company-size Mid-size --company-name "Acme Retail" \
  --role-title "Head of AI" --format markdown
```

The CLI prints an assessment id and share path when persistence is enabled (`--no-persist` to skip).

## API summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Main UI |
| `GET` | `/static/*` | Static assets |
| `GET` | `/health` |
| `GET` | `/api/checklist` | 15-question checklist for UI |
| `GET` | `/api/assessments/{id}/pilot.zip` | Download runnable Docker pilot | `{"status":"ok"}` |
| `POST` | `/assess` | Sync assessment → `ResonanceReport` (+ `X-Assessment-Id`, persisted) |
| `POST` | `/api/assessments/stream` | SSE assessment (`event: step` / `complete` / `error`) |
| `GET` | `/api/assessments` | List summaries |
| `GET` | `/api/assessments/{id}` | Full record + report |
| `GET` | `/api/reports/{id}` | Public completed report JSON |
| `GET` | `/r/{id}` | Shareable report HTML |

SSE step payload example:

```text
event: step
data: {"step":1,"name":"diagnostician","label":"Diagnosing readiness","id":"..."}
```

## Architecture (4 agents)

```
START → diagnostician → architect → code_generator → critic → END
```

| Agent | Output |
|-------|--------|
| **Diagnostician** | ACCESS / ADAPT / ADOPT scores, gaps, overall readiness |
| **Architect** | Recommended agent roles, flow, complexity |
| **Code Generator** | Valid LangGraph Python (`StateGraph`, `TypedDict`, `START`/`END`, `compile()`) |
| **Critic** | Strengths, weaknesses, risks, recommendations, verdict |

Orchestration: `app/graphs/resonance_graph.py`. Persistence: `app/db.py` (stdlib sqlite3). LLM: Groq via `langchain_groq`.

## Project layout

```
ResonanceForge/
  app/                 # FastAPI, agents, LangGraph, CLI, db
  static/              # index.html, report.html, styles, JS
  data/                # SQLite DB (gitignored *.db; .gitkeep kept)
  .env.example
  Dockerfile
  docker-compose.yml
  requirements.txt
  README.md
  LICENSE
```

## Limitations

- No RAG / knowledge base grounding
- No authentication or multi-tenant access control
- No human-in-the-loop (HITL) approval gates
- No Stripe / billing
- Generated code is a starting scaffold — review before production use
- Requires a valid Groq API key

## License

MIT © 2026 Sairam Reddy Dornala
