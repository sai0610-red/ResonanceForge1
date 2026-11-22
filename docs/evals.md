# Evals

`make eval` runs a set of golden cases through the real app and checks the parts
of the output that should never drift. It runs in CI on every push and pull
request, with no API key.

```bash
make eval                                   # offline, all cases, about 15 s
python -m evals.run --case red-river        # one case (substring match)
make eval-live                              # real model calls; uses your quota
EVAL_LIVE=1 python -m evals.run --case 01-red-river
```

Results go to `evals/results/summary.json` and `summary.md`, which are gitignored.
In CI, the Markdown table is written to the job summary and both files are
uploaded as the `eval-summary` artifact. The process exits 1 if any check fails.

## What runs

Each case goes through the full FastAPI app in-process, with a fresh temp
`DATA_DIR` and the same code paths a user hits: `POST /api/documents` when the case
has documents, then `POST /api/assessments/stream`. That covers the rubric,
retrieval, citation validation, the scaffold compile check, the pilot zip, the
1-pager, and the Markdown export.

- **Offline (default).** The four agents' chat model is replaced by a stub that
  returns fixed structured outputs from `evals/stubs/default.json`, merged with
  each case's `stub` overrides. No network. Everything around the model is real.
- **Live (`--live` / `EVAL_LIVE=1`).** Real provider calls, with stubs ignored. It
  pauses `EVAL_LIVE_PAUSE_SECONDS` (default 60) between cases to stay under
  free-tier token limits. A model-estimated band (the no-checklist case) is not
  pinned in live mode.

## Cases (`evals/cases/`)

| Case | What it pins |
|------|--------------|
| `01-red-river` | Fictional demo case: rubric 5/6/4, Medium |
| `02-red-river-with-docs` | Same, plus the two sample docs. The stub cites two real chunks and one invented label (`[D9:C9]`), which must be removed |
| `03-ennis`, `04-parker-food-group`, `05-optex-systems` | The three outside-in DFW examples: 5/5/5, 5/6/5, 5/5/6, all Medium (matches `docs/examples/`) |
| `06-edge-all-ones` / `07-edge-all-fives` | Floor (2/2/2, Low) and ceiling (10/10/10, High) |
| `08`, `09`, `10` boundary cases | Mean 4.33 is Low, 4.67 is Medium, 7.67 is High (the thresholds are 4.5 and 7.5) |
| `11-edge-no-checklist` | The LLM diagnosis path must label the summary "Estimated without checklist" |
| `12-edge-broken-scaffold` | Code with a syntax error: the report still completes and the badge says FAIL |
| `13-edge-codegen-no-stategraph` | No `StateGraph` in the output: the template fallback is used and compiles |
| `14-edge-empty-question`, `15-edge-unknown-document-set` | 422 before any LLM call (the harness asserts zero model calls) |

## Checks

| Check | Rule |
|-------|------|
| `rubric_scores` | ACCESS / ADAPT / ADOPT equal the golden values |
| `diagnosis_source`, `rubric_reasons` | A complete checklist uses the rubric (reasons start "Checklist-driven:"); no checklist is labeled as estimated |
| `overall_band` | The band matches the mean of the three scores (Low < 4.5 ≤ Medium < 7.5 ≤ High) and the golden band |
| `verdict_mapping` | The critic's verdict is one of the three allowed values and is carried unchanged into the 1-pager `go_no_go`, the executive verdict line, and the Markdown "Go / No-Go" |
| `verdict_vs_readiness` | Low readiness may never come with "Ready for pilot" |
| `scaffold_compile` | `scaffold_check.ok` matches the expectation (PASS with `StateGraph` and `.compile()` found, or an honest FAIL) |
| `citations_valid`, `citations_dropped`, `evidence_section` | Every `[D:C]` left in the text is a retrieved passage marked `cited`, and vice versa. Invented labels are counted as dropped. Markdown has an Evidence section |
| `no_evidence_without_docs` | No documents means no Evidence block |
| `report_sections` | The Markdown export has all 1-pager and report headings |
| `pilot_package` | The pilot zip exists and contains `Dockerfile` and `WHAT_BREAKS_FIRST.md` |
| `architect_prompt_has_passages` | Offline with docs: retrieved passages actually reached the Architect prompt |

`tests/test_evals.py` runs the offline harness under pytest and proves it can
fail: a wrong golden score fails only `rubric_scores`, and "Ready for pilot" on an
all-ones checklist fails only `verdict_vs_readiness`.

## What this does not measure

Offline mode checks the deterministic pipeline around the model, not model
quality. It does not grade whether an architecture is good, whether a cited
passage really supports the sentence it is attached to, or retrieval recall.
Those need labeled data and, for the support question, a human or model grader.
Live mode only applies the same structural rules to real model output. In one
local live run of `01-red-river`, all 10 checks passed, with two Groq TPM waits
handled by the retry layer. That is one run, not a pass rate.

## Adding a case

Drop a JSON file in `evals/cases/`:

```json
{
  "description": "why this case exists",
  "intake_file": "docs/red-river-intake.json",
  "checklist": {"all": 3},
  "documents": ["docs/sample-docs/red-river-systems-notes.txt"],
  "stub": {"critique": {"final_verdict": "Not ready"}},
  "expected": {"scores": {"access": 6, "adapt": 6, "adopt": 6}, "overall_readiness": "Medium",
               "diagnosis_source": "rubric", "evidence": true, "min_citations_dropped": 0}
}
```

`checklist` is optional and overrides the intake. It accepts `{"all": n}`,
`{"access": [5 values], "adapt": [...], "adopt": [...]}`, a raw list, or `null`
for no checklist. Use `"expected": {"http_status": 422}` for request-rejection
cases.
