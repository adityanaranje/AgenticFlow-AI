# AgentFlow AI

Multi-tenant **AI research platform**. An organization uploads its documents,
AgentFlow turns them into a searchable knowledge base, and an agentic workflow
researches questions against *only* that knowledge base — producing reports
where every claim carries a citation back to a source chunk.

The emphasis throughout is **grounding**: answers are assembled from retrieved
evidence, citations are validated before a report is stored, and ungrounded
sources are discarded rather than presented.

---

## What it does

| | |
| --- | --- |
| **Ingest** | Upload PDF / DOCX / TXT / MD. A background worker parses, chunks, embeds and indexes each file, with per-document progress and reprocessing. |
| **Retrieve** | Vector search over Qdrant, scoped to one organization, returning chunks with provenance (document, page, chunk index). |
| **Research** | A LangGraph agent plans sub-questions, retrieves evidence, detects gaps, loops for more evidence, then synthesises an answer. |
| **Cite & verify** | A citation-validation step checks every claim maps to real retrieved evidence; unsupported sources are dropped before the report is saved. |
| **Report** | Generated reports are stored per organization, listed and readable in the UI. |
| **Evaluate** | Each report is scored for `groundedness` (share of sentences carrying a citation) and `relevance` (mean retrieval score of cited sources). |
| **Collaborate** | Organizations with four roles, in-app join requests (accept/decline from your dashboard), and invariants enforced by database triggers. |
| **Stay in budget** | Per-user hourly/daily token limits, a concurrent-run cap and a per-run token budget, all Redis-backed. |

### Feature detail

**Documents.** Upload is size-capped (`MAX_UPLOAD_SIZE_MB`, default 25 MB) and
streamed to Supabase Storage; metadata and chunks live in PostgreSQL. Parsing,
chunking, embedding and vector upsert happen in a **background worker** so the
request returns immediately, and every stage is batched and concurrency-tuned
(see §9). A failed document can be reprocessed without re-uploading.

**Research.** A run is queued to a second worker and progresses through the
graph below. Runs can be cancelled, and the UI polls status and shows the
finished report with its citations.

**Roles.** `owner > admin > researcher > viewer`. Viewers read; researchers
additionally upload and run research; admins manage members; owners control
ownership and deletion. The role matrix is in §12 — and the rules are enforced
by a PostgreSQL trigger plus RLS, not only by the UI.

---

## 1. Which tool does what

Every dependency below is actually used; nothing is listed aspirationally.

### Core stack

| Tool | Used for | Where |
| --- | --- | --- |
| **Next.js 16** (App Router) + **React 19** | The whole UI, server-rendered. Server Components read Supabase directly; Route Handlers under `app/api/**` proxy privileged mutations. | `frontend/app` |
| **TypeScript** + **Tailwind CSS v4** | Types across the frontend; all styling (no component library). | `frontend/` |
| **lucide-react** | Icon set. | `frontend/components` |
| **FastAPI** + **Uvicorn** | The backend HTTP API (`/api/v1/...`) and its OpenAPI docs. | `backend/app/api` |
| **Pydantic** / **pydantic-settings** | Request/response schemas and typed, env-driven configuration. | `backend/app/api/schemas.py`, `core/config.py` |
| **Supabase** | Three distinct jobs: **Auth** (email + Google OAuth), **PostgreSQL** (all relational data, RLS, triggers, `security definer` functions), and **Storage** (uploaded files). | everywhere |
| **PostgreSQL (via Supabase)** | Source of truth *and* the security boundary — RLS policies and the `organization_members_guard` trigger enforce the role rules. | `database/migrations` |

### AI / retrieval

| Tool | Used for | Where |
| --- | --- | --- |
| **OpenAI** | Chat completions (`OPENAI_CHAT_MODEL`, default `gpt-4o-mini`) for planning, evidence analysis and synthesis; embeddings (`OPENAI_EMBEDDING_MODEL`) for indexing and query vectors. | `backend/app/llm`, `services/embeddings.py` |
| **LangGraph** | Orchestrates the research workflow as a state graph with a **conditional loop** — the gap detector can send the run back to retrieval before synthesis. | `backend/app/agents/research_graph.py` |
| **LangChain** | Model client wrappers used by the agent nodes. | `backend/app/llm/models.py` |
| **Qdrant** | Vector database. Stores chunk embeddings, filtered by `organization_id` so tenants can never retrieve each other's content. | `backend/app/services/vector_store.py`, `rag/qdrant.py` |
| **pypdf** / **python-docx** | Extracting text from PDF and DOCX uploads, preserving page and heading structure. | `backend/app/services/document_parser.py` |
| **Langfuse** | LLM tracing/observability, plus **prompt management** — prompts are fetched from Langfuse with a local fallback and a short TTL cache. | `backend/app/core/observability.py`, `services/prompt_service.py` |

