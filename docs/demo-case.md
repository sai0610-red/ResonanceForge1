# Demo case: Red River Components (fictional)

> **Everything in this case is fictional.** Red River Components is an invented
> company used to demo ResonanceForge. Any resemblance to a real business is
> coincidental. No real employer or customer data is used.

**Company:** Red River Components, a DFW-area discrete manufacturer
(machined and stamped metal components, two plants, ~650 employees).

**Workflow under assessment:** CMMS work-order exception triage, meaning the
maintenance work orders that miss SLA, stall on parts backorders, or carry the
wrong priority.

Use the exact intake below to reproduce the demo run. Paste each field into the
matching input on the main page (or send the JSON in the API section at the end).

---

## Intake fields

| Field | Value |
|-------|-------|
| Company name | `Red River Components` |
| Your role | `Director of Maintenance & Reliability` |
| Industry | `Manufacturing` |
| Company size | `Mid-size` |
| Primary systems | `On-prem CMMS (work orders, asset register, PM schedules); ERP inventory and purchasing module; MES downtime log; shared maintenance inbox` |
| Constraints | `90-day pilot; capped pilot budget; no autonomous work-order closure or priority changes without a planner approving; plant data stays in our approved environment; 2 reliability engineers part-time` |
| Success metric | `Cut SLA-missed P1/P2 work orders from 18% to under 10% in 90 days, and triage time per exception from ~20 min to under 5 min` |

### Company situation (paste exactly; 1,752 characters, under the 4,000 limit)

```text
Red River Components is a mid-size discrete manufacturer in the Dallas-Fort Worth area with two plants (CNC machining and metal stamping), about 650 employees, and roughly 2,400 maintenance work orders per month in an on-prem CMMS.

The workflow we want to assess is work-order exception triage. Every morning two maintenance planners spend 2-3 hours reviewing exceptions: work orders that have missed their SLA, work orders stuck waiting on backordered parts, and work orders whose priority looks wrong (for example, a leaking hydraulic line on a press logged as P4, or a cosmetic guard issue logged as P1). About 18% of P1/P2 work orders miss SLA today. Roughly a third of those are parts-related: the part shows as in stock in the ERP but is actually on backorder or sitting in the wrong crib.

Data reality: asset hierarchy in the CMMS is about 70% complete, failure codes are free text and inconsistent across shifts, and the ERP-to-CMMS parts sync is a nightly batch file. The MES downtime log has good timestamps but is not linked to work-order numbers. There is no API gateway; the CMMS has a read-only SQL view and a limited REST endpoint for creating notes.

We want a narrow multi-agent pilot that reads open exceptions each morning, checks parts status against the ERP, flags likely misclassified priorities with a short justification, and drafts a ranked triage list for the planner. A planner must approve any priority change or escalation. Nothing is closed or reprioritized automatically.

Constraints: 90-day pilot, capped budget, two reliability engineers part-time, plant data must stay in our approved environment, technicians are skeptical of another tool. Success means fewer SLA misses and faster triage, not headcount reduction.
```

---

## Suggested checklist answers (all 15 answered, so scores come from the rubric)

With all 15 answers present, the Diagnostician uses the deterministic rubric
(dimension = `round(avg * 2)`, clamped 1–10) and skips the LLM for scoring.
The Architect, Code Generator, and Critic still call the LLM, so their text
and the final verdict can vary between runs.

### ACCESS

| Question id | Answer | Why (fictional context) |
|-------------|:------:|--------------------------|
| `access_data_quality` | 2 | Free-text failure codes; asset hierarchy ~70% complete |
| `access_unified_apis` | 2 | Read-only SQL view + a limited REST note endpoint; no gateway |
| `access_pii_governance` | 3 | Technician names/badges in work orders; policy exists, uneven enforcement |
| `access_latency_freshness` | 3 | CMMS is live; ERP parts sync is a nightly batch |
| `access_integrations` | 2 | Brittle scripts between ERP and CMMS |

### ADAPT

| Question id | Answer | Why |
|-------------|:------:|-----|
| `adapt_ai_strategy` | 2 | Interest in AI, no prioritized roadmap |
| `adapt_talent_partners` | 3 | Two reliability engineers part-time for the pilot |
| `adapt_change_management` | 2 | Technicians skeptical; training is reactive |
| `adapt_exec_sponsorship` | 4 | VP Operations sponsors and reviews weekly |
| `adapt_pilot_budget` | 3 | Limited discretionary pilot spend |

### ADOPT

| Question id | Answer | Why |
|-------------|:------:|-----|
| `adopt_security_compliance` | 3 | Known review path, slow exception process |
| `adopt_observability` | 2 | App logs only, no agent traces |
| `adopt_human_in_loop` | 3 | Planner review queue exists, no SLA |
| `adopt_eval_testing` | 1 | No golden set of triaged exceptions yet |
| `adopt_production_ownership` | 2 | Would start as a consultant-style side project |

Expected rubric scores from these answers: **ACCESS 5/10, ADAPT 6/10, ADOPT 4/10,
overall Medium** (mean 5.0). The critic's verdict comes from the LLM.

---

## Reproduce via API

```bash
export DEMO_TOKEN=<your-demo-token>   # the value the server was started with
curl -N -X POST http://localhost:8010/api/assessments/stream \
  -H "Content-Type: application/json" \
  -H "X-Demo-Token: $DEMO_TOKEN" \
  --data @docs/red-river-intake.json
```

`docs/red-river-intake.json` contains the same intake and checklist as JSON.
