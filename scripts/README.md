# Development scripts

Small convenience scripts for local development (Phase 1).

| Script                        | Purpose                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `scripts/bootstrap.sh`        | Create the backend venv and install Python dependencies.   |
| `scripts/dev-backend.sh`      | Run the FastAPI backend with hot reload on port 8000.      |
| `scripts/dev-frontend.sh`     | Install frontend deps and run Next.js dev server on 3000.  |
| `scripts/check-health.sh`     | Poll backend and frontend health endpoints.               |

All scripts assume they are executed from the repository root:

```bash
./scripts/bootstrap.sh
./scripts/dev-backend.sh      # terminal 1
./scripts/dev-frontend.sh     # terminal 2
./scripts/check-health.sh
```