### Infrastructure

| Tool | Used for | Where |
| --- | --- | --- |
| **Redis** | Four jobs: the **job queue** feeding both workers, **caching** (LLM responses, embeddings, retrieval results), **token-quota counters**, and **concurrency locks**. | `backend/app/cache`, `services/job_queue.py`, `llm_guardrails.py` |
| **Background workers** | Two long-running consumers — `document_worker` (parse → chunk → embed → index) and `research_worker` (run the graph). Both shut down gracefully. | `backend/app/workers` |
| **Docker Compose** | Runs backend, both workers, frontend and Redis together. | `docker-compose.yml` |
| **pytest** | Backend tests, plus a SQL suite that runs migrations against a real ephemeral PostgreSQL (`pgserver`) to test triggers and RLS. | `backend/tests`, `database/tests` |
| **ESLint** | Frontend linting (`npx eslint app components lib --ext .ts,.tsx`). | `frontend/` |

> **Declared but unused:** `rank-bm25` and `fastmcp` appear in
> `requirements.txt`, and `backend/app/rag/hybrid.py`, `rag/reranker.py`,
> `app/tools/*` and `app/mcp/server.py` are empty placeholders. Hybrid BM25
> search, reranking, agent tools and the MCP server are **not** implemented
> yet — retrieval today is pure vector search.

### How the pieces talk

```
                 ┌──────────────── Supabase Auth (session cookie)
                 │
Browser ──► Next.js :3000 ──► FastAPI :8000 ──► OpenAI (chat + embeddings)
   │              │                │
   │              │                ├──► Qdrant     (vector search)
   │              │                ├──► Redis      (queue, cache, quotas)
   │              │                ├──► Supabase   (PostgreSQL + Storage)
   │              │                └──► Langfuse   (traces + prompts)
   │              │
   │              └─ Server Components read PostgreSQL through PostgREST,
   │                 constrained by the caller's RLS policies
   │
   └─ Uploads go to Supabase Storage

                 Redis queue
FastAPI ──enqueue──► ├──► document-worker  : parse → chunk → embed → Qdrant
                     └──► research-worker  : LangGraph run → report → evaluation
```

Supabase, Qdrant and Langfuse are **managed services** — they are not run
locally. The local stack is backend + workers + frontend + Redis.

### The research graph

```
START → planner → retriever → evidence_analyzer → gap_detector
                     ▲                                 │
                     └────── more evidence needed ──────┤
                            (max_iterations)            ▼
                                                    synthesis
                                                        ↓
                                               citation_validator
                                                        ↓
                                                    finalizer → END
```

| Node | Responsibility |
| --- | --- |
| `planner` | Break the question into sub-questions. |
| `retriever` | Vector-search the org's chunks for each sub-question. |
| `evidence_analyzer` | Extract and score the evidence that actually answers them. |
| `gap_detector` | Decide whether evidence is sufficient; if not, loop back with new queries (bounded by `MAX_RESEARCH_ITERATIONS`). |
| `synthesis` | Write the answer from the gathered evidence. |
| `citation_validator` | Check each citation resolves to real retrieved evidence. |
| `finalizer` | Assemble the report and persist only grounded sources. |

## 2. Repository layout

