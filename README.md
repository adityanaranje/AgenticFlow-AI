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
| Backend       | Python 3.11+ · FastAPI · LangChain · LangGraph · OpenAI                     |
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

- Python **3.11+**
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

## 6. Local development

### Run the backend

```bash
./scripts/dev-backend.sh
# or manually:
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs — Health: http://localhost:8000/health

### Run the frontend

```bash
./scripts/dev-frontend.sh
# or manually:
cd frontend
npm run dev
```

Open http://localhost:3000. Sign-up / sign-in is handled by Supabase Auth:
email + password, or **Google OAuth** (Sign in with Google). To enable
Google, add the provider in your Supabase dashboard
(Authentication → Providers → Google) with the authorized redirect URL
`https://<your-app>/auth/callback` (in the Supabase dashboard for
`http://localhost:3000/auth/callback`). The dashboard reads the user
profile and organizations seeded by `database/migrations`.

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

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

## 9. Health endpoint

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

## 10. Database migrations

SQL migrations live in `database/migrations/` (extensions, profiles,
organizations, documents, research, reports, evaluations, RLS, storage,
indexes). Apply them in a Supabase SQL editor or via `psql`, in filename
order, then run `database/seed.sql` for development data (it intentionally
inserts nothing today — users/orgs are created through the app).

## 11. Phase 1 completion checklist

- [x] Backend starts successfully
- [x] Frontend starts successfully
- [x] `GET /health` works (structured, degraded-safe)
- [x] Connectivity wiring for OpenAI, Supabase, Qdrant, Redis, Langfuse
- [x] Frontend `npm run lint` + `npm run build` pass
- [x] Backend `pytest` passes
- [x] No hard-coded secrets; `.env.example` files exist at root/backend/frontend

## 12. Known limitations (Phase 1)

- Health checks report `Not configured`/`down` until real credentials are
  supplied — there is no bundled local Supabase/Qdrant/Langfuse.
- Backend API routers for auth/organizations/documents/research/reports/
  evaluations are registered placeholders (no endpoints yet, by design).
- Dockerfiles and compose are validated as configuration; image builds
  require Docker with network access to registries.
- Qdrant collection creation, Redis cache keys and Langfuse tracing
  call-sites arrive with their consuming features in later phases.

## 13. Next phase (Phase 2 — expected scope)

Multi-tenant foundation: organization CRUD, membership/roles, Supabase RLS
aligned endpoints (`/api/v1/organizations`, `/api/v1/auth`), document upload
to Supabase Storage with metadata persistence in PostgreSQL, and backend
test coverage for those flows. Phase 2 should not start until explicitly
instructed.

---

*Phase 1 — Project Foundation and Infrastructure.*
