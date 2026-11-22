> **Note:** `GITHUB_URL=https://github.com/sai0610-red/ResonanceForge1`
> `DEMO_URL` = replace with the private demo URL once it exists.
> Short replies to likely comments. Keep them factual. No pitching.

## Suggested screenshots to attach when useful

- The checklist (for "is the scoring just the LLM?")
- The scores (for "how did it rate X?")
- The 1-pager (for "what does leadership actually see?")
- The pilot button / zip listing (for "what do I get?")
- The compile badge (for "does the code run?")

## Replies

1. **"Isn't this just ChatGPT with a prompt?"**
   Partly, for the architecture and critique text. The scores aren't, though. With all 15 checklist answers, they come from a fixed rubric in code, so the same answers always give the same scores. The rubric is in GITHUB_URL.

2. **"Does the generated code actually run?"**
   Not guaranteed. The badge only means it parses and byte-compiles. Nothing is executed on the server. The pilot zip has smoke tests you can run yourself in Docker. Treat the code as a scaffold.

3. **"Is ACCESS / ADAPT / ADOPT an official framework?"**
   No. They're just the three readiness dimensions I use to group the checklist: data and integrations, organizational readiness, and production readiness.

4. **"Can I try it on my own workflow?"**
   Yes. It's open source. Clone GITHUB_URL, set a Groq key, and run it locally or in Docker. The Red River demo case in docs/ shows the intake format.

5. **"What happens to the data I enter?"**
   It's stored in a local SQLite file on whatever instance you run. Share links are public to anyone who has the link, so don't paste confidential details into a shared demo.

6. **"Why Groq and why LangGraph?"**
   Groq because it's fast and cheap enough for a four-agent run. LangGraph because the output should be an explicit graph with named nodes you can put gates between, not a single long prompt.

7. **"Why does the verdict change between runs?"**
   The architect, code generator, and critic use an LLM, so their text and verdict can vary. The checklist scores don't. I'd rather be upfront about that than hide it.

8. **"What is Forge Control? Are you raising?"**
   Not raising. Forge Control is the next piece I'm building in the open: approvals, eval checks, and run logs around one workflow. I'll post progress in the repo.
