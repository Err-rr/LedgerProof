#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Boots the full local demo: the real FastAPI app (in-memory persistence --
    no Neon, S3, or Anthropic credentials needed) and the Next.js dashboard,
    each in its own window so you can watch both logs live while driving the
    browser at http://127.0.0.1:<WebPort>.

    Restarting either process forgets every run -- persistence is in-memory
    only, by design (see scripts/dev_api_server.py).
#>

param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RepoRoot "web"
$EnvLocal = Join-Path $WebDir ".env.local"
$EnvExample = Join-Path $WebDir ".env.example"

# Pinned explicitly rather than relying on bare `python` on PATH: a bare
# `python` picks up whatever environment happens to be first on PATH, which
# silently ran a DIFFERENT checkout's editable install during verification
# of this exact script (a global `python -c "import api"` resolved to a
# different clone entirely) -- a fresh clone with its own .venv must use
# ITS OWN interpreter, not whatever else is on the machine.
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "No venv found at $VenvPython -- run 'python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`"' first (see README.md Quickstart)."
    exit 1
}

if (-not (Test-Path $EnvLocal)) {
    Copy-Item $EnvExample $EnvLocal
    "LEDGERPROOF_API_BASE_URL=http://127.0.0.1:$ApiPort" | Out-File -FilePath $EnvLocal -Encoding utf8
    Write-Host "Created $EnvLocal pointing at http://127.0.0.1:$ApiPort"
} else {
    $existing = Get-Content $EnvLocal -Raw
    if ($existing -notmatch "LEDGERPROOF_API_BASE_URL=http://127\.0\.0\.1:$ApiPort") {
        Write-Warning "$EnvLocal does not point at http://127.0.0.1:$ApiPort -- update it or the web app will fail loudly at startup (see instrumentation.ts)."
    }
}

Write-Host "Starting API dev server on port $ApiPort ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$RepoRoot'; & '$VenvPython' scripts/dev_api_server.py --port $ApiPort"

Write-Host "Starting web dev server on port $WebPort ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$WebDir'; npm run dev -- --port $WebPort"

Write-Host ""
Write-Host "API:  http://127.0.0.1:$ApiPort/healthz"
Write-Host "Web:  http://127.0.0.1:$WebPort"
Write-Host ""
Write-Host "Two new windows just opened. Close them (or Ctrl+C in each) to stop."
