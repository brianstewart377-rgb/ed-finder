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
Deploy the build-SHA instrumentation once, then rerun this check.
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
If the owner has approved promotion, run scripts/release-main-to-prod.ps1.
"@ -ForegroundColor Red
    exit 1
  }

  Write-Host @"
DEPLOY DIVERGENCE: production is not an ancestor of origin/main.
Production:  $liveSha
origin/main: $mainSha
Inspect the production checkout before deploying.
"@ -ForegroundColor Red
  exit 3
}
finally {
  Pop-Location
}
