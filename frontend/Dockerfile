# ============================================================
# AgentFlow AI - frontend image (Next.js standalone)
#
# Build context: repository root (required because next.config.ts
# reads build-time args). See infrastructure/docker/README.md.
#
# The Next.js image inlines NEXT_PUBLIC_* values at build time,
# so real (public) Supabase credentials must be supplied as build
# args - compose reads them from the root .env file. A build with
# empty values would "succeed" and ship a bundle whose sign-in
# throws "Missing NEXT_PUBLIC_SUPABASE_URL" in the browser, so the
# guard below fails loudly instead. Set REQUIRE_SUPABASE_ENV=0 to
# skip it (e.g. a CI image build with no credentials).
# ============================================================

FROM node:22-alpine AS deps
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app

ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG REQUIRE_SUPABASE_ENV=1

ENV NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL} \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=${NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY} \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1

# Fail fast on an unbuilt-configuration image (see header comment).
RUN if [ "$REQUIRE_SUPABASE_ENV" = "1" ]; then \
      if [ -z "$NEXT_PUBLIC_SUPABASE_URL" ]; then \
        echo "BUILD ERROR: NEXT_PUBLIC_SUPABASE_URL is empty." ; \
        echo "  Pass it as a build arg: --build-arg NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co" ; \
        echo "  (docker compose reads it from the repository root .env)" ; exit 1 ; \
      fi ; \
      if [ -z "$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY$NEXT_PUBLIC_SUPABASE_ANON_KEY" ]; then \
        echo "BUILD ERROR: no browser-safe Supabase key baked in." ; \
        echo "  Pass --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_..." ; \
        echo "  (legacy projects: NEXT_PUBLIC_SUPABASE_ANON_KEY). Never a secret / service_role key." ; exit 1 ; \
      fi ; \
    fi

COPY frontend/package.json frontend/package-lock.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./

# Standalone output requires `output: "standalone"` in next.config.ts.
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
