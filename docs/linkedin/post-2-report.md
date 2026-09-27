> **Note:** `GITHUB_URL=https://github.com/sai0610-red/ResonanceForge1`
> `DEMO_URL` = replace with the private demo URL once it exists (nothing is deployed yet).
> Post body word count: 152 (target 120–180).
>
> **Status of numbers:** The ACCESS / ADAPT / ADOPT scores and the overall band
> come from the app's deterministic checklist rubric. They were produced by a local run
> of the Red River intake (`docs/red-river-intake.json`) on 2026-09-27 and do not
> depend on the LLM. The **live Groq run could not be completed** because no Groq key was
> available on the box. So `[GO_NO_GO]` and `[SCAFFOLD_BADGE]` are **placeholders**.
> Fill them in from a real run before posting, and do not guess them.

## Post

I ran ResonanceForge on a fictional case to see what it says about a messy, realistic workflow.

Red River Components is a made-up mid-size manufacturer in the DFW area. The workflow is CMMS work-order exception triage: orders that miss SLA, parts that show in stock but are backordered, and priorities logged wrong. Two planners spend hours on it every morning, and 18% of P1/P2 orders miss SLA.

Checklist scores: ACCESS 5/10, ADAPT 6/10, ADOPT 4/10. Overall: Medium. The weakest answers were eval testing, data quality, and integrations. That matches the story: free-text failure codes and a nightly ERP batch.

Critic verdict: [GO_NO_GO]. Scaffold compile check: [SCAFFOLD_BADGE].

The pilot zip has a LangGraph main.py, a Dockerfile, smoke tests, and a WHAT_BREAKS_FIRST.md built from the gaps and risks. Every priority change still goes through a planner.

The exact intake is in the repo, so you can rerun it and compare.

Demo: DEMO_URL
Code: GITHUB_URL

## Suggested screenshots

1. The scores for Red River Components (score cards + Medium badge).
2. The 1-pager with the go/no-go badge and the 90-day plan.
3. The pilot button ("Download runnable pilot (Docker)") and the unzipped file list.
4. The compile badge (PASS/FAIL) above the generated scaffold.
5. The filled-in checklist (optional).
