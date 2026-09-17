# AgentFlow AI

Production-oriented, multi-tenant **AI research platform**. Organizations upload
documents, build a searchable knowledge base, run AI-powered research,
generate reports, and evaluate the quality of generated answers.

> **Status: Phase 1 — Project Foundation & Infrastructure**
> This phase delivers the application shell, health-checked service wiring and
> development infrastructure. AI functionality (RAG, agents, evaluation) is
> intentionally **not** implemented yet — no fake AI endpoints are exposed.

---

## 1. Architecture

| Layer         | Technology                                                                 |
| ------------- | -------------------------------------------------------------------------- |
| Frontend      | Next.js (App Router) · TypeScript · React · Supabase Auth · Supabase Storage |
| Backend       | Python 3.10+ · FastAPI · LangChain · LangGraph · OpenAI                     |
| Infrastructure| Supabase (PostgreSQL + Storage) · Qdrant · Redis · Langfuse                |
| AI            | OpenAI models · Embeddings · RAG · Agentic research workflow (LangGraph)   |
| Observability | Langfuse                                                                   |

```
Browser ──► Next.js (frontend, :3000) ──► FastAPI (backend, :8000) ──► OpenAI
   │                                                                    │
   ├─ Supabase Auth (browser)            Redis (cache) ◄────────────────┘
   └─ Supabase Storage / PostgREST        Qdrant (vector DB)
                                          Langfuse (traces / prompts)
```

External managed services (Supabase, Qdrant, Langfuse) are **not** duplicated
locally; the development stack runs only the backend, frontend and Redis.

## 2. Repository layout

```
agentflow-ai/
├── backend/
│   ├── app/
│   │   ├── api/        # API routers (health, auth, documents, research, ...)
│   │   ├── agents/     # LangGraph agent modules (later phases)
│   │   ├── core/       # config, logging, exceptions, langfuse
│   │   ├── db/         # Supabase client + repositories
│   │   ├── llm/        # OpenAI clients
│   │   ├── models/     # (later phases)
│   │   ├── rag/        # Qdrant / embeddings (later phases)
│   │   ├── schemas/    # Pydantic API schemas
│   │   ├── services/   # health + business services
│   │   ├── tools/      # agent tools (later phases)
│   │   └── main.py     # FastAPI entrypoint
│   ├── tests/          # pytest suite
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/            # App Router pages (login, signup, dashboard, ...)
│   ├── components/     # UI components
│   ├── lib/            # env config, API client, Supabase clients
│   ├── hooks/          # (later phases)
│   ├── types/          # (later phases)
│   ├── package.json
│   ├── Dockerfile
│   └── .env.example
├── database/
│   ├── migrations/     # Supabase/PostgreSQL migrations (001-011)
│   └── seed.sql
├── infrastructure/
│   ├── docker/         # Image documentation
│   └── redis/          # Dev Redis configuration
├── scripts/            # Dev helper scripts
├── docker-compose.yml
├── .gitignore
├── README.md
└── .env.example
```

## 3. Prerequisites

- Python **3.10+** (3.11 and 3.12 also work: the code stays inside the 3.10
  stdlib surface, and `python -m pytest` enforces that)
