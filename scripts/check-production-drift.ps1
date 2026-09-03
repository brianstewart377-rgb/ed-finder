param(
  [string]$RepoPath = '',
  [string]$PublicUrl = 'https://ed-finder.app'
)

$ErrorActionPreference = 'Stop'

if (-not $RepoPath) {
  $RepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

Push-Location $RepoPath
try {
  git fetch --prune origin
  if ($LASTEXITCODE -ne 0) {
    throw 'Could not fetch origin.'
  }

  $mainSha = (git rev-parse origin/main).Trim()
  $healthUrl = "$($PublicUrl.TrimEnd('/'))/api/health"
  $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 20
  $liveSha = [string]$health.build_sha

  if ($liveSha -notmatch '^[0-9a-f]{40}$') {
    Write-Host @"
DEPLOY DRIFT UNKNOWN: $healthUrl did not report a full build_sha.
Live value: '$liveSha'
Use the current V3 production runbook/operator path to verify the deployed build before taking action.
"@ -ForegroundColor Red
    exit 2
  }

  if ($liveSha -eq $mainSha) {
    Write-Host "DEPLOY CURRENT: production matches origin/main at $mainSha" -ForegroundColor Green
    exit 0
  }

  git merge-base --is-ancestor $liveSha origin/main
  if ($LASTEXITCODE -eq 0) {
    $behind = (git rev-list --count "$liveSha..origin/main").Trim()
    Write-Host @"
DEPLOY DRIFT: production is $behind commit(s) behind origin/main.
Production:  $liveSha
origin/main: $mainSha
Do not use a retired V2/Hetzner release wrapper. Follow the current V3 production runbook/operator path for any approved promotion.
"@ -ForegroundColor Red
    exit 1
  }

  Write-Host @"
DEPLOY DIVERGENCE: production is not an ancestor of origin/main.
Production:  $liveSha
origin/main: $mainSha
Inspect the current V3 deployment state through the authorized production operator path before taking action.
"@ -ForegroundColor Red
  exit 3
}
finally {
  Pop-Location
}
