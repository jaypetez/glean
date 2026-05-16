#!/usr/bin/env pwsh
# Example 01 setup — fully self-contained glean stack:
#   glean + ollama (qwen2.5:7b) + searxng → file + dashboard sinks.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model   = 'qwen2.5:7b'
$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')

function Log { param($msg) Write-Host "[ex01] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex01] $msg" -ForegroundColor Green }
function Die { param($msg) Write-Host "[ex01] $msg" -ForegroundColor Red; exit 1 }

# -- 1. Prerequisites ---------------------------------------------------------

Log 'Checking prerequisites…'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
Ok 'Prerequisites OK.'

# -- 2. .env ------------------------------------------------------------------

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example…'
    Copy-Item .env.example .env
}

$envContent = Get-Content .env -Raw
if ($envContent -notmatch '(?m)^SEARXNG_SECRET=[0-9a-fA-F]{32,}') {
    Log 'Generating SEARXNG_SECRET (32 bytes)…'
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $patched = ($envContent -split "`n") | ForEach-Object {
        if ($_ -match '^SEARXNG_SECRET=') { "SEARXNG_SECRET=$secret" } else { $_ }
    }
    Set-Content -Path .env -Value ($patched -join "`n") -NoNewline
    Ok 'SEARXNG_SECRET set.'
} else {
    Ok 'SEARXNG_SECRET already present.'
}

# -- 3. data/ directory -------------------------------------------------------

New-Item -ItemType Directory -Force -Path 'data\digests', 'data\ollama' | Out-Null

# -- 4. Bring up ollama + searxng first, wait for healthy ---------------------

Log 'Starting ollama + searxng…'
& $Compose[0] $Compose[1..($Compose.Count-1)] up -d ollama searxng
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for ollama/searxng.' }

Log 'Waiting for ollama to be healthy (≤2 min)…'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex01-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die "ollama did not become healthy. Check: $($Compose -join ' ') logs ollama" }

# -- 5. Pull the LLM model ----------------------------------------------------

$listed = (& $Compose[0] $Compose[1..($Compose.Count-1)] exec -T ollama ollama list 2>$null) -split "`n"
$hasModel = $listed | Where-Object { $_ -match "^${Model}\s" }
if ($hasModel) {
    Ok "Model $Model already present."
} else {
    Log "Pulling $Model (~5 GB — first time only)…"
    & $Compose[0] $Compose[1..($Compose.Count-1)] exec -T ollama ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
    Ok "Model $Model pulled."
}

# -- 6. Start glean -----------------------------------------------------------

Log 'Starting glean…'
& $Compose[0] $Compose[1..($Compose.Count-1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (≤60 s)…'
for ($i = 0; $i -lt 12; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9091/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { Ok 'glean is healthy.'; break }
    } catch { }
    Start-Sleep -Seconds 5
}

# -- 7. Dry-run the feed so the user sees output immediately ------------------

Log "Dry-running the 'web-search' feed (no items will be sent — first tick is bootstrap)…"
& $Compose[0] $Compose[1..($Compose.Count-1)] exec -T glean glean test-feed web-search

Write-Host @"

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 01 is up.

 Force one digest right now (writes to .\data\digests\web-search.md):
   docker compose -f docker-compose.yml exec glean glean send-now web-search

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Browse digests in the browser:
   Start-Process http://127.0.0.1:9091/
   # Get the API key from: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 The feed will tick every hour on its own from now on.

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@
