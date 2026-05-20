#!/usr/bin/env pwsh
# Example 04 setup - arXiv cs.AI + cs.LG -> skill extraction -> ntfy + JSONL + dashboard.
#
# Idempotent. Safe to re-run.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

$Model = 'qwen2.5:7b'
$EmbeddingModel = 'nomic-embed-text'

function Log { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Cyan }
function Ok  { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Green }
function Die { param($msg) Write-Host "[ex04] $msg" -ForegroundColor Red; exit 1 }

function Test-OllamaTagsEndpoint {
    param([string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Get-GpuMode {
    if (-not [string]::IsNullOrWhiteSpace($env:GLEAN_OLLAMA_GPU)) {
        switch ($env:GLEAN_OLLAMA_GPU) {
            'none' { return 'none' }
            'nvidia' { return 'nvidia' }
            'rocm' { return 'rocm' }
            'external' { return 'external' }
            default { Die "Invalid GLEAN_OLLAMA_GPU=$($env:GLEAN_OLLAMA_GPU)" }
        }
    }

    if ((Test-OllamaTagsEndpoint 'http://host.docker.internal:11434/api/tags') -or (Test-OllamaTagsEndpoint 'http://127.0.0.1:11434/api/tags')) {
        return 'external'
    }

    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & nvidia-smi *> $null
        if ($LASTEXITCODE -eq 0) {
            return 'nvidia'
        }
    }

    if ((Get-Command rocm-smi -ErrorAction SilentlyContinue) -and (Test-Path '/dev/kfd')) {
        return 'rocm'
    }

    return 'none'
}

function Update-FeedsYamlForExternalOllama {
    if (Select-String -Path feeds.yaml -Pattern 'base_url: http://host.docker.internal:11434' -SimpleMatch -Quiet) {
        return
    }

    Log 'Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)'
    Copy-Item feeds.yaml feeds.yaml.bak -Force
    $content = Get-Content feeds.yaml -Raw
    $patched = $content.Replace('base_url: http://ollama:11434', 'base_url: http://host.docker.internal:11434')
    Set-Content -Path feeds.yaml -Value $patched
}

function Restore-FeedsYamlFromBackup {
    if (Test-Path feeds.yaml.bak) {
        Log 'Restoring feeds.yaml from feeds.yaml.bak'
        Move-Item -Force feeds.yaml.bak feeds.yaml
    }
}

Log 'Checking prerequisites...'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die 'docker is required.' }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Die 'docker compose v2 is required (try: docker compose version).' }
Ok 'Prerequisites OK.'

if (-not (Test-Path .env)) {
    Log 'Creating .env from .env.example...'
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

$gpuModeMatch = Select-String -Path .env -Pattern '^GLEAN_OLLAMA_GPU=' | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($env:GLEAN_OLLAMA_GPU) -and $gpuModeMatch) {
    $env:GLEAN_OLLAMA_GPU = ($gpuModeMatch.Line -split '=', 2)[1].Trim().Trim('"').Trim("'")
}

$Mode = Get-GpuMode
Log "GPU mode: $Mode (override via GLEAN_OLLAMA_GPU in .env)"
$ComposeArgs = @('-f', 'docker-compose.yml')
switch ($Mode) {
    'nvidia' {
        Restore-FeedsYamlFromBackup
        $ComposeArgs += @('-f', 'docker-compose.nvidia.yml')
    }
    'rocm' {
        Restore-FeedsYamlFromBackup
        $ComposeArgs += @('-f', 'docker-compose.rocm.yml')
    }
    'external' {
        $ComposeArgs += @('-f', 'docker-compose.external-ollama.yml')
        Update-FeedsYamlForExternalOllama
    }
    'none' {
        Restore-FeedsYamlFromBackup
    }
}

New-Item -ItemType Directory -Force -Path 'data\digests', 'data\ollama' | Out-Null

Log 'Starting ollama...'
& docker compose @ComposeArgs up -d ollama
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for ollama.' }

Log 'Waiting for ollama to be healthy (<=2 min)...'
$state = ''
for ($i = 0; $i -lt 24; $i++) {
    $state = (& docker inspect -f '{{.State.Health.Status}}' glean-ex04-ollama 2>$null)
    if ($state -eq 'healthy') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'healthy') { Die 'ollama did not become healthy. Check the compose logs for ollama.' }

switch ($Mode) {
    'nvidia' {
        Log 'Verifying NVIDIA GPU access inside ollama...'
        & docker compose @ComposeArgs exec -T ollama nvidia-smi *> $null
        if ($LASTEXITCODE -ne 0) { Die 'NVIDIA GPU not visible inside the ollama container.' }
        Ok 'NVIDIA GPU detected inside ollama.'
    }
    'rocm' {
        Log 'Verifying ROCm GPU access inside ollama...'
        & docker compose @ComposeArgs exec -T ollama rocm-smi *> $null
        if ($LASTEXITCODE -ne 0) { Die 'ROCm GPU not visible inside the ollama container.' }
        Ok 'ROCm GPU detected inside ollama.'
    }
}

if ($Mode -eq 'external') {
    Ok 'Using external Ollama; skipping model pull.'
    Log "If missing, pull on your host: ollama pull $Model && ollama pull $EmbeddingModel"
} else {
    $listed = (& docker compose @ComposeArgs exec -T ollama ollama list 2>$null) -split "`n"
    $hasModel = $listed | Where-Object { $_ -match '^qwen2\.5:7b\s' -or $_ -eq $Model }
    if ($hasModel) {
        Ok "Model $Model already present."
    } else {
        Log 'Pulling qwen2.5:7b (~5 GB - first time only)...'
        & docker compose @ComposeArgs exec -T ollama ollama pull $Model
        if ($LASTEXITCODE -ne 0) { Die "Failed to pull $Model." }
        Ok "Model $Model pulled."
    }

    $hasEmbeddingModel = $listed | Where-Object {
        $_ -match "^$([regex]::Escape($EmbeddingModel))(\s|$)"
    }
    if ($hasEmbeddingModel) {
        Ok "Model $EmbeddingModel already present."
    } else {
        Log "Pulling $EmbeddingModel (~270 MB - first time only)..."
        & docker compose @ComposeArgs exec -T ollama ollama pull $EmbeddingModel
        if ($LASTEXITCODE -ne 0) { Die "Failed to pull $EmbeddingModel." }
        Ok "Model $EmbeddingModel pulled."
    }
}

Log 'Starting glean...'
& docker compose @ComposeArgs up -d glean
if ($LASTEXITCODE -ne 0) { Die 'compose up failed for glean.' }

Log 'Waiting for glean healthz (<=60 s)...'
$healthy = $false
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:9094/healthz' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
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
if (-not $healthy) { Die 'glean did not become healthy. Check the compose logs for glean.' }

Log "Dry-running the 'arxiv-papers' feed..."
& docker compose @ComposeArgs exec -T glean glean test-feed arxiv-papers
if ($LASTEXITCODE -ne 0) { Die "Dry-run failed for 'arxiv-papers'." }

Write-Host @"

[ex04] Example 04 is up.

GPU mode:
  $Mode

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
"@
