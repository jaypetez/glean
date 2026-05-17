#!/usr/bin/env pwsh
# Example 03 setup — GitHub releases -> Slack + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')

function Log { param($msg) Write-Host "[ex03] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex03] $msg" -ForegroundColor Green }
function Die { param($msg) Write-Host "[ex03] $msg" -ForegroundColor Red; exit 1 }

# -- 1. Prerequisites ---------------------------------------------------------

Log 'Checking prerequisites…'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Die 'curl is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
Ok 'Prerequisites OK.'

# -- 2. .env ------------------------------------------------------------------

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example…'
    Copy-Item .env.example .env
}

$envContent = Get-Content .env -Raw
$match = [regex]::Match($envContent, '(?m)^SLACK_WEBHOOK_URL=(.*)$')
$slackWebhookUrl = if ($match.Success) { $match.Groups[1].Value.Trim().Trim('"', "'") } else { '' }
if (-not $slackWebhookUrl) {
    Die 'SLACK_WEBHOOK_URL is blank in .env. Add your Slack webhook URL, then re-run setup.ps1.'
}

if (-not $slackWebhookUrl.StartsWith('https://hooks.slack.com/services/')) {
    Die 'SLACK_WEBHOOK_URL must start with https://hooks.slack.com/services/'
}

Ok 'Slack webhook URL looks valid.'

# -- 3. data/ directory -------------------------------------------------------

New-Item -ItemType Directory -Force -Path 'data' | Out-Null

# -- 4. Start glean -----------------------------------------------------------

Log 'Starting glean (no Ollama container needed for this example)…'
& $Compose[0] $Compose[1..($Compose.Count-1)] up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (≤60 s)…'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    & curl.exe -fsS 'http://127.0.0.1:9093/healthz' *>$null
    if ($LASTEXITCODE -eq 0) {
        $healthy = $true
        Ok 'glean is healthy.'
        break
    }
    Start-Sleep -Seconds 5
}

if (-not $healthy) {
    Die "glean did not become healthy. Check: $($Compose -join ' ') logs glean"
}

# -- 5. Dry-run the feed ------------------------------------------------------

Log "Dry-running the 'github-releases' feed…"
& $Compose[0] $Compose[1..($Compose.Count-1)] exec -T glean glean test-feed github-releases
if ($LASTEXITCODE -ne 0) {
    Log 'Dry-run hit a transient fetch error. The stack is still up; re-run setup.ps1 or try again later.'
}

Write-Host @"

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 03 is up.

 Browse recent digests in the dashboard:
   Start-Process http://127.0.0.1:9093/
   # Get the API key from: docker compose -f docker-compose.yml logs glean | Select-String GLEAN_INITIAL_API_KEY

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Customize the repo list:
   edit feeds.yaml to add/remove GitHub repos ending in /releases.atom

 Note: bootstrap is skip-and-mark, so the dashboard stays empty until one of
 the tracked repos publishes a new release after setup.

 The feed will check for new releases every 6 hours and post them to Slack.

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@
