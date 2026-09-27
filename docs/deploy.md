# Deploying ResonanceForge (Fly.io or Railway)

These are step-by-step notes for running a **private demo** instance. Nothing
here is deployed automatically.

## What production mode requires

- `ENV=production`. In this mode the app **refuses to start** unless both
  `GROQ_API_KEY` and `DEMO_TOKEN` are set. The error names the missing variable,
  never its value.
- Secrets go in the platform's secret store (`fly secrets set`, Railway
  Variables). Never in `fly.toml`, the Dockerfile, or git.
- A **persistent volume mounted at `/app/data`** (`DATA_DIR=/app/data`). It
  holds the SQLite DB (`resonanceforge.db`) and pilot zips (`pilots/`).
- Health check: `GET /health` returns `{"status","env","db_ok","model"}` (no secrets).

> **Single instance only.** SQLite on a local volume and the in-memory rate
> limiter both assume **one** running instance. Do not scale horizontally.
> Running two machines gives you two separate databases and two separate rate-limit counters.

| Variable | Example | Notes |
|----------|---------|-------|
| `GROQ_API_KEY` | *(secret)* | Required in production |
| `DEMO_TOKEN` | *(secret)* | Required in production; clients send it as `X-Demo-Token` |
| `ENV` | `production` | |
| `DATA_DIR` | `/app/data` | Must be the volume mount path |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | or `openai/gpt-oss-20b` |
| `TEMPERATURE` | `0.2` | |
| `RATE_LIMIT_PER_HOUR` | `5` | Per client IP, assessment-creating endpoints only |
| `MAX_SITUATION_CHARS` | `4000` | Longer input returns 422 |
| `LOG_LEVEL` | `INFO` | |

Generate a demo token locally, e.g. `python -c "import secrets; print(secrets.token_urlsafe(24))"`.

---

## Fly.io

1. Install `flyctl` and log in: `fly auth login`.
2. Edit `fly.toml` and replace `app = "your-resonanceforge-app-name"` with your app
   name. Keep `internal_port = 8000`, the `/health` check, and the `[[mounts]]` entry.
3. Create the app without deploying:
   ```bash
   fly launch --no-deploy --copy-config
   ```
4. Create the persistent volume, in the same region as `primary_region`:
   ```bash
   fly volumes create rf_data --size 1 --region dfw
   ```
5. Set secrets. They are stored encrypted and never written to `fly.toml`:
   ```bash
   fly secrets set GROQ_API_KEY=<your-groq-key> DEMO_TOKEN=<your-demo-token>
   ```
   `ENV=production` and `DATA_DIR=/app/data` are already in `[env]` in `fly.toml`.
6. Deploy and pin to one machine:
   ```bash
   fly deploy
   fly scale count 1
   ```
7. Verify:
   ```bash
   curl https://<app>.fly.dev/health
   # {"status":"ok","env":"production","db_ok":true,"model":"openai/gpt-oss-120b"}
   curl -o /dev/null -w "%{http_code}\n" -X POST https://<app>.fly.dev/api/assessments/stream \
     -H 'Content-Type: application/json' -d '{"question":"test"}'   # 401 without token
   ```
8. Logs: `fly logs`. You get one line per agent run:
   `assessment_id=... agent=... latency_ms=... ok=...`.

## Railway

1. Create a new project, then **Deploy from GitHub repo** and pick this repository.
   Railway detects the `Dockerfile`.
2. Open the service and go to **Variables**. Add:
   - `GROQ_API_KEY` = your key
   - `DEMO_TOKEN` = your demo token
   - `ENV` = `production`
   - `DATA_DIR` = `/app/data`
   - `PORT` = `8000` (the container listens on 8000)
3. Go to **Volumes** (or right-click the service and choose **Attach volume**). Add a volume
   with mount path **`/app/data`**.
4. Under **Settings → Networking**, generate a domain with target port `8000`.
5. Under **Settings → Deploy**, set the healthcheck path to **`/health`**.
6. Keep **replicas = 1**, because SQLite and the in-memory rate limit are single-instance.
7. Redeploy, then check `https://<your-domain>/health`.

---

## Notes and caveats

- **Rate limiting behind a proxy.** The limiter keys on the TCP client address
  that uvicorn sees. On Fly and Railway, that can be the platform proxy address.
  Then the limit behaves as a **global** limit (fail-safe on cost, but
  stricter). Trusting `X-Forwarded-For` blindly (`--forwarded-allow-ips="*"`)
  would let clients spoof their IP and bypass the limit, so it's off by default.
- **Restart resets the rate limit.** Counters live in memory.
- **Share links are public.** Anyone with `/r/{id}` can read that report. Pilot
  zips and the history list need the demo token.
- **Backups.** Snapshot the volume (`fly volumes snapshots list`, Railway volume
  backups). The DB is a single file at `/app/data/resonanceforge.db`.
