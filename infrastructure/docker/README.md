# Docker images

This directory documents the container images defined by the project.
Dockerfiles live next to their code (`backend/Dockerfile`,
`frontend/Dockerfile`) and the compose stack at the repository root
builds them with the repository root as build context.

## Images

| Image                | Dockerfile           | Runtime                                   |
| -------------------- | -------------------- | ----------------------------------------- |
| `agentflow-backend`  | `backend/Dockerfile` | Python 3.11-slim + Uvicorn on port 8000   |
| `agentflow-frontend` | `frontend/Dockerfile`| Next.js standalone server on port 3000    |

External managed services (Supabase, Qdrant, Langfuse) are **not**
containerized here — they are hosted and referenced by URL.

## Build & run

The recommended way to build and run the stack is:

```bash
docker compose up --build
```

Individual images can also be built manually:

```bash
docker build -f backend/Dockerfile -t agentflow-backend .
docker build -f frontend/Dockerfile -t agentflow-frontend .
```

The frontend image expects `NEXT_PUBLIC_*` build arguments (see
`frontend/.env.example`) so that the browser bundle contains the
public Supabase credentials and the API base URL:

```bash
docker build \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=... \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=... \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  -f frontend/Dockerfile -t agentflow-frontend .
```

## Health probes

- Backend: `GET http://localhost:8000/health`
- Frontend: `GET http://localhost:3000` returns the application shell
