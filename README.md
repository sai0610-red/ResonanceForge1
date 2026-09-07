# ResonanceForge

**Diagnose multi-agent AI readiness. Design an architecture. Generate LangGraph code. Critique before you pilot.**

ResonanceForge is a clone-and-run internal assessment tool for companies evaluating multi-agent AI adoption. It runs a four-agent LangGraph pipeline (Diagnostician → Architect → Code Generator → Critic) and presents results in a professional dark navy / teal web UI, plus a CLI and JSON/Markdown exports.

## How companies use it

1. Describe a company situation (data maturity, AI strategy, org constraints).
2. Optionally set industry and company size.
3. Run an assessment to get ACCESS / ADAPT / ADOPT scores, a recommended multi-agent design, scaffolded LangGraph Python, and a candid critique with a pilot verdict.
4. Download JSON or Markdown for sharing with stakeholders.

## UI overview

- **Header** — ResonanceForge wordmark and short tagline.
- **Input panel** — Textarea for the company situation; industry dropdown (Retail, Manufacturing, Healthcare, Finance, Technology, Other); company size (Startup, Mid-size, Enterprise); **Run assessment** button.
- **Pipeline progress** — Animated 1/4–4/4 steps while waiting: Diagnosing readiness → Designing architecture → Generating LangGraph code → Critiquing solution.
- **Results** — Score cards for ACCESS / ADAPT / ADOPT; overall Low/Medium/High badge; architecture agents and flow; syntax-highlighted code with Copy; critique lists and verdict badge; Download JSON / Download Markdown.
- **Empty / error states** — Clear empty copy before first run; error panel for missing API key, validation, timeout, or LLM failures.

*(Screenshot placeholders: input panel with teal accent controls; score cards on dark navy; code block with copy action; critique verdict badge.)*

## Quick start

```bash
git clone <your-repo-url> ResonanceForge
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

### Example test question

> How ready is a mid-size retail company with poor data quality and no AI strategy for adopting multi-agent systems?

### CLI

```bash
python -m app.main "How ready is a mid-size retail company with poor data quality and no AI strategy for adopting multi-agent systems?" \
  --industry Retail --company-size Mid-size --format markdown
```

Or:

```bash
python -m app.main -q "..." --format json
```

## API summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Single-page UI (`static/index.html`) |
| `GET` | `/static/*` | Static assets |
| `GET` | `/health` | `{"status":"ok"}` |
| `POST` | `/assess` | Body: `{ "question": "...", "industry": "...", "company_size": "..." }` → `ResonanceReport` |

Empty `question` → HTTP 422. Missing/invalid `GROQ_API_KEY` or LLM failures → HTTP 500/502 with `{"detail": "..."}`.

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

Orchestration lives in `app/graphs/resonance_graph.py`. LLM: Groq via `langchain_groq` (`GROQ_MODEL`, default `llama-3.3-70b-versatile`).

## Project layout

```
ResonanceForge/
  app/                 # FastAPI, agents, LangGraph, CLI
  static/              # index.html, styles.css, app.js
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
- Generated code is a starting scaffold — review before production use
- Requires a valid Groq API key

## License

MIT © 2026 Sairam Reddy Dornala