```
agentflow-ai/
├── backend/
│   ├── app/
│   │   ├── api/         # FastAPI routers: health, auth, organizations,
│   │   │                #   documents, research, reports, evaluations
│   │   ├── agents/      # LangGraph research graph
│   │   │   └── nodes/   #   planner, retriever, evidence_analyzer,
│   │   │                #   gap_detector, synthesis, citation_validator,
│   │   │                #   finalizer  (other files are placeholders)
│   │   ├── cache/       # Redis client
│   │   ├── core/        # config, auth/RBAC, logging, observability
│   │   ├── db/          # Supabase client + repositories
│   │   ├── llm/         # OpenAI / LangChain model clients
│   │   ├── rag/         # Qdrant collection management
│   │   ├── services/    # ingestion, retrieval, research, reports,
│   │   │                #   evaluation, membership, guardrails, prompts
│   │   ├── workers/     # document_worker + research_worker
│   │   └── main.py      # FastAPI entrypoint
│   └── tests/           # pytest suite
├── frontend/
│   ├── app/             # App Router: landing, auth, dashboard,
│   │                    #   organizations/{id}/{documents,research,
│   │                    #   reports,evaluations,members}, api/ handlers
│   ├── components/      # auth, brand, documents, evaluations,
│   │                    #   organizations, research
│   ├── lib/             # env, Supabase clients, organizations (RBAC,
│   │                    #   members), API helpers
│   └── scripts/         # check-env.mjs (`npm run doctor`)
├── database/
│   ├── migrations/      # 001-018, applied in filename order
│   ├── tests/           # SQL tests against a real ephemeral PostgreSQL
│   └── seed.sql
├── infrastructure/      # Docker image docs + dev Redis config
├── scripts/             # dev/bootstrap/benchmark helpers
└── docker-compose.yml
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

| Level            | Setting                        | Default | Enforced where        | On breach                                    |
| ---------------- | ------------------------------ | ------- | --------------------- | -------------------------------------------- |
| Per user / hour  | `LLM_USER_TOKEN_LIMIT_HOURLY`  | 100k    | dispatch (API)        | `429` with the window + used/limit details   |
| Per user / day   | `LLM_USER_TOKEN_LIMIT_DAILY`   | 200k    | dispatch (API)        | `429` as above                               |
| Per user, runs   | `LLM_USER_MAX_CONCURRENT_RUNS` | 2       | dispatch (API)        | `429` "already have N runs in progress"      |
| Per run          | `LLM_RUN_TOKEN_BUDGET`         | 100k    | worker, before each model call | run fails with a clear error; work so far is persisted |

**How much is left?** `GET /api/v1/organizations/{org}/research/quota`
(**researcher+** — the budget only gates *starting* a run, so it is withheld
from viewers, who cannot start one) returns the caller's remaining budget:

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
database — not just the application — refuses privilege escalation:
member management (`test_member_management.py`), the in-app invitation
requests including directory-enumeration limits
(`test_invitation_requests.py`), and profile visibility
(`test_profile_visibility.py`) — which runs as the `authenticated` role, not
the RLS-bypassing owner, so the policies are genuinely exercised.

### Frontend

```bash
cd frontend
npm install
npx tsc --noEmit                              # type-check
npx eslint app components lib --ext .ts,.tsx  # lint
npm run build
npm run doctor                                # verify Supabase env vars
```

> `npx next lint` has been removed from Next.js — call `eslint` directly.
> Run `npm install` first: `npx tsc` without `node_modules` silently
> installs an unrelated `tsc` package and exits 0, which looks like a pass.

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
indexes, member management, profile visibility). Apply them in a Supabase SQL
editor or via `psql`, in filename order, then run `database/seed.sql` for
development data
(it intentionally inserts nothing today — users/orgs are created through the
app).

> **Upgrading an existing database?** Apply `015_member_management.sql`,
> `016_invitation_requests.sql`, `017_member_profiles_visibility.sql`, then
> `018_member_profile_relationship.sql` — 017 and 018 are both required or
> the members list renders empty. See
> [`database/APPLY_MEMBER_MANAGEMENT.md`](database/APPLY_MEMBER_MANAGEMENT.md)
> for step-by-step instructions and verification queries.

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

**Adding members.** Works like a social follow request. An admin or owner
uses **Add a member** on the dashboard (or
`/organizations/{id}/members`), searches for the person, picks a role and
sends the request. The invitee sees it under **Invitations** on their own
dashboard the next time they sign in and can **Accept** or **Decline** —
no email round-trip needed.

If the address does not belong to an account yet, the inviter also gets a
one-time link (`/invitations/{token}`) to share. Invitations expire after
14 days, can be revoked, can only be accepted by the address they were
issued to, and someone who declined can be invited again.

**Finding people.** The picker is deliberately *not* a browsable user
directory. `search_invitable_users` requires the caller to be an
admin/owner of the target organization, matches only on a full exact email
address or a 3+ character name prefix, and never returns anybody's email
address to the browser. Resolving a picked user to an address happens
server-side via `resolve_invitable_email`, which repeats the admin check.

**Invariants enforced by the database** (migration 015, trigger
`organization_members_guard`) — not merely by the UI or API:

- an organization always keeps at least one owner (the last owner cannot be
  demoted, removed, or leave),
- only an owner may grant or revoke `owner` — including through an
  invitation: joining via an `owner` invite is refused unless whoever
  issued it is still an owner,
- nobody may change their own role, assign a role above their own, or act on
  a higher-ranked member,
- any member may leave voluntarily (`leave_organization`),
- membership rows are never inserted from the browser:
  `create_organization`, `accept_invitation` and `respond_to_invitation`
  are `security definer` functions that derive the user from `auth.uid()`,
- a user can only ever list or answer their *own* invitations
  (`my_pending_invitations` / `respond_to_invitation` pin every query to
  the caller's verified email, and never expose the invitation token).

The frontend helpers in `lib/organizations/rbac.ts` only shape the UI; RLS,
the guard trigger, and `backend/app/core/rbac.py` are the security boundary.

## 13. API reference

All backend routes are versioned under `/api/v1` and require a Supabase
session; every one is additionally authorised against the caller's role in
the target organization.

**Organizations** — `/api/v1/organizations`

| Method | Path | Min role |
| --- | --- | --- |
| `GET` | `` | — (your orgs) |
| `GET` | `/{id}` | viewer |
| `GET` | `/{id}/members` | viewer |
| `POST` | `/{id}/members` | admin |
| `PATCH` | `/{id}/members/{user_id}` | admin |
| `DELETE` | `/{id}/members/me` | any member |
| `DELETE` | `/{id}/members/{user_id}` | admin |
| `GET` | `/{id}/invitations` | admin |
| `DELETE` | `/{id}/invitations/{invitation_id}` | admin |

**Documents** — `/api/v1/organizations/{id}/documents`

| Method | Path | Min role |
| --- | --- | --- |
| `POST` | `/upload` | researcher |
| `GET` | `` · `/{document_id}` · `/{document_id}/chunks` | viewer |
| `GET` | `/{document_id}/retrieve` | viewer |
| `POST` | `/{document_id}/reprocess` | researcher |
| `DELETE` | `/{document_id}` | admin |

**Research** — `/api/v1/organizations/{id}/research`

| Method | Path | Min role |
| --- | --- | --- |
| `POST` | `` (start a run) | researcher |
| `GET` | `` · `/{research_id}` | viewer |
| `GET` | `/quota` | researcher |
| `POST` | `/{research_id}/cancel` | viewer |

**Reports** — `/api/v1/organizations/{id}/reports`

| Method | Path | Min role |
| --- | --- | --- |
| `GET` | `` · `/{report_id}` | viewer |
| `DELETE` | `/{report_id}` | admin |

**Evaluations** — `/api/v1/organizations/{id}/evaluations`

| Method | Path | Min role |
| --- | --- | --- |
| `GET` | `` · `/{run_id}` | viewer |
| `POST` | `` (score a report) | researcher |

**Health** — `GET /health` and `GET /api/v1/health`, unauthenticated (§11).

Interactive docs: <http://localhost:8000/docs>.

Some privileged mutations are also exposed as Next.js Route Handlers under
`frontend/app/api/**` (invitation accept/respond, member search) so the
browser never receives a Supabase service key.

## 14. Current limitations

- **Retrieval is pure vector search.** Hybrid BM25 (`rag/hybrid.py`) and
  reranking (`rag/reranker.py`) are empty placeholders, as are the agent
  tools in `app/tools/` (web search, calculator, database) and the MCP
  server. `rank-bm25` and `fastmcp` are declared in `requirements.txt` but
  not yet imported anywhere.
- **Evaluation is heuristic, not model-graded.** `groundedness` counts
  sentences carrying a citation; `relevance` averages retrieval scores of
  cited sources. There is no LLM-as-judge step.
- **No conversational follow-up.** `api/conversations.py` is a placeholder;
  each research run is independent.
- Health checks report `Not configured` / `down` until real credentials are
  supplied — there is no bundled local Supabase/Qdrant/Langfuse.
- Five backend tests covering document parsing and ingestion limits require
  optional parser dependencies and fail without them.

---

*Grounded, multi-tenant AI research over your organization's own documents.*