- Node.js **20+** and npm **10+**
- Docker + Docker Compose (optional, for the containerized stack)
- Accounts / endpoints for the external services:
  - [OpenAI](https://platform.openai.com) — API key
  - [Supabase](https://supabase.com) — project URL + anon key + service-role key
  - [Qdrant](https://qdrant.tech) — cluster URL + API key
  - Redis — local or hosted instance
  - [Langfuse](https://langfuse.com) — public/secret keys + host

## 4. Installation

### 4.1 Clone & configure

```bash
git clone <repository-url>
cd agentflow-ai

# Backend environment
cp backend/.env.example backend/.env         # fill in real values

# Frontend environment  (NEXT_PUBLIC_SUPABASE_URL + the publishable key,
# or the legacy anon key). `npm run dev` only reads frontend/.env*, never this
# root file - and it inlines NEXT_PUBLIC_* values at start-up, so restart it
# after every edit.
cp frontend/.env.example frontend/.env.local

# (Optional) docker-compose environment
cp .env.example .env

# Validate what the frontend will actually load
(cd frontend && npm run doctor)             # add -- --copy to create the file
```

### 4.2 Backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

or:

```bash
./scripts/bootstrap.sh
```

### 4.3 Frontend

```bash
cd frontend
npm install
```

## 5. Environment variables

| Variable                          | Used by    | Required | Notes                                     |
| --------------------------------- | ---------- | :------: | ----------------------------------------- |
| `ENVIRONMENT`                     | backend    |          | `development` (default) / `production`    |
| `API_HOST` / `API_PORT`           | backend    |          | Bind host / port (default `0.0.0.0:8000`) |
| `FRONTEND_URL`                    | backend    |          | CORS origin (default `http://localhost:3000`) |
| `OPENAI_API_KEY`                  | backend    |    🔒    | Backend-only                              |
| `OPENAI_MODEL`                    | backend    |          | Default `gpt-4o-mini`                     |
| `OPENAI_EMBEDDING_MODEL`          | backend    |          | Default `text-embedding-3-small`          |
| `SUPABASE_URL`                    | both       |    ✅    | Project URL                               |
| `SUPABASE_ANON_KEY`               | both       |    ✅    | Public anon key (browser-safe)            |
| `SUPABASE_SERVICE_ROLE_KEY`       | backend    |    🔒    | **Never expose to the browser**           |
| `QDRANT_URL`                      | backend    |    🔒    | Cluster URL                               |
| `QDRANT_API_KEY`                  | backend    |    🔒    | **Never expose to the browser**           |
| `QDRANT_COLLECTION`               | backend    |          | Default `agentflow_documents`             |
| `REDIS_URL`                       | backend    |          | Default `redis://localhost:6379/0`        |
| `EMBEDDING_BATCH_SIZE`            | backend    |          | Chunk texts per embedding request (default `256`) |
| `EMBEDDING_CONCURRENCY`           | backend    |          | Embedding requests in flight (default `4`) |
| `EMBEDDING_MAX_RETRIES`           | backend    |          | Retries for transient provider errors (default `3`) |
| `CHUNK_INSERT_BATCH_SIZE`         | backend    |          | Chunk rows per bulk insert (default `200`) |
| `CHUNK_INSERT_CONCURRENCY`        | backend    |          | Bulk inserts in flight (default `2`)      |
| `QDRANT_UPSERT_BATCH_SIZE`        | backend    |          | Points per Qdrant upsert request (default `128`) |
| `QDRANT_UPSERT_CONCURRENCY`       | backend    |          | Qdrant upserts in flight (default `2`)    |
| `DOCUMENT_WORKER_CONCURRENCY`     | backend    |          | Documents processed in parallel (default `4`) |
| `DOCUMENT_WORKER_POLL_SECONDS`    | backend    |          | Idle queue poll interval (default `2`)    |
| `INLINE_PROCESSING_WORKERS`       | backend    |          | Threads for the no-Redis upload fallback (default `2`) |
| `OPENAI_TIMEOUT_SECONDS`          | backend    |          | Per-request model timeout (default `60`)  |
| `RESEARCH_LLM_MAX_RETRIES`        | backend    |          | Retries for transient model errors (default `2`) |
| `RETRIEVAL_CONCURRENCY`           | backend    |          | Queries retrieved in parallel (default `4`) |
| `EVIDENCE_BATCH_CHARS`            | backend    |          | Excerpt characters per analysis call (default `60000`) |
| `EVIDENCE_CONCURRENCY`            | backend    |          | Analysis calls in flight (default `4`)    |
| `EVIDENCE_MAX_CHUNKS`             | backend    |          | Chunks analysed per run (default `48`)    |
| `RESEARCH_WORKER_CONCURRENCY`     | backend    |          | Research runs in parallel (default `2`)   |
| `RESEARCH_WORKER_POLL_SECONDS`    | backend    |          | Idle queue poll interval (default `2`)    |
| `RESEARCH_UNCLAIMED_FALLBACK_SECONDS` | backend |         | Take over a run no worker claimed (default `15`; `0` = off) |
| `REPORT_SOURCE_BATCH_SIZE`        | backend    |          | Rows per report source insert (default `100`) |
| `EMBEDDING_CACHE_TTL_SECONDS`     | backend    |          | TTL for cached query embeddings (default `3600`) |
| `LLM_USER_TOKEN_LIMIT_HOURLY`     | backend    |          | Per-user hourly token quota, `0` = unlimited (default `100000`) |
| `LLM_USER_TOKEN_LIMIT_DAILY`      | backend    |          | Per-user daily token quota, `0` = unlimited (default `200000`) |
| `LLM_USER_MAX_CONCURRENT_RUNS`    | backend    |          | Max queued/in-flight research runs per user, `0` = unlimited (default `2`) |
| `LLM_RUN_TOKEN_BUDGET`            | backend    |          | Token budget for one research run, `0` = unlimited (default `100000`) |
| `RESEARCH_RUN_SLOT_TTL_SECONDS`   | backend    |          | TTL for a run's concurrency slot (default `3600`) |
| `RESEARCH_MAX_REPORT_CHARS`       | backend    |          | Output guardrail: max stored report length (default `100000`) |
| `LANGFUSE_HOST`                   | backend    |    🔒    | Default `https://cloud.langfuse.com`      |
| `LANGFUSE_PUBLIC_KEY`             | backend    |    🔒    | Backend-only                              |
| `LANGFUSE_SECRET_KEY`             | backend    |    🔒    | **Never expose to the browser**           |
| `NEXT_PUBLIC_SUPABASE_URL`        | frontend   |    ✅    | Inlined into the browser bundle           |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | frontend |   ✅    | Publishable key (`sb_publishable_...`) - preferred |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`   | frontend   |    ✅    | Legacy anon key; used when the publishable one is unset |
| `NEXT_PUBLIC_API_URL`             | frontend   |          | Backend base URL (default `http://localhost:8000`) |

**Security rules (enforced by design):** secrets are never hard-coded; the
service-role key, Langfuse secret and Qdrant key exist only server-side and
must never be given a `NEXT_PUBLIC_` prefix or referenced by frontend code.
`backend/.env.example` and `frontend/.env.example` document exactly this
split. Supabase renamed "anon" to "publishable" (and "service_role" to
"secret", `sb_secret_...`); both frontend variable names are accepted and the
legacy keys still work while enabled, but new projects only get the new ones.

### 5.1 LLM usage guardrails

Research runs make a chain of model calls, so per-user token spend is
bounded at four levels (all Redis-backed, all `0` = unlimited; degrades to
"allowed" when Redis is down, so a missing Redis never breaks dev setups):

| Level            | Setting                        | Enforced where        | On breach                                    |
| ---------------- | ------------------------------ | --------------------- | -------------------------------------------- |
| Level            | Setting                        | Default | Enforced where        | On breach                                    |
| ---------------- | ------------------------------ | ------- | --------------------- | -------------------------------------------- |
| Per user / hour  | `LLM_USER_TOKEN_LIMIT_HOURLY`  | 100k    | dispatch (API)        | `429` with the window + used/limit details   |
| Per user / day   | `LLM_USER_TOKEN_LIMIT_DAILY`   | 200k    | dispatch (API)        | `429` as above                               |
| Per user, runs   | `LLM_USER_MAX_CONCURRENT_RUNS` | 2       | dispatch (API)        | `429` "already have N runs in progress"      |
| Per run          | `LLM_RUN_TOKEN_BUDGET`         | 100k    | worker, before each model call | run fails with a clear error; work so far is persisted |

**How much is left?** `GET /api/v1/organizations/{org}/research/quota`
(authenticated, viewer+) returns the caller's remaining budget:

```json
{
  "hourly": { "used": 12000, "limit": 100000, "remaining": 88000 },
  "daily":  { "used": 47000, "limit": 200000, "remaining": 153000 },
  "concurrent_runs": { "active": 1, "limit": 2 },
  "run_token_budget": 100000,
  "enforced": true
}
```

`remaining` is `null` for a disabled limit (`0` = unlimited) and
`enforced` is `false` when Redis is down (counters then read 0).

Tokens are the **real usage** reported by the model provider (estimated
from character counts only when a provider omits usage); cached LLM
responses consume none. Related input/output guardrails: the research
question is capped at 4000 characters, client-supplied run config is
whitelisted + clamped (`top_k ≤ 50`, `max_subquestions ≤ 10`,
`max_iterations ≤ 5`, `max_chunks ≤ 500`), and stored reports are truncated
at `RESEARCH_MAX_REPORT_CHARS` with a visible marker.

## 6. Local development

### Run the backend

```bash
./scripts/dev-backend.sh
# or manually:
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs — Health: http://localhost:8000/health

### Run the workers (**required** for uploads and research)

The API only *queues* work. Uploaded documents stay `pending` and research runs
stay `queued` until a worker process consumes the Redis queue:

```bash
./scripts/dev-workers.sh
# or, manually (one terminal each, from backend/):
python -m app.workers.document_worker    # parse -> chunk -> embed -> Qdrant
python -m app.workers.research_worker    # plan -> retrieve -> analyse -> report
```

On Windows PowerShell use `.\scripts\dev-workers.ps1` (add `-NoWindow` to keep
both logs in the current console).

Symptoms of a missing worker: a research run stuck on **"Queued — waiting for a
worker"**, or an uploaded document stuck on `pending`/`processing`. If Redis is
not configured at all (no `REDIS_URL`), the API process runs the work itself in
its background pool — but the recommended setup is the two worker processes,
exactly as `docker compose` does it.

After `RESEARCH_UNCLAIMED_FALLBACK_SECONDS` (default `15`, `0` disables) the API
also takes a research run over when nothing has consumed its queue message, so a
single-process dev setup still works; the takeover is an atomic queue claim, so
a job can never run twice.

### Run the frontend

```bash
./scripts/dev-frontend.sh
# or manually:
cd frontend
npm run dev
```

Open http://localhost:3000. Sign-up / sign-in is handled by Supabase Auth:
email + password, or **Google OAuth** (Sign in with Google). The dashboard
reads the user profile and organizations seeded by `database/migrations`.

### Google OAuth: which URL goes where

Three lists have to agree, and putting the *app* URL in the *provider* list is
what produces Google's `Access blocked: This app's request is invalid`
(`redirect_uri_mismatch`). During the provider hop Google only ever talks to
your **Supabase project**, never to `localhost:3000`:

| Where | Value |
| ----- | ----- |
| Google Cloud → Auth Platform → Clients → your **Web application** client → *Authorized redirect URIs* | the Supabase project callback shown on the Google provider page — `https://<project-ref>.supabase.co/auth/callback` |
| Google Cloud → same client → *Authorized JavaScript origins* | `http://localhost:3000`, your deployed origin, and any preview origin |
| Supabase → Authentication → URL Configuration → *Site URL* | `http://localhost:3000` (dev) / the production origin |
| Supabase → Authentication → URL Configuration → *Redirect URLs* | `http://localhost:3000/auth/callback` (or `http://localhost:3000/**` in dev) plus the deployed equivalent |
| Supabase → Authentication → Sign In / Providers → Google | Client ID + Client Secret, provider enabled; scopes `openid`, `email`, `profile` |

`components/auth/GoogleButton.tsx` sends `redirectTo = <app origin>/auth/callback`
(PKCE) and `app/auth/callback/route.ts` exchanges the code — both must stay in
Supabase's *Redirect URLs* list, never in Google's.

Then verify without a browser:

```bash
cd frontend && npm run doctor     # probes /auth/v1/authorize and prints the exact
                                  # redirect_uri Supabase sends to Google
```

The dev login page also lists every value above, pre-filled from your
configured project URL and the request's own origin, under
“Google sign-in setup — exact URLs to paste”.

Notes: Google takes ~1 minute to propagate client changes; keep the OAuth
client's *Audience* set so your account can sign in (an unverified app in
“Testing” mode only lets approved test users); use the same host you visit
(`localhost` vs `127.0.0.1` are different origins — register both). Running a
local `supabase start` stack instead of the hosted one? Register
`http://127.0.0.1:54321/auth/v1/callback` with Google.

```bash
cd frontend && npm run doctor
```

Checks what Next.js will actually load — which `.env*` file each value comes
from, placeholders/quotes/UTF-16 files, an empty shell variable shadowing your
file, secret keys in browser variables, keys belonging to another project, and
(live) whether Supabase accepts the URL + key pair.

### Troubleshooting: “Missing NEXT_PUBLIC_SUPABASE_URL”

Sign-in is compiled into the browser bundle, so this family of errors is about
the *build*, not the account. In order of likelihood:

1. **Wrong file.** Values must be in `frontend/.env.local` (or
   `frontend/.env`). The repository root `.env` is only read by
   docker-compose.
2. **No restart.** `NEXT_PUBLIC_*` values are read when the dev server starts.
   Restart it (`Ctrl+C`, `npm run dev`); you should see
   `Reload env: .env.local` in the terminal. A production image needs a
   rebuild — see `frontend/Dockerfile` build args.
3. **Empty value in your shell.** `NEXT_PUBLIC_SUPABASE_URL=""` exported in the
   terminal wins over every file (Next.js stops at the first definition).
4. **Blank / placeholder line** left over from copying `.env.example`, or a
   value quoted, truncated, or with a path appended.
5. **Secret key in the frontend.** `sb_secret_...` / a `service_role` JWT in a
   `NEXT_PUBLIC_*` variable is rejected on purpose — it would be shipped to
   every browser. Use the publishable key.

The login and sign-up pages show the exact problem and the fix instead of a
generic failure, the dev server prints the same in your terminal, and
`npm run doctor` explains all five cases with commands.

## 7. Docker usage

```bash
docker compose up --build
```

| Service    | Container            | URL                            |
| ---------- | -------------------- | ------------------------------ |
| frontend   | `agentflow-frontend` | http://localhost:3000          |
| backend    | `agentflow-backend`  | http://localhost:8000/health   |
| redis      | `agentflow-redis`    | redis://localhost:6379/0       |

The frontend image bakes `NEXT_PUBLIC_*` values into the browser bundle at
**build** time, so `docker compose build` fails with a `BUILD ERROR:` line when
`NEXT_PUBLIC_SUPABASE_URL` / the publishable key are missing from the root
`.env` (a green build with a broken sign-in is worse). Pass
`--build-arg REQUIRE_SUPABASE_ENV=0` for a build that intentionally carries no
credentials.

Supabase, Qdrant and Langfuse remain external — point the stack at your
hosted instances through the root `.env` file (see `.env.example`).
Image build details: `infrastructure/docker/README.md`.

## 8. Testing

### Backend (`pytest`)

```bash
# from the repository root (uses backend/tests + backend pythonpath)
pytest
# or with coverage:
.venv/bin/pip install pytest-cov
pytest --cov=app
```

The suite covers:

- `GET /health` (and `/api/v1/health`) degrade gracefully when services are
  unconfigured/unreachable and report `healthy` when every service is up
- configuration loading, env aliases (`OPENAI_MODEL`, `LANGFUSE_HOST`) and
  empty-by-default secrets
- application startup/shutdown, CORS, router registration, and OpenAPI
  exposing no secrets
- ingestion and research performance contracts (`test_ingestion_performance.py`,
  `test_research_performance.py`): batched/parallel provider calls, bounded
  prompts, progress-only mid-run writes and deterministic fallbacks
- interpreter floor (`test_python_compat.py`): no 3.11+/3.12+ only API may enter
  the shipped code, so the backend still runs on Python 3.10
- organization membership rules (`test_membership.py`): invitations, role
  changes, removals and the "always at least one owner" invariant

### Database (`pytest database/tests`)

The member-management guard rules are verified against a **real**
PostgreSQL instance, started and thrown away by the test run:

```bash
pip install pgserver "psycopg[binary]" pytest
pytest database/tests
```

The harness stubs Supabase's `auth` schema (`auth.users`, `auth.uid()`,
`auth.jwt()`), applies every migration in order, and then asserts the
database — not just the application — refuses privilege escalation.

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

## 9. Ingestion performance

Uploading a document is fast because it is decoupled from ingestion: the
`POST .../documents/upload` request validates the file, writes the record and
the bytes, and hands the job to the document worker (or, when Redis is not
configured, to an in-process background pool). It never runs the pipeline
itself, so response time does not grow with document size. Clients follow
progress by polling the document's `status` (`pending` → `processing` →
`completed`/`failed`).

Chunking is pure CPU and cheap (a 300-page, ~930 KB document chunks in a few
milliseconds); ingestion wall-clock time is dominated by remote calls. Each
stage is therefore batched and overlapped:

| Stage            | How it is accelerated                                                     |
| ---------------- | ------------------------------------------------------------------------- |
| Embeddings       | `EMBEDDING_BATCH_SIZE` texts per request, `EMBEDDING_CONCURRENCY` requests in flight, transient errors retried with backoff |
| Chunk rows (DB)  | `create_chunks` bulk insert, `CHUNK_INSERT_BATCH_SIZE` rows per request, `CHUNK_INSERT_CONCURRENCY` batches in flight |
| Qdrant vectors   | `QDRANT_UPSERT_BATCH_SIZE` points per request, `QDRANT_UPSERT_CONCURRENCY` requests in flight |
| DB + vector write| The two writes are independent and run at the same time; the pre-delete of previous chunks/vectors runs concurrently too |
| Multiple uploads | `DOCUMENT_WORKER_CONCURRENCY` documents are consumed in parallel (each `document-worker` container; scale replicas too) |

Measure a change without touching the real services:

```bash
python scripts/benchmark-ingestion.py --paragraphs 2000   # ~500 chunks
```

With simulated latencies (20 ms PostgREST, 300 ms embeddings, 150 ms Qdrant,
120 ms storage) the same 500-chunk document went from **13.3 s / 504 insert
requests / 8 embedding requests** to **1.2 s / 4 insert requests / 2 embedding
requests**. Tune the knobs above per deployment — raise the batch sizes to
save round trips, lower them (or the concurrency) if a provider rate-limits
you.

## 10. Research performance

A research run is a chain of *dependent* model calls (plan → retrieve →
analyse → check gaps → …→ synthesise), so latency cannot be removed by
throwing concurrency at the whole pipeline. What can be improved is the work
that is independent, and how tightly each provider call is bounded:

| Stage              | How it is accelerated                                                     |
| ------------------ | ------------------------------------------------------------------------- |
| Retrieval          | Every open query is resolved together: **one** embeddings request for all query texts, then `RETRIEVAL_CONCURRENCY` vector searches in parallel — instead of an embedding + search round trip per query |
| Evidence analysis  | Chunks are map-reduced in parallel batches of `EVIDENCE_BATCH_CHARS`, capped at the `EVIDENCE_MAX_CHUNKS` highest-scoring chunks — a prompt can no longer exceed the model's context window (which previously made the whole run fail) |
| Model calls        | `OPENAI_TIMEOUT_SECONDS` bounds each request (the SDK default is 600 s) and transient errors are retried with backoff (`RESEARCH_LLM_MAX_RETRIES`) |
| Progress writes    | Mid-run `graph_state` writes carry status/counters/queries only; the full state (chunks, evidence, report) is written once when the run ends. Cancellation checks read only the `status` column |
| Report storage     | Citation rows are inserted in bulk (`REPORT_SOURCE_BATCH_SIZE`) instead of one request per citation |
| Repeat questions   | Query embeddings are cached (`EMBEDDING_CACHE_TTL_SECONDS`, `EMBEDDING_CACHE_ENABLED`) — a query vector is a pure function of its text, so the cache can never go stale |
| Several questions  | `RESEARCH_WORKER_CONCURRENCY` runs execute in parallel per worker process |

Measure it without touching the real services:

```bash
python scripts/benchmark-research.py                          # typical run
python scripts/benchmark-research.py --subquestions 8         # 9 open queries
python scripts/benchmark-research.py --chunks-per-query 150   # large corpus
```

With simulated latencies (2.5 s per model call, 300 ms per embeddings
request, 100 ms per vector search, 20 ms per PostgREST round trip):

| Scenario                        | Before                                   | After                        |
| ------------------------------- | ---------------------------------------- | ---------------------------- |
| 4 sub-questions, 5 chunks/query  | 12.3 s · 5 embeddings · 124 KB of progress writes | 10.8 s · 1 embedding · 24 KB |
| 8 sub-questions (9 queries)      | 13.9 s · 9 embeddings · 9 searches serial | 10.9 s · 1 embedding · 9 searches parallel |
| Large corpus (287 chunks)        | run **failed** (prompt exceeded the model window) | completed, citations produced |

The remaining wall-clock time is the dependent model calls themselves; reduce
`max_iterations`, `max_subquestions` or `top_k` per run (or use a faster chat
model) to trade depth for latency.

## 11. Health endpoint

`GET /health` (also `GET /api/v1/health`) checks **OpenAI · Supabase ·
Qdrant · Redis · Langfuse** without crashing when one is unavailable:

```json
{
  "status": "healthy",
  "openai":    { "status": "up",   "detail": "Connected" },
  "supabase":  { "status": "up",   "detail": "Connected" },
  "qdrant":    { "status": "up",   "detail": "Connected" },
  "redis":     { "status": "up",   "detail": "Connected" },
  "langfuse":  { "status": "up",   "detail": "Connected" }
}
```

If any dependency is down or not configured the overall status becomes
`degraded` (HTTP 200) with per-service `down` details — the API keeps serving.

```bash
./scripts/check-health.sh          # polls backend + frontend
curl http://localhost:8000/health
```

## 12. Database migrations

SQL migrations live in `database/migrations/` (extensions, profiles,
organizations, documents, research, reports, evaluations, RLS, storage,
indexes, member management). Apply them in a Supabase SQL editor or via
`psql`, in filename order, then run `database/seed.sql` for development data
(it intentionally inserts nothing today — users/orgs are created through the
app).

### Organizations, members and roles

Roles are `owner > admin > researcher > viewer`, defined once in the
database (`organization_members_role_check`) and mirrored in
`backend/app/core/rbac.py` and `frontend/lib/organizations/types.ts`.

| Capability | viewer | researcher | admin | owner |
| ---------- | :----: | :--------: | :---: | :---: |
| Read documents, research, reports | ✅ | ✅ | ✅ | ✅ |
| Upload documents, run research | — | ✅ | ✅ | ✅ |
| Invite / remove members, change roles | — | — | ✅ | ✅ |
| Grant or revoke the `owner` role | — | — | — | ✅ |
| Delete the organization | — | — | — | ✅ |

**Adding members.** An admin or owner opens
`/organizations/{id}/members` and invites by email. If the address already
belongs to a registered user they are added immediately; otherwise a
pending invitation is created and the inviter gets a one-time link
(`/invitations/{token}`) to share. Invitations expire after 14 days, can be
revoked, and can only be accepted by the address they were issued to.

**Invariants enforced by the database** (migration 015, trigger
`organization_members_guard`) — not merely by the UI or API:

- an organization always keeps at least one owner (the last owner cannot be
  demoted, removed, or leave),
- only an owner may grant or revoke `owner`,
- nobody may change their own role, assign a role above their own, or act on
  a higher-ranked member,
- any member may leave voluntarily (`leave_organization`),
- membership rows are never inserted from the browser: `create_organization`
  and `accept_invitation` are `security definer` functions that derive the
  user from `auth.uid()`.

The frontend helpers in `lib/organizations/rbac.ts` only shape the UI; RLS,
the guard trigger, and `backend/app/core/rbac.py` are the security boundary.

## 13. Phase 1 completion checklist

- [x] Backend starts successfully
- [x] Frontend starts successfully
- [x] `GET /health` works (structured, degraded-safe)
- [x] Connectivity wiring for OpenAI, Supabase, Qdrant, Redis, Langfuse
- [x] Frontend `npm run lint` + `npm run build` pass
- [x] Backend `pytest` passes
- [x] No hard-coded secrets; `.env.example` files exist at root/backend/frontend

## 14. Known limitations (Phase 1)

- Health checks report `Not configured`/`down` until real credentials are
  supplied — there is no bundled local Supabase/Qdrant/Langfuse.
- Backend API routers for auth/organizations/documents/research/reports/
  evaluations are registered placeholders (no endpoints yet, by design).
- Dockerfiles and compose are validated as configuration; image builds
  require Docker with network access to registries.
- Qdrant collection creation, Redis cache keys and Langfuse tracing
  call-sites arrive with their consuming features in later phases.

## 15. Next phase (Phase 2 — expected scope)

Multi-tenant foundation: organization CRUD, membership/roles, Supabase RLS
aligned endpoints (`/api/v1/organizations`, `/api/v1/auth`), document upload
to Supabase Storage with metadata persistence in PostgreSQL, and backend
test coverage for those flows. Phase 2 should not start until explicitly
instructed.

---

*Phase 1 — Project Foundation and Infrastructure.*
