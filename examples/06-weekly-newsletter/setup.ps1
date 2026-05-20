#!/usr/bin/env pwsh
# Example 06 setup — Weekly AI news -> email via Mailpit.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')
$Model = 'qwen2.5:7b'

function Log { param([string]$Message) Write-Host "[ex06] $Message" -ForegroundColor Cyan }
function Ok  { param([string]$Message) Write-Host "[ex06] $Message" -ForegroundColor Green }
function Die { param([string]$Message) Write-Host "[ex06] $Message" -ForegroundColor Red; exit 1 }

Log 'Checking prerequisites...'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
if (-not (Get-Command curl -ErrorAction SilentlyContinue) -and -not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    Die 'curl is required.'
}
Ok 'Prerequisites OK.'

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example...'
    Copy-Item .env.example .env
}

New-Item -ItemType Directory -Force -Path 'data\ollama' | Out-Null

Log 'Starting ollama + mailpit...'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d ollama mailpit
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for ollama/mailpit.' }

Log 'Waiting for ollama to be healthy (<=2 min)...'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex06-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die "ollama did not become healthy. Check: $($Compose -join ' ') logs ollama" }

$listed = (& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama list 2>$null) -split "`n"
$hasModel = $listed | Where-Object { $_ -match "^$([regex]::Escape($Model))(\s|$)" }
if ($hasModel) {
    Ok "Model $Model already present."
} else {
    Log "Pulling $Model (~5 GB - first time only)..."
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
    Ok "Model $Model pulled."
}

Log 'Starting glean...'
& $Compose[0] $Compose[1..($Compose.Count - 1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (<=60 s)...'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:9096/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            Ok 'glean is healthy.'
            break
        }
    } catch {
        # Expected while glean is still starting; the retry loop handles readiness.
    }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { Die "glean did not become healthy. Check: $($Compose -join ' ') logs glean" }

Log "Dry-running the 'weekly-digest' feed..."
& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T glean glean test-feed weekly-digest
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ex06] Dry-run failed. The stack is still up; inspect logs with: $($Compose -join ' ') logs glean" -ForegroundColor Yellow
}

Write-Host @"

✅ Example 06 is up.

View caught emails in Mailpit:
  Start-Process http://127.0.0.1:8025

Force send a digest now:
  docker compose -f docker-compose.yml exec glean glean send-now weekly-digest

Browse digests in the dashboard:
  Start-Process http://127.0.0.1:9096/

The feed ticks every Monday at 09:00 UTC.
"@
