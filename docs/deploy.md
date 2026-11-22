# Deploying ResonanceForge (Fly.io or Railway)

These are step-by-step notes for running a **private demo** instance. Nothing
here is deployed automatically. Keep `DEMO_TOKEN` set and share it only with
people who should be able to run assessments.

## What production mode requires

- `ENV=production`. In this mode the app **refuses to start** unless both
  `GROQ_API_KEY` and `DEMO_TOKEN` are set. The error names the missing variable,
  never its value.
- Secrets go in the platform's secret store (`fly secrets set`, Railway
  Variables). Never in `fly.toml`, the Dockerfile, or git.
- A **persistent volume mounted at `/app/data`** (`DATA_DIR=/app/data`). It
  holds the SQLite DB (`resonanceforge.db`, plus `-wal`/`-shm` when WAL is
  active) and pilot zips (`pilots/`).
- Health check: `GET /health` returns `{"status","env","db_ok","model"}` (no secrets)
  and an `X-Request-ID` header.
- The container runs as a non-root user (uid 10001). The entrypoint chowns
  `DATA_DIR` if it starts as root, then drops privileges.

> **Single instance only.** SQLite on a local volume and the in-memory rate
> limiter both assume **one** running instance. Do not scale horizontally.
> Running two machines gives you two separate databases and two separate
> rate-limit counters.

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
| `LOG_FORMAT` | `json` | |
| `TRUSTED_PROXY` | `true` on Fly/Railway | Use the first `X-Forwarded-For` hop. **Do not** set this on a public IP. |
| `CORS_ORIGINS` | *(empty)* | Leave empty when the UI is served from the same origin |
| `LLM_TIMEOUT_SECONDS` | `60` | |
| `LLM_MAX_RETRIES` | `2` | |

Generate a demo token locally, e.g. `python -c "import secrets; print(secrets.token_urlsafe(24))"`.

---

## Fly.io

### First-time setup

1. Install `flyctl` and log in: `fly auth login`.
2. Edit `fly.toml` and replace `app = "your-resonanceforge-app-name"` with your
   app name. Keep `internal_port = 8000`, the `/health` check, `TRUSTED_PROXY=true`,
   and the `[[mounts]]` entry.
3. Create the app without deploying, create the volume, set secrets, deploy, and
   pin to one machine:
   ```bash
   fly launch --no-deploy --copy-config
   fly volumes create rf_data --size 1 --region dfw
   fly secrets set GROQ_API_KEY=<your-groq-key> DEMO_TOKEN=<your-demo-token>
   fly deploy
   fly scale count 1
   ```
   `ENV=production`, `DATA_DIR=/app/data`, and `TRUSTED_PROXY=true` are already
   in `[env]` in `fly.toml`. Secrets never go in that file.

### Later deploys (one command)

Once the app, volume, and secrets exist:

```bash
fly deploy
```

`fly deploy` builds the Dockerfile, rolls the machine, and uses the existing
volume and secrets.

### Verify

```bash
curl -sS https://<app>.fly.dev/health
# {"status":"ok","env":"production","db_ok":true,"model":"openai/gpt-oss-120b"}

curl -o /dev/null -w "%{http_code}\n" -X POST https://<app>.fly.dev/api/assessments/stream \
  -H 'Content-Type: application/json' -d '{"question":"test"}'   # 401 without token
```

Logs: `fly logs`. Lines are JSON, one object per event, including
`request_id` and `assessment_id=... agent=... latency_ms=... ok=...`.

---

## Railway

1. Create a new project, then **Deploy from GitHub repo** and pick this repository.
   Railway detects the `Dockerfile`.
2. Open the service and go to **Variables**. Add:
   - `GROQ_API_KEY` = your key
   - `DEMO_TOKEN` = your demo token
   - `ENV` = `production`
   - `DATA_DIR` = `/app/data`
   - `TRUSTED_PROXY` = `true`
   - `PORT` = `8000` (the container listens on 8000)
3. Go to **Volumes** (or right-click the service and choose **Attach volume**).
   Add a volume with mount path **`/app/data`**.
4. Under **Settings → Networking**, generate a domain with target port `8000`.
5. Under **Settings → Deploy**, set the healthcheck path to **`/health`**.
6. Keep **replicas = 1**, because SQLite and the in-memory rate limit are
   single-instance.
7. Redeploy, then check `https://<your-domain>/health`.

---

## Backups

SQLite runs in WAL mode. The database is a set of files under `DATA_DIR`:

- `resonanceforge.db`
- `resonanceforge.db-wal` and `resonanceforge.db-shm` (present while WAL is active)

Ways to take a consistent copy:

```bash
# Online backup (preferred). Run on the machine that has DATA_DIR mounted:
sqlite3 /app/data/resonanceforge.db ".backup '/app/data/resonanceforge-backup.db'"

# Or checkpoint, then copy the main file:
sqlite3 /app/data/resonanceforge.db "PRAGMA wal_checkpoint(TRUNCATE);"
cp /app/data/resonanceforge.db /app/data/resonanceforge-backup.db
```

Also snapshot the volume (`fly volumes snapshots list`, Railway volume backups).
There is no built-in scheduled backup; set one on the platform if the instance
holds reports you care about.

## Notes and caveats

- **Rate limiting behind a proxy.** Leave `TRUSTED_PROXY=false` (the default)
  unless a trusted platform proxy is the only source of `X-Forwarded-For`.
  On Fly and Railway, set `TRUSTED_PROXY=true` (already in `fly.toml`). If you
  leave it false on those platforms, every visitor may share one IP bucket.
- **Restart resets the rate limit.** Counters live in memory.
- **Share links are public.** Anyone with `/r/{id}` can read that report. Links
  do not expire and cannot be revoked. Pilot zips and the history list need the
  demo token.
- **LLM cost.** Each full assessment makes up to three LLM calls (the
  Diagnostician skips the model when the checklist is complete). The token gate
  and rate limit are the cost controls.
