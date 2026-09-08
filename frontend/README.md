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
cp .env.example .env.local     # .env works too; only this folder is read

#    -> NEXT_PUBLIC_SUPABASE_URL
#    -> NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, or the legacy
#       NEXT_PUBLIC_SUPABASE_ANON_KEY (Supabase dashboard -> Project
#       Settings -> API Keys; the *publishable* key is the browser-safe one)
#    -> NEXT_PUBLIC_API_URL (defaults to http://localhost:8000)

# 2. Install, check the values, and run
npm install
npm run doctor         # what Next.js will actually load, explained
npm run dev            # http://localhost:3000
```

> `NEXT_PUBLIC_*` values are inlined into the browser bundle when the dev
> server starts, so every edit needs a restart (Turbopack prints
> `Reload env: .env.local` when it picks the change up) or a rebuild for
> `npm run build && npm run start`.

## Sign-in does nothing / “Missing NEXT_PUBLIC_SUPABASE_URL”

That is a build-configuration problem, not an account problem. The login and
sign-up pages render a checklist naming the exact variable and mistake, and the
dev server prints the same box in the terminal. `npm run doctor` covers the
whole family of causes:

| Finding                                                        | Fix |
| -------------------------------------------------------------- | --- |
| No `.env*` file in `frontend/`                                  | `npm run doctor -- --copy`, fill in the values, restart |
| Values live in the **repository root** `.env`                   | Only docker-compose reads it; move them to `frontend/.env.local` |
| Variable declared but empty in `.env.local`                     | A blank line beats a good value in `.env` — delete the blank line |
| Value set in your shell (e.g. `""`)                             | `unset VAR` / `Remove-Item Env:VAR`, then restart from a fresh terminal |
| `.env.local` written by PowerShell `>` (UTF-16)                 | Save as “UTF-8 without BOM”; Next.js reads nothing from UTF-16 |
| Quotes, placeholder text, trailing `/`, missing `https://`      | Write `NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co` |
| `sb_secret_...` or a `service_role` JWT in a `NEXT_PUBLIC_*` var | Replace with the publishable key and rotate the secret — it bypasses RLS |
| Key’s `iss` points at another project ref                       | Take URL and key from the same project |
| Reachability: Supabase answers `400/401`, or the host has no DNS record | Live check runs by default (`--offline` to skip); it also catches paused projects |

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
- All `NEXT_PUBLIC_*` reads go through `lib/env.ts` (validation lives in
  `lib/supabase-env.ts`, shared with the auth pages and `npm run doctor`).
- Secrets (`SUPABASE_SERVICE_ROLE_KEY`, `LANGFUSE_SECRET_KEY`,
  `QDRANT_API_KEY`, `OPENAI_API_KEY`) must never appear in frontend
  code or with a `NEXT_PUBLIC_` prefix.

## Authentication

Supabase Auth handles sign-in with email + password **and Google OAuth**
(Sign in with Google on `/login` and `/signup`). `GoogleButton` calls
`signInWithOAuth` with `redirectTo = <origin>/auth/callback`; the app's
`/auth/callback` route then does the PKCE code exchange, so the session
lands in cookies written by `@supabase/ssr`.

Two redirect lists, and they are not interchangeable:

- **Google Cloud → Clients → Authorized redirect URIs** takes *Supabase's*
  callback — `https://<project-ref>.supabase.co/auth/callback` (the value is
  printed on the Supabase Google provider page). Google never sees this app.
- **Supabase → Authentication → URL Configuration → Redirect URLs** takes
  *this app's* `redirectTo` — `http://localhost:3000/auth/callback` or
  `http://localhost:3000/**` in development, plus the deployed origin.
  *Authorized JavaScript origins* in Google Cloud gets the bare origins.

Swap those two and Google answers “Access blocked: This app's request is
invalid (`redirect_uri_mismatch`)”. To check the live wiring, run
`npm run doctor` — it asks GoTrue `/auth/v1/authorize?provider=google` and
prints the `redirect_uri` your project actually sends, or reports that the
provider is disabled. In development the same values are pre-filled on the
login and sign-up pages under “Google sign-in setup — exact URLs to paste”.

## Docker

See `../infrastructure/docker/README.md` and the root
`docker-compose.yml`.
