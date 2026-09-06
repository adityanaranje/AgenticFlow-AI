# Redis (development)

Redis is the only data service run locally in the Phase 1 development
stack — it backs caching (LLM / retrieval / web-search) and will back
queue-backed workers in later phases.

## Usage

The Docker Compose stack at the repository root mounts
`infrastructure/redis/redis.conf` into the `redis` container and uses a
named volume (`redis-data`) for persistence:

```bash
docker compose up redis
```

Connect from the backend container via `REDIS_URL=redis://redis:6379/0`,
or from the host via `redis://localhost:6379/0`.

For a bare-metal backend run, use a local Redis server and export:

```bash
export REDIS_URL=redis://localhost:6379/0
```
