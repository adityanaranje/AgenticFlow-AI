# AgentFlow AI — Frontend

Next.js (App Router) + TypeScript application shell for AgentFlow AI.
Supabase handles authentication; the FastAPI backend
(`../backend`) serves the versioned `/api/v1` API.

## Stack

- Next.js 16 (App Router, React 19, TypeScript)
- Tailwind CSS v4
- Supabase (`@supabase/ssr` + `@supabase/supabase-js`)

## Getting started

Requirements: Node.js 20+ and npm 10+.

```bash
# 1. Configure environment (see .env.example)
cp .env.example .env.local
#    -> set NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY,
#       NEXT_PUBLIC_API_URL (defaults to http://localhost:8000)

# 2. Install and run
npm install
npm run dev          # http://localhost:3000
```

## Scripts

| Command        | Purpose                          |
| -------------- | -------------------------------- |
| `npm run dev`  | Development server on port 3000  |
| `npm run lint` | ESLint (`eslint-config-next`)    |
| `npm run build`| Production build (standalone)    |
| `npm run start`| Serve the production build       |

## Structure

```
app/            # App Router pages (login, signup, dashboard, auth routes)
components/     # Reusable UI components
lib/env.ts      # Centralized public environment configuration
lib/api/        # Centralized backend API client (single fetch entry point)
lib/supabase/   # Supabase browser / server / middleware clients
public/         # Static assets
```

## Conventions

- All backend HTTP calls go through `lib/api/client.ts` — never scatter
  `fetch` calls through the app.
- All `NEXT_PUBLIC_*` reads go through `lib/env.ts`.
- Secrets (`SUPABASE_SERVICE_ROLE_KEY`, `LANGFUSE_SECRET_KEY`,
  `QDRANT_API_KEY`, `OPENAI_API_KEY`) must never appear in frontend
  code or with a `NEXT_PUBLIC_` prefix.

## Authentication

Supabase Auth handles sign-in with email + password **and Google OAuth**
(Sign in with Google on `/login` and `/signup`). The OAuth callback is
`/auth/callback` (PKCE code exchange). Google must be enabled as a
provider in the Supabase project dashboard; add
`http://localhost:3000/auth/callback` (plus your deployed origin) to the
provider's authorized redirect URLs.

## Docker

See `../infrastructure/docker/README.md` and the root
`docker-compose.yml`.
