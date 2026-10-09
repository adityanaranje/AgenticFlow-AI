# Free deployment: Vercel (frontend) + Render (API + workers)

Runbook for hosting AgentFlow AI at **$0/month** on free tiers, with the
external services (OpenAI, Redis, Supabase, Qdrant, Langfuse) you already
have set up.

```
Browser ──> Vercel (Next.js, free Hobby)          NEXT_PUBLIC_* build-time vars
   │  └── HTTPS, CDN, auto-deploy from Git
   │
   └── fetch ──> Render (free web service, Docker)
                   ├── uvicorn app.main:app        (FastAPI, $PORT)
                   ├── python -m app.workers.document_worker
                   └── python -m app.workers.research_worker
                     │
                     ├── Supabase (Auth + Postgres + Storage)
                     ├── Qdrant (vectors)
                     ├── Redis (queues, caches, usage counters)
                     ├── OpenAI (chat + embeddings)
                     └── Langfuse (traces, prompts)
```

**Why one Render container for three processes:** Render's free tier offers
web services only — background workers are a paid service type — so the API
and both queue consumers are started together by
[`start-services.sh`](./start-services.sh) inside a single free web service.
`docker-compose.yml` (separate containers) remains the model for any host
with a free worker type.

**Free-tier facts that shape this runbook** (verified 2026-10):

| Constraint | Consequence | Mitigation in this repo |
| --- | --- | --- |
| Render free = 512 MB RAM / 0.1 CPU | LangChain/PyPDF ingestion can OOM | Lean concurrency defaults in [`render.yaml`](../../render.yaml) |
| Render free spins down after 15 min idle | Workers sleep → documents stay `pending` | Keep-alive ping (Part 4) |
| Render free = 750 instance hrs/month, workspace-wide | One always-warm service fits (~730 h) | Don't add a second always-on free service |
| Render free has no persistent disk | Uploaded files must not live on disk | They already live in Supabase Storage |
| Vercel Hobby is **non-commercial only** | Fine for a portfolio/demo | Move to Pro before any commercial use |
| `NEXT_PUBLIC_*` is inlined at build time | Changing the API URL needs a rebuild | Set Vercel env vars *before* deploying |

---

## Part 1 — Render: API + both workers

### Option A: Blueprint (recommended, ~5 minutes)

1. Push this branch to GitHub (the blueprint and the start script must be in
   the repo Render builds).
2. Render Dashboard → **New** → **Blueprint**.
3. Select the `AgenticFlow-AI` repository. Render reads
   [`render.yaml`](../../render.yaml) and shows one service, `agentflow-api`.
4. Fill in every prompted secret (all `sync: false` values):

   | Env var | Where to get it |
   | --- | --- |
   | `FRONTEND_URL` | your Vercel URL — **set after Part 2**, e.g. `https://agentflow-ai.vercel.app` |
   | `OPENAI_API_KEY` | platform.openai.com → API keys |
   | `SUPABASE_URL` | Supabase → Project Settings → General |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API keys → **secret** key (`sb_secret_...`) |
   | `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant Cloud console → your cluster |
   | `REDIS_URL` | your hosted Redis (Upstash/Redis Cloud); use `rediss://…` for TLS |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Langfuse → Project Settings → API keys |

   Tip: leave `FRONTEND_URL` as a placeholder (e.g. `http://localhost:3000`)
   for the first deploy if you don't have the Vercel URL yet, then fix it in
   Part 3 — CORS is the only thing that depends on it.
5. **Apply**. The first build installs LangChain/LangGraph/FastMCP and friends
   — expect **5–10 minutes**. When the deploy goes live, note the service URL:
   `https://agentflow-api-<something>.onrender.com`.

### Option B: Manual (no blueprint)

New → **Web Service** → connect the repo, then:

