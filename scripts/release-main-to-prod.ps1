param(
  [string]$RepoPath = 'C:\Users\brian\Documents\Codex\2026-05-20\files-mentioned-by-the-user-edfinder',
  [string]$DeployHost = $(if ($env:EDFINDER_DEPLOY_HOST) { $env:EDFINDER_DEPLOY_HOST } else { 'ed-finder.app' }),
  [string]$DeployUser = $env:EDFINDER_DEPLOY_USER,
  [string]$PublicUrl = 'https://ed-finder.app',
  [string]$PlannerRoute = '#colony-planner/system/1453586352459',
  [switch]$SkipPrompt,
  [switch]$SkipPull,
  [switch]$SkipTypecheck,
  [switch]$SkipBuild,
  [switch]$SkipTests,
  [switch]$SkipPush,
  [switch]$SkipDeploy,
  [switch]$OpenApp
)

$ErrorActionPreference = 'Stop'

if (-not $DeployUser) {
  $DeployUser = 'root'
}

if (-not (Test-Path -LiteralPath $RepoPath)) {
  throw "Repo path not found: $RepoPath"
}

if (-not $SkipPrompt) {
  $target = if ($SkipDeploy) { '(deploy skipped)' } else { "$DeployUser@$DeployHost" }
  $answer = Read-Host "Release main, push, and deploy to $target ? (y/N)"
  if ($answer -notin @('y', 'Y')) {
    throw 'Cancelled by user.'
  }
}

Set-Location $RepoPath

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') {
  throw "Expected branch 'main' but found '$branch'"
}

# Ignore .codex-context noise, but fail on any tracked edits or other untracked files.
git diff --quiet
if ($LASTEXITCODE -ne 0) {
  throw 'Working tree has unstaged tracked edits. Commit/stash before release.'
}
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  throw 'Working tree has staged tracked edits. Commit before release.'
}
$untracked = git ls-files --others --exclude-standard | Where-Object { $_ -notlike '.codex-context*' }
if ($untracked) {
  throw "Untracked files present outside .codex-context.`n$($untracked -join "`n")"
}

if (-not $SkipPull) {
  git pull --ff-only origin main
}

Set-Location (Join-Path $RepoPath 'frontend-v2')

if (-not $SkipTypecheck) {
  npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw 'typecheck failed' }
}

if (-not $SkipBuild) {
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'build failed' }
}

if (-not $SkipTests) {
  npm test
  if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
}

Set-Location $RepoPath

$head = (git rev-parse --short HEAD).Trim()

if (-not $SkipPush) {
  git push origin main
  if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
}

if (-not $SkipDeploy) {
  if (-not $DeployHost) {
    throw 'Deploy host missing. Set EDFINDER_DEPLOY_HOST or pass -DeployHost.'
  }

  $remote = "$DeployUser@$DeployHost"
  $remoteCmd = 'cd /opt/ed-finder && bash scripts/deploy_main.sh'
  & ssh $remote $remoteCmd
  if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed on $remote"
  }
}

$healthUrl = "$PublicUrl/api/health"
$health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 20
if ($health.status -ne 'ok') {
  throw "Public health check did not return status=ok from $healthUrl"
}

$baseUrl = $PublicUrl.TrimEnd('/')
$plannerUrl = if ($PlannerRoute.StartsWith('#')) { "$baseUrl/$PlannerRoute" } else { "$baseUrl/$PlannerRoute" }
$plannerProbe = Invoke-WebRequest -Uri $plannerUrl -UseBasicParsing -TimeoutSec 20
if ($plannerProbe.StatusCode -lt 200 -or $plannerProbe.StatusCode -ge 400) {
  throw "Planner URL probe failed: $plannerUrl ($($plannerProbe.StatusCode))"
}

if ($OpenApp) {
  Start-Process $plannerUrl
}

[PSCustomObject]@{
  repo = $RepoPath
  commit = $head
  branch = $branch
  deployHost = if ($SkipDeploy) { '(skipped)' } else { "$DeployUser@$DeployHost" }
  publicHealth = $health
  plannerUrl = $plannerUrl
  plannerHttpStatus = $plannerProbe.StatusCode
} | ConvertTo-Json -Depth 6
