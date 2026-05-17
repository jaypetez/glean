#!/usr/bin/env pwsh
# Example 01 setup - fully self-contained glean stack:
#   glean + ollama (qwen2.5:7b) + searxng -> file + dashboard sinks.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model = 'qwen2.5:7b'
$ComposeArgs = @('compose', '-f', 'docker-compose.yml')

function Log { param([string]$msg) Write-Host "[ex01] $msg" -ForegroundColor Cyan }
function Ok  { param([string]$msg) Write-Host "[ex01] $msg" -ForegroundColor Green }
function Warn { param([string]$msg) Write-Host "[ex01] $msg" -ForegroundColor Yellow }
function Die { param([string]$msg) Write-Host "[ex01] $msg" -ForegroundColor Red; exit 1 }

function Load-GpuOverrideFromEnvFile {
    if (-not [string]::IsNullOrWhiteSpace($env:GLEAN_OLLAMA_GPU)) {
        return
    }
    if (-not (Test-Path .env)) {
        return
    }
    $line = Select-String -Path .env -Pattern '^GLEAN_OLLAMA_GPU=' | Select-Object -Last 1
    if ($line) {
        $env:GLEAN_OLLAMA_GPU = ($line.Line -replace '^GLEAN_OLLAMA_GPU=', '').Trim()
    }
}

function Test-ExternalOllamaEndpoint {
    foreach ($uri in @('http://host.docker.internal:11434/api/tags', 'http://127.0.0.1:11434/api/tags')) {
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.Content -match '"models"') {
                return $true
            }
        } catch {
        }
    }
    return $false
}

function Test-NvidiaContainerRuntime {
    $runtimes = & docker info --format '{{json .Runtimes}}' 2>$null
    return ($LASTEXITCODE -eq 0 -and $runtimes -match '"nvidia"')
}

function Detect-GpuMode {
    $override = $env:GLEAN_OLLAMA_GPU
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        switch ($override) {
            'none' { return 'none' }
            'nvidia' { return 'nvidia' }
            'rocm' { return 'rocm' }
            'external' { return 'external' }
            default { Die "Invalid GLEAN_OLLAMA_GPU=$override (must be none|nvidia|rocm|external)" }
        }
    }

    if (Test-ExternalOllamaEndpoint) {
        return 'external'
    }

    if ((Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        & nvidia-smi *>$null
        if ($LASTEXITCODE -eq 0 -and (Test-NvidiaContainerRuntime)) {
            return 'nvidia'
        }
    }

    if ((Get-Command rocm-smi -ErrorAction SilentlyContinue) -and (Test-Path '/dev/kfd')) {
        return 'rocm'
    }

    return 'none'
}

function Patch-FeedsYamlForExternalOllama {
    $content = Get-Content feeds.yaml -Raw
    if ($content -match 'base_url: http://host\.docker\.internal:11434') {
        return  # already patched
    }
    Log 'Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)'
    Copy-Item feeds.yaml feeds.yaml.bak -Force
    ($content -replace 'base_url: http://ollama:11434', 'base_url: http://host.docker.internal:11434') |
        Set-Content feeds.yaml -NoNewline
}

function Restore-FeedsYamlFromBackup {
    if (Test-Path feeds.yaml.bak) {
        Log 'Restoring feeds.yaml from .bak'
        Move-Item feeds.yaml.bak feeds.yaml -Force
    }
}

# -- 1. Prerequisites ---------------------------------------------------------

Log 'Checking prerequisites...'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *>$null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
Ok 'Prerequisites OK.'

# -- 2. .env ------------------------------------------------------------------

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example...'
    Copy-Item .env.example .env
}

