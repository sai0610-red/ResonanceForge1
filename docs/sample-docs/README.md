# Sample customer documents (fictional)

Two short documents for the fictional Red River Components demo case
([../demo-case.md](../demo-case.md)). They exist so you can try document grounding
without real customer data. Everything in them is invented.

- `red-river-wo-priority-sop.md` — how maintenance planners assign and change work-order priority
- `red-river-systems-notes.txt` — what the CMMS, ERP, and MES expose today

Upload them and run the demo case:

```bash
SET=$(curl -s -X POST http://127.0.0.1:8000/api/documents \
  -H "X-Demo-Token: $DEMO_TOKEN" \
  -F files=@docs/sample-docs/red-river-wo-priority-sop.md \
  -F files=@docs/sample-docs/red-river-systems-notes.txt | python3 -c "import sys,json;print(json.load(sys.stdin)['document_set_id'])")

python3 -c "import json,sys;d=json.load(open('docs/red-river-intake.json'));d['document_set_id']=sys.argv[1];print(json.dumps(d))" "$SET" \
  | curl -N -X POST http://127.0.0.1:8000/api/assessments/stream \
      -H "Content-Type: application/json" -H "X-Demo-Token: $DEMO_TOKEN" --data @-
```
