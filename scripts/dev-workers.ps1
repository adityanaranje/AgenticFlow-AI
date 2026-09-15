# ============================================================
# AgentFlow AI - run the background workers in development (Windows).
#
# Uploads land in `pending` and research runs in `queued` until a worker
# consumes the Redis queue, so the API server alone is not enough:
#
#   document-worker  -> parse + chunk + embed + upsert uploaded documents
#   research-worker  -> run the multi-step research pipeline
#
# Usage:  .\scripts\dev-workers.ps1
#         .\scripts\dev-workers.ps1 -NoWindow   # logs in this console instead
# Stop:   Ctrl+C for -NoWindow; otherwise close the two worker windows
#
# Requires: backend dependencies installed (scripts\bootstrap.sh) and a
# backend\.env with REDIS_URL pointing at a reachable Redis.
# ============================================================
[CmdletBinding()]
param(
    [switch]$NoWindow
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root "backend"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Backend dependencies missing ($python not found). Run scripts\bootstrap.sh first."
}

$workers = @("app.workers.document_worker", "app.workers.research_worker")

Write-Host "Starting document worker and research worker..."

if ($NoWindow) {
    $procs = @()
    try {
        foreach ($worker in $workers) {
            $procs += Start-Process -FilePath $python -ArgumentList "-m", $worker `
                -WorkingDirectory $backend -NoNewWindow -PassThru
        }
        # Block until either worker exits, then stop the survivor.
        while ($true) {
            foreach ($p in $procs) {
                if ($p.HasExited) { throw "Worker $($p.Id) exited with code $($p.ExitCode)." }
            }
            Start-Sleep -Seconds 1
        }
    }
    finally {
        foreach ($p in $procs) {
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        }
    }
}
else {
    foreach ($worker in $workers) {
        Start-Process -FilePath $python -ArgumentList "-m", $worker -WorkingDirectory $backend
    }
    Write-Host "Workers started in separate windows. Close those windows to stop them."
}
