# Development scripts

Small convenience scripts for local development (Phase 1).

| Script                        | Purpose                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `scripts/bootstrap.sh`        | Create the backend venv and install Python dependencies.   |
| `scripts/dev-backend.sh`      | Run the FastAPI backend with hot reload on port 8000.      |
| `scripts/dev-frontend.sh`     | Install frontend deps and run Next.js dev server on 3000.  |
| `scripts/check-health.sh`     | Poll backend and frontend health endpoints.               |
| `scripts/benchmark-ingestion.py` | Measure ingestion speed against simulated remote latencies. |
| `scripts/benchmark-research.py` | Measure research-run speed against simulated remote latencies. |

Frontend environment problems (missing / shadowed / wrong-file `NEXT_PUBLIC_*`
values) are diagnosed by `cd frontend && npm run doctor`, which reads the same
`.env*` files in the same precedence order Next.js does.

`scripts/benchmark-ingestion.py` runs the real ingestion pipeline (worker,
chunking, id linkage) against fakes that sleep for a configurable amount of
time per remote request, so batching changes can be measured without touching
OpenAI / Supabase / Qdrant:

```bash
python scripts/benchmark-ingestion.py --paragraphs 2000     # ~500 chunks
EMBEDDING_CONCURRENCY=8 python scripts/benchmark-ingestion.py
```

`scripts/benchmark-research.py` does the same for a research run: the real
pipeline (planner, retriever, evidence analyser, gap detector, synthesis,
finalizer, report storage) runs while only the provider calls are faked, so
the numbers show how many round trips the application makes and how much it
overlaps:

```bash
python scripts/benchmark-research.py                        # typical run
python scripts/benchmark-research.py --subquestions 8       # 9 open queries
python scripts/benchmark-research.py --chunks-per-query 150 # large corpus
```

All scripts assume they are executed from the repository root:

```bash
./scripts/bootstrap.sh
./scripts/dev-backend.sh      # terminal 1
./scripts/dev-frontend.sh     # terminal 2
./scripts/check-health.sh
```