$envContent = Get-Content .env -Raw
if ($envContent -notmatch '(?m)^SEARXNG_SECRET=[0-9a-fA-F]{32,}') {
    Log 'Generating SEARXNG_SECRET (32 bytes)...'
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

Load-GpuOverrideFromEnvFile
$Mode = Detect-GpuMode
Log "GPU mode: $Mode (override with GLEAN_OLLAMA_GPU=none|nvidia|rocm|external in .env)"
if ($Mode -ne 'external' -and (Test-Path feeds.yaml.bak)) {
    Restore-FeedsYamlFromBackup
}

switch ($Mode) {
    'nvidia' { $ComposeArgs += @('-f', 'docker-compose.nvidia.yml') }
    'rocm' { $ComposeArgs += @('-f', 'docker-compose.rocm.yml') }
    'external' {
        $ComposeArgs += @('-f', 'docker-compose.external-ollama.yml')
        Patch-FeedsYamlForExternalOllama
    }
}
$ComposeDisplay = 'docker ' + ($ComposeArgs -join ' ')

# -- 3. data/ directory -------------------------------------------------------

New-Item -ItemType Directory -Force -Path 'data\digests', 'data\ollama' | Out-Null

# -- 4. Bring up ollama + searxng first, wait for healthy ---------------------

Log 'Starting ollama + searxng...'
& docker @ComposeArgs up -d ollama searxng
if ($LASTEXITCODE -ne 0) {
    if ($Mode -eq 'nvidia') {
        Warn 'NVIDIA mode could not start the ollama container.'
        Warn 'Install nvidia-container-toolkit, then: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker'
        Warn 'Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode.'
    } elseif ($Mode -eq 'rocm') {
        Warn 'ROCm mode could not start the ollama container.'
        Warn 'See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon for ROCm setup.'
        Warn 'Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode.'
    }
    Die 'compose up failed for ollama/searxng.'
}

Log 'Waiting for ollama to be healthy (<=2 min)...'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex01-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die "ollama did not become healthy. Check: $ComposeDisplay logs ollama" }

if ($Mode -eq 'nvidia') {
    & docker @ComposeArgs exec -T ollama nvidia-smi *>$null
    if ($LASTEXITCODE -eq 0) {
        Ok 'ollama container can see the GPU'
    } else {
        Warn 'ollama container could NOT see the GPU.'
        Warn 'Install nvidia-container-toolkit, then: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker'
        Warn 'Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode.'
    }
} elseif ($Mode -eq 'rocm') {
    & docker @ComposeArgs exec -T ollama rocm-smi *>$null
    if ($LASTEXITCODE -eq 0) {
        Ok 'ollama container can see the AMD GPU'
    } else {
        Warn 'ollama container could NOT see the AMD GPU.'
        Warn 'See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon for ROCm setup.'
    }
}

# -- 5. Pull the LLM model ----------------------------------------------------

if ($Mode -eq 'external') {
    Log 'External Ollama mode - skipping model pull (host Ollama is expected to have qwen2.5:7b)'
    Log 'If missing, pull on your host: ollama pull qwen2.5:7b'
} else {
    $listed = (& docker @ComposeArgs exec -T ollama ollama list 2>$null) -split "`n"
    $hasModel = $listed | Where-Object { $_ -match "^$([regex]::Escape($Model))(\s|$)" }
    if ($hasModel) {
        Ok "Model $Model already present."
    } else {
        Log "Pulling $Model (~5 GB - first time only)..."
        & docker @ComposeArgs exec -T ollama ollama pull $Model
        if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
        Ok "Model $Model pulled."
    }
}

# -- 6. Start glean -----------------------------------------------------------

Log 'Starting glean...'
& docker @ComposeArgs up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (<=60 s)...'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9091/healthz' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Ok 'glean is healthy.'
            $healthy = $true
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 5
}
if (-not $healthy) {
    Warn "glean healthz did not respond within 60 s. Continuing so you can inspect logs with: $ComposeDisplay logs glean"
}

# -- 7. Dry-run the feed so the user sees output immediately ------------------

Log "Dry-running the 'web-search' feed (no items will be sent - first tick is bootstrap)..."
& docker @ComposeArgs exec -T glean glean test-feed web-search

Write-Host @"

------------------------------------------------------------------------------
 OK: Example 01 is up (Ollama mode: $Mode).

 Compose command for this run:
   $ComposeDisplay

 Force one digest right now (writes to .\data\digests\web-search.md):
   $ComposeDisplay exec glean glean send-now web-search

 Tail the logs:
   $ComposeDisplay logs -f glean

 Browse digests in the browser:
   Start-Process http://127.0.0.1:9091/
   # Get the API key from: $ComposeDisplay logs glean | Select-String GLEAN_INITIAL_API_KEY

 The feed will tick every hour on its own from now on.

 Tear it all down:
   .\teardown.ps1
------------------------------------------------------------------------------
"@