#!/usr/bin/env pwsh
# Example 02 setup — AI news via RSS + Ollama + Discord + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model = 'qwen2.5:7b'

function Log { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Yellow }
function Die { param($msg) Write-Host "[ex02] $msg" -ForegroundColor Red; exit 1 }

function Get-EnvValue {
    param([string]$Name)

    $content = Get-Content .env -Raw
    $match = [regex]::Match($content, "(?m)^$([regex]::Escape($Name))=(.*)$")
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ''
}

function Test-OllamaEndpoint {
    param([string]$Uri)

    try {
        $null = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Detect-GpuMode {
    if (-not [string]::IsNullOrWhiteSpace($script:GpuOverride)) {
        switch ($script:GpuOverride) {
            'none' { return 'none' }
            'nvidia' { return 'nvidia' }
            'rocm' { return 'rocm' }
            'external' { return 'external' }
            default { Die "Invalid GLEAN_OLLAMA_GPU=$($script:GpuOverride) (must be none|nvidia|rocm|external)" }
        }
    }
    if ((Test-OllamaEndpoint 'http://host.docker.internal:11434/api/tags') -or (Test-OllamaEndpoint 'http://127.0.0.1:11434/api/tags')) {
        return 'external'
    }
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & nvidia-smi *>$null
        if ($LASTEXITCODE -eq 0) {
            return 'nvidia'
        }
    }
    if ((Get-Command rocm-smi -ErrorAction SilentlyContinue) -and (Test-Path '/dev/kfd')) {
        return 'rocm'
    }
    return 'none'
}

function Patch-FeedsYamlForExternalOllama {
    if (Select-String -Path feeds.yaml -Pattern 'base_url: http://host\.docker\.internal:11434' -Quiet) {
        if (-not (Test-Path 'feeds.yaml.bak')) {
            Warn 'feeds.yaml already points to host.docker.internal and no feeds.yaml.bak exists; teardown will leave it as-is.'
        }
        return
    }
    Log 'Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)'
    if (-not (Test-Path 'feeds.yaml.bak')) {
        Copy-Item feeds.yaml feeds.yaml.bak
    }
    $content = Get-Content feeds.yaml -Raw
    $content = $content -replace 'base_url: http://ollama:11434', 'base_url: http://host.docker.internal:11434'
    Set-Content -Path feeds.yaml -Value $content -NoNewline
}

function Restore-FeedsYamlIfNeeded {
    if (Test-Path 'feeds.yaml.bak') {
        Log 'Restoring feeds.yaml: ollama base_url -> ollama container'
        Move-Item -Force feeds.yaml.bak feeds.yaml
    }
}

function Test-ExternalOllamaFromGlean {
    $probe = @"
import json
import sys
import urllib.request
model = sys.argv[1]
with urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5) as response:
    payload = json.load(response)
models = {entry.get('name') for entry in payload.get('models', [])}
sys.exit(0 if model in models else 1)
"@
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T glean python -c $probe $Model *>$null
    if ($LASTEXITCODE -eq 0) {
        Ok "glean container can reach host Ollama and found $Model"
    } else {
        Warn "glean container could NOT confirm host Ollama at host.docker.internal:11434 with model $Model. Ensure host Ollama is reachable from Docker and run: ollama pull $Model"
    }
}

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

$script:GpuOverride = if (-not [string]::IsNullOrWhiteSpace($env:GLEAN_OLLAMA_GPU)) {
    $env:GLEAN_OLLAMA_GPU.Trim()
} else {
    Get-EnvValue 'GLEAN_OLLAMA_GPU'
}
$webhookUrl = Get-EnvValue 'DISCORD_WEBHOOK_URL'
$Mode = Detect-GpuMode
if ($Mode -ne 'external') {
    Restore-FeedsYamlIfNeeded
}
Log "GPU mode: $Mode (override with GLEAN_OLLAMA_GPU=none|nvidia|rocm|external in .env)"
$ComposeFiles = @('docker-compose.yml')
switch ($Mode) {
    'nvidia' { $ComposeFiles += 'docker-compose.nvidia.yml' }
    'rocm' { $ComposeFiles += 'docker-compose.rocm.yml' }
    'external' {
        $ComposeFiles += 'docker-compose.external-ollama.yml'
        Patch-FeedsYamlForExternalOllama
    }
}
$Compose = @('docker', 'compose')
foreach ($composeFile in $ComposeFiles) {
    $Compose += @('-f', $composeFile)
}
$ComposeText = $Compose -join ' '

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
if ($state -ne 'healthy') { Die "ollama did not become healthy. Check: $ComposeText logs ollama" }

if ($Mode -eq 'nvidia') {
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama nvidia-smi *>$null
    if ($LASTEXITCODE -eq 0) {
        Ok 'ollama container can see the GPU'
    } else {
        Warn 'ollama container could NOT see the GPU. Install nvidia-container-toolkit + restart Docker, or set GLEAN_OLLAMA_GPU=none.'
    }
} elseif ($Mode -eq 'rocm') {
    & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama rocm-smi *>$null
    if ($LASTEXITCODE -eq 0) {
        Ok 'ollama container can see the AMD GPU'
    } else {
        Warn 'ollama container could NOT see the AMD GPU. See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon.'
    }
}

# -- 5. Pull the LLM model ----------------------------------------------------

if ($Mode -eq 'external') {
    Log "External Ollama mode - skipping model pull (host Ollama expected to have $Model)"
    Log "If missing, pull on your host: ollama pull $Model"
} else {
    $listed = (& $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama list 2>$null) -split "`n"
    $hasModel = $listed | Where-Object { $_ -match "^$([regex]::Escape($Model))(\s|$)" }
    if ($hasModel) {
        Ok "Model $Model already present."
    } else {
        Log "Pulling $Model (~5 GB — first time only)…"
        & $Compose[0] $Compose[1..($Compose.Count - 1)] exec -T ollama ollama pull $Model
        if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
        Ok "Model $Model pulled."
    }
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
    Die "glean did not become healthy. Check: $ComposeText logs glean"
}

if ($Mode -eq 'external') {
    Test-ExternalOllamaFromGlean
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
   $ComposeText logs glean | Select-String GLEAN_INITIAL_API_KEY

 Force-send a digest right now:
   $ComposeText exec glean glean send-now ai-news

 Tear it all down:
   .\teardown.ps1
──────────────────────────────────────────────────────────────────────────────
"@
