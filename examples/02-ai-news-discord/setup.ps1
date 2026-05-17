#!/usr/bin/env pwsh
# Example 02 setup — AI news via RSS + Ollama + Discord + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model = 'qwen2.5:7b'
$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')

function Log { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Green }
function Die { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Red; exit 1 }

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
if ($envContent -notmatch '(?m)^DISCORD_WEBHOOK_URL=') {
    $envContent = $envContent.TrimEnd("`r", "`n") + "`nDISCORD_WEBHOOK_URL=`n"
    Set-Content -Path .env -Value $envContent -NoNewline
}

$envContent = Get-Content .env -Raw
$webhookUrl = ([regex]::Match($envContent, '(?m)^DISCORD_WEBHOOK_URL=(.*)$')).Groups[1].Value.Trim()
if ([string]::IsNullOrWhiteSpace($webhookUrl)) {
    Die 'Set DISCORD_WEBHOOK_URL in .env (Server Settings > Integrations > Webhooks > New Webhook).'
}
if (-not ($webhookUrl.StartsWith('https://discord.com/api/webhooks/') -or $webhookUrl.StartsWith('https://discordapp.com/api/webhooks/'))) {
    Die 'DISCORD_WEBHOOK_URL must start with https://discord.com/api/webhooks/ or https://discordapp.com/api/webhooks/.'
}
Ok 'Discord webhook looks valid.'

# -- 3. data/ directory -------------------------------------------------------

New-Item -ItemType Directory -Force -Path 'data\ollama' | Out-Null

# -- 4. Bring up ollama first, wait for healthy -------------------------------

Log 'Starting ollama…'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d ollama
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for ollama.' }

Log 'Waiting for ollama to be healthy (≤2 min)…'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex02-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die "ollama did not become healthy. Check: $($Compose -join ' ') logs ollama" }

# -- 5. Pull the LLM model ----------------------------------------------------

$listed = (& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama list 2>$null) -split "`n"
$hasModel = $listed | Where-Object { $_ -match "^${Model}\s" }
if ($hasModel) {
    Ok "Model $Model already present."
} else {
    Log "Pulling $Model (~5 GB — first time only)…"
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
    Ok "Model $Model pulled."
}

# -- 6. Start glean -----------------------------------------------------------

Log 'Starting glean…'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (≤60 s)…'
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:9092/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($response.StatusCode -eq 200) { Ok 'glean is healthy.'; break }
    } catch {
    }
    Start-Sleep -Seconds 5
}
try {
    $final = Invoke-WebRequest -Uri 'http://127.0.0.1:9092/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($final.StatusCode -ne 200) { Die 'glean did not become healthy.' }
} catch {
    Die "glean did not become healthy. Check: $($Compose -join ' ') logs glean"
}

# -- 7. Dry-run the feed ------------------------------------------------------

Log "Dry-running the 'ai-news' feed…"
& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T glean glean test-feed ai-news

Write-Host @"

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 02 is up.

 Browse recent digests in the browser:
   Start-Process http://127.0.0.1:9092/

 Get the API key from logs:
   docker compose -f docker-compose.yml logs glean | Select-String GLEAN_INITIAL_API_KEY

 Force-send a digest right now:
   docker compose -f docker-compose.yml exec glean glean send-now ai-news

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@