| Setting | Value |
| --- | --- |
| Runtime | **Docker** |
| Dockerfile path | `backend/Dockerfile` |
| Docker build context | repository root (`.`) |
| Docker command | `bash /app/infrastructure/render/start-services.sh` |
| Instance type | **Free** |
| Region | Singapore (or closest to you) |
| Health check path | `/` |
| Auto-deploy | On commit (optional) |

Add the same environment variables from the table above, plus the tuning
block from `render.yaml`.

### What "healthy" looks like

```bash
curl https://<your-service>.onrender.com/
# {"name":"AgentFlow AI","status":"running","version":"0.1.0"}

curl https://<your-service>.onrender.com/api/v1/health
# deep probe: every service should report "up"
```

The service log should show three lines from the start script:

```
[start-services] Starting document worker...
[start-services] Starting research worker...
[start-services] Starting FastAPI on 0.0.0.0:10000...
[start-services] Processes up: api=… document_worker=… research_worker=…
```

---

## Part 2 — Vercel: Next.js frontend

1. vercel.com → **Add New… → Project** → import `AgenticFlow-AI`.
2. **Root Directory: `frontend`** ← the single most important setting.
   Framework preset auto-detects as Next.js; leave build/output commands alone.
3. Add environment variables (**Production** environment):

   | Env var | Value |
   | --- | --- |
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase → API keys → publishable (`sb_publishable_…`). Legacy projects: set `NEXT_PUBLIC_SUPABASE_ANON_KEY` instead. **Never** the secret key. |
   | `NEXT_PUBLIC_API_URL` | `https://<your-render-service>.onrender.com` (no `/api/v1`, no trailing slash) |

4. **Deploy**. The URL is `https://<project>-<hash>.vercel.app`.

Because these values are baked into the browser bundle **at build time**, any
later change requires a redeploy (Deployments → ⋯ → Redeploy) — editing the
variable alone does nothing.

---

## Part 3 — Wire the two together

1. **Backend CORS:** Render → `agentflow-api` → **Environment** → set
   `FRONTEND_URL` to the exact Vercel origin (scheme + host, no trailing
   slash) → **Save** (Render redeploys automatically). `main.py` builds
   `allow_origins` from this single value.
2. **Supabase Auth URLs:** Supabase → Authentication → **URL Configuration**:
   - Site URL: `https://<your-vercel-domain>`
   - Redirect URLs: `https://<your-vercel-domain>/**`
