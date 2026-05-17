#!/usr/bin/env pwsh
# Example 04 setup — arXiv cs.AI + cs.LG → skill extraction → ntfy + JSONL + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model = 'qwen2.5:7b'
$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')

function Log { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Green }
function Die { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Red; exit 1 }

Log 'Checking prerequisites…'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Die 'curl is required.' }
Ok 'Prerequisites OK.'

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example…'
    Copy-Item .env.example .env
}

$topicMatch = Select-String -Path .env -Pattern '^NTFY_TOPIC=' | Select-Object -First 1
$topic = if ($topicMatch) { ($topicMatch.Line -split '=', 2)[1].Trim() } else { '' }
if ([string]::IsNullOrWhiteSpace($topic) -or $topic -eq 'glean-arxiv-CHANGE-ME') {
    Die "Set a private ntfy topic in .env before starting.`n# In .env, set: NTFY_TOPIC=glean-arxiv-`$(openssl rand -hex 6)"
}
if ($topic -notmatch '^[A-Za-z0-9_-]{1,64}$') {
    Die "NTFY_TOPIC must be 1-64 characters using only letters, digits, '_' or '-'."
}

New-Item -ItemType Directory -Force -Path 'data\digests', 'data\ollama' | Out-Null

Log 'Starting ollama…'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d ollama
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for ollama.' }

Log 'Waiting for ollama to be healthy (≤2 min)…'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex04-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die 'ollama did not become healthy. Check: docker compose -f docker-compose.yml logs ollama' }

$listed = (& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama list 2>$null) -split "`n"
$hasModel = $listed | Where-Object { $_ -match '^qwen2\.5:7b\s' -or $_ -eq $Model }
if ($hasModel) {
    Ok "Model $Model already present."
} else {
    Log "Pulling $Model (~5 GB — first time only)…"
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
    Ok "Model $Model pulled."
}

Log 'Starting glean…'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (≤60 s)…'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:9094/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $payload = $response.Content | ConvertFrom-Json
        if ($response.StatusCode -eq 200 -and $payload.status -eq 'ok') {
            $healthy = $true
            Ok 'glean is healthy.'
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { Die 'glean did not become healthy. Check: docker compose -f docker-compose.yml logs glean' }

Log "Dry-running the 'arxiv-papers' feed…"
& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T glean glean test-feed arxiv-papers
if ($LASTEXITCODE -ne 0) { Die "Dry-run failed for 'arxiv-papers'." }

Write-Host @"

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 04 is up.

 Browser viewer URL:
   http://127.0.0.1:9094/
   # Get the API key from: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 JSONL archive:
   $ScriptDir\data\digests\arxiv-papers.jsonl

 Subscribe on your phone:
   https://ntfy.sh/$topic
   # Or install the ntfy mobile app and subscribe to topic: $topic

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@