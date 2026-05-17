#!/usr/bin/env pwsh
# Example 05 setup — Reddit -> cloud LLM -> Telegram + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')

function Log { param($Message) Write-Host "[ex05] $Message" -ForegroundColor Cyan }
function Ok  { param($Message) Write-Host "[ex05] $Message" -ForegroundColor Green }
function Die { param($Message) Write-Host "[ex05] $Message" -ForegroundColor Red; exit 1 }

Log 'Checking prerequisites…'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
if (-not (Get-Command curl -ErrorAction SilentlyContinue) -and -not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    Die 'curl is required.'
}
Ok 'Prerequisites OK.'

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example…'
    Copy-Item .env.example .env
    Die 'Created .env from .env.example. Fill in your cloud LLM key and Telegram values, then re-run .\setup.ps1.'
}

$envMap = @{}
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*$' -or $line -match '^\s*#') { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $name = $matches[1]
        $value = $matches[2]
        if (
            (($value.StartsWith('"')) -and $value.EndsWith('"')) -or
            (($value.StartsWith("'")) -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $envMap[$name] = $value
        Set-Item -Path "Env:$name" -Value $value
    }
}

$providerMatch = Get-Content feeds.yaml | Select-String -Pattern '^\s*provider:\s*(\S+)' | Select-Object -First 1
$SelectedProvider = if ($providerMatch) { $providerMatch.Matches[0].Groups[1].Value } else { 'openai' }

if ([string]::IsNullOrWhiteSpace($envMap['OPENAI_API_KEY']) -and [string]::IsNullOrWhiteSpace($envMap['ANTHROPIC_API_KEY'])) {
    Die 'Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env before starting.'
}

if ($SelectedProvider -eq 'openai' -and [string]::IsNullOrWhiteSpace($envMap['OPENAI_API_KEY'])) {
    Die 'feeds.yaml is configured for provider=openai. Set OPENAI_API_KEY or switch feeds.yaml to the Anthropic block in README.md.'
}

if ($SelectedProvider -eq 'anthropic' -and [string]::IsNullOrWhiteSpace($envMap['ANTHROPIC_API_KEY'])) {
    Die 'feeds.yaml is configured for provider=anthropic. Set ANTHROPIC_API_KEY or switch feeds.yaml back to OpenAI.'
}

if ([string]::IsNullOrWhiteSpace($envMap['TELEGRAM_BOT_TOKEN'])) { Die 'TELEGRAM_BOT_TOKEN is required.' }
if ([string]::IsNullOrWhiteSpace($envMap['TELEGRAM_CHAT_ID'])) { Die 'TELEGRAM_CHAT_ID is required.' }
if ([string]::IsNullOrWhiteSpace($envMap['TELEGRAM_OPS_CHAT_ID'])) { Die 'TELEGRAM_OPS_CHAT_ID is required.' }

if ($envMap['TELEGRAM_BOT_TOKEN'] -notmatch '^[0-9]+:[A-Za-z0-9_-]+$') {
    Die 'TELEGRAM_BOT_TOKEN must match ^[0-9]+:[A-Za-z0-9_-]+$.'
}
if ($envMap['TELEGRAM_CHAT_ID'] -notmatch '^-?[0-9]+$') {
    Die 'TELEGRAM_CHAT_ID must be an integer (negative for groups).'
}
if ($envMap['TELEGRAM_OPS_CHAT_ID'] -notmatch '^-?[0-9]+$') {
    Die 'TELEGRAM_OPS_CHAT_ID must be an integer (negative for groups).'
}

New-Item -ItemType Directory -Force -Path 'data' | Out-Null

Log "Using cloud LLM provider: $SelectedProvider"
Log 'Starting glean…'
& $Compose[0] $Compose[1..($Compose.Count-1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (≤60 s)…'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:9095/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            Ok 'glean is healthy.'
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { Die "glean did not become healthy. Check: $($Compose -join ' ') logs glean" }

Log "Dry-running the 'reddit-ml' feed…"
& $Compose[0] $Compose[1..($Compose.Count-1)] exec -T glean glean test-feed reddit-ml
if ($LASTEXITCODE -ne 0) { Die "Dry-run failed for feed 'reddit-ml'." }

Write-Host @"

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 05 is up.

 Browser UI:
   http://127.0.0.1:9095/
   # API key: docker compose -f docker-compose.yml logs glean | Select-String GLEAN_INITIAL_API_KEY

 Telegram chat to watch:
   $($envMap['TELEGRAM_CHAT_ID'])

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Force one digest right now:
   docker compose -f docker-compose.yml exec glean glean send-now reddit-ml

 Cost note:
   This example uses a cloud LLM, so expect a small per-tick spend.
   No Ollama container, GPU, or 5 GB model pull is required.

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@