3. **Google OAuth** (if enabled): add the Vercel origin to *Authorized
   JavaScript origins* and `https://<your-vercel-domain>/auth/callback` to
   *Authorized redirect URLs* in the Google Cloud console — the same table as
   the local setup in the main README (§6, "Google OAuth: which URL goes
   where").
4. Re-run the sign-in flow once end-to-end. If the browser shows a CORS
   error, `FRONTEND_URL` is the culprit (http vs https, trailing slash, or a
   Vercel *preview* domain — only one origin is allowed per backend).

---

## Part 4 — Keep the free service warm

Without this, the instance sleeps after 15 minutes and both workers pause
with it: uploads sit at `pending` and research never starts until someone
opens the app.

- The repo ships a GitHub Actions template,
  [`keepalive.github-actions.yml`](./keepalive.github-actions.yml). GitHub only
  runs workflows from `.github/workflows/`, so copy it there once:

  ```bash
  mkdir -p .github/workflows
  cp infrastructure/render/keepalive.github-actions.yml .github/workflows/render-keepalive.yml
  ```

  then add a repository secret `RENDER_SERVICE_URL`
  (`https://<service>.onrender.com`) and the workflow pings `/` every
  10 minutes.
- Alternative: any free external pinger (e.g. cron-job.org) on the same URL
  and cadence.
- Caveat: GitHub pauses scheduled workflows after 60 days without repo
  activity — commit now and then, or use the external pinger.

---

## Part 5 — Limits and tuning

| Free-tier limit | Value | What to do |
| --- | --- | --- |
| RAM / CPU | 512 MB / 0.1 CPU | Ship the lean knobs from `render.yaml` (already the defaults there) |
| Idle spin-down | 15 min (~1 min wake) | Part 4 keep-alive |
| Instance hours | 750/month/workspace | One always-warm service ≈ 730 h — that's your budget |
| Bandwidth | 5 GB/month | Fine for a demo; upgrade before heavy file downloads |
| Persistent disk | None | No local state — by design, state lives in Supabase/Qdrant/Redis |
| Outbound SMTP | Blocked | Not needed by this app |
| No payment method on file | Service *suspended* for the rest of the month once hours run out | Watch the Render dashboard usage bar |

**Knobs that matter on 512 MB** (all already set lean in `render.yaml`;
compose defaults in parentheses):

| Variable | Free-tier | Compose default |
| --- | --- | --- |
| `DOCUMENT_WORKER_CONCURRENCY` | 1 | 4 |
| `RESEARCH_WORKER_CONCURRENCY` | 1 | 2 |
| `EMBEDDING_BATCH_SIZE` | 32 | 256 |
| `EMBEDDING_CONCURRENCY` | 2 | 4 |
| `CHUNK_INSERT_CONCURRENCY` | 1 | 2 |
| `QDRANT_UPSERT_CONCURRENCY` | 1 | 2 |
| `EVIDENCE_CONCURRENCY` | 2 | 4 |
| `RETRIEVAL_CONCURRENCY` | 2 | 4 |

Ingestion is I/O-bound, so these trade wall-clock time for memory — a large
PDF now takes a couple of minutes instead of seconds. If you see
`Killed` / exit code 137 in the logs, drop `EMBEDDING_BATCH_SIZE` to `16` or
move the workers to a paid instance and restore the compose values.

---

## Verification checklist

- [ ] `curl https://<render>/` returns `{"status":"running",…}`
- [ ] `curl https://<render>/api/v1/health` shows every service `up`
- [ ] Vercel app loads, sign-in works, no CORS errors in the browser console
- [ ] Upload a PDF → document leaves `pending` → `completed` within ~1–2 min
- [ ] Run a research question → report appears with citations
- [ ] Langfuse shows the research trace with spans and token usage
- [ ] Render logs show all three `[start-services]` process lines

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Vercel build fails at `onBuildComplete`: `ENOENT … next-server.js.nft.json` | Next 16.3 + Turbopack doesn't emit that file, but Vercel's tracing expects it when `output: "standalone"` is set | Already fixed: `next.config.ts` now sets standalone only when `VERCEL` is unset (Docker keeps it) — redeploy |
| Render deploy fails with a port error | Server bound to the wrong port | The start script binds `${PORT:-8000}`; keep `dockerCommand` as shipped |
| `Killed` / exit 137 in logs | OOM on the 512 MB instance | Lower `EMBEDDING_BATCH_SIZE`/concurrency (Part 5) |
| Browser: CORS error | `FRONTEND_URL` ≠ exact Vercel origin | Fix scheme/host/trailing slash; preview deploys need the same origin |
| Browser: "Missing NEXT_PUBLIC_SUPABASE_URL" | Env var missing at **build** time | Set it on Vercel, then **redeploy** (not just save) |
| Documents stuck at `pending` | Service asleep or a worker died | Confirm keep-alive; check logs for `[start-services]` lines |
| First request after idle takes ~1 min | Free-tier cold start | Keep-alive (Part 4) or a paid instance |
| Service suspended mid-month | 750 free hours exhausted | Wait for the monthly reset, or add a payment method |
| Build takes 5–10 min | Heavy Python deps (LangChain, LangGraph, FastMCP) | Normal; subsequent builds use layer cache |

## Upgrading later

- **Paid Render instance ($7/mo Starter):** remove the spin-down problem,
  raise the concurrency knobs back toward the compose defaults, and split the
  workers into their own background-worker services with
  `dockerCommand: python -m app.workers.document_worker` (and
  `…research_worker`) — then the combined start script is no longer needed.
- **Commercial use:** Vercel Hobby is non-commercial; move the frontend to
  Vercel Pro or another Next.js host.
