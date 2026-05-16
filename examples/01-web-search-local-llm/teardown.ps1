#!/usr/bin/env pwsh
# Tear down example 01: containers, volumes, local data\, and .env.
# The example directory itself is preserved so you can re-run setup.ps1.

#Requires -Version 7
$ErrorActionPreference = 'Continue'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

Write-Host '[ex01] Stopping containers + removing volumes…' -ForegroundColor Cyan
& docker compose -f docker-compose.yml down -v --remove-orphans

Write-Host '[ex01] Removing local data\ and .env…' -ForegroundColor Cyan
if (Test-Path data) { Remove-Item -Recurse -Force data }
if (Test-Path .env) { Remove-Item -Force .env }

Write-Host '[ex01] Done. Re-run .\setup.ps1 to start fresh.' -ForegroundColor Green
