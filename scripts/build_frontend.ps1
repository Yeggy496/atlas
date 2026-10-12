<#
.SYNOPSIS
    Rebuild the committed frontend bundle (frontend/dist) and stage it.

.DESCRIPTION
    The live ATLAS-Sigma demo is served from frontend/dist, which is committed to
    git. Run this after any change under frontend/src (or the frontend build
    config) so the deployed bundle never goes stale. It installs from the locked
    dependency set, runs the production build, and stages the result.

    Pair it with the tracked pre-commit guard in .githooks (enable once per clone):
        git config core.hooksPath .githooks
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    throw "pnpm was not found on PATH. Install pnpm (or add it to PATH) and re-run this script."
}

Push-Location $frontend
try {
    Write-Host "Installing locked frontend dependencies..." -ForegroundColor Cyan
    & $pnpm.Source install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "pnpm install failed with exit code $LASTEXITCODE." }

    Write-Host "Building the production frontend bundle..." -ForegroundColor Cyan
    & $pnpm.Source build
    if ($LASTEXITCODE -ne 0) { throw "pnpm build failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

git -C $repoRoot add frontend/dist
Write-Host "frontend/dist rebuilt and staged. Review 'git status' and commit." -ForegroundColor Green