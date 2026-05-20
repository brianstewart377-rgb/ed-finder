param(
  [string]$RepoPath = 'C:\Users\brian\Documents\Codex\2026-05-20\files-mentioned-by-the-user-edfinder',
  [string]$DeployHost = $(if ($env:EDFINDER_DEPLOY_HOST) { $env:EDFINDER_DEPLOY_HOST } else { 'ed-finder.app' }),
  [string]$DeployUser = $env:EDFINDER_DEPLOY_USER,
  [int]$DeployPort = $(if ($env:EDFINDER_DEPLOY_PORT) { [int]$env:EDFINDER_DEPLOY_PORT } else { 22 }),
  [string]$PublicUrl = 'https://ed-finder.app',
  [string]$PlannerRoute = '#colony-planner/system/1453586352459',
  [string]$RemoteRepoPath = '/opt/ed-finder',
  [ValidateSet('abort', 'stash', 'reset')]
  [string]$RemoteDirtyPolicy = 'stash',
  [switch]$SkipPrompt,
  [switch]$SkipPull,
  [switch]$SkipTypecheck,
  [switch]$SkipBuild,
  [switch]$SkipTests,
  [switch]$SkipPush,
  [switch]$SkipDeploy,
  [switch]$OpenApp,
  [string]$SshOptions = '-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4'
)

$ErrorActionPreference = 'Stop'

function Test-TcpOpen {
  param(
    [Parameter(Mandatory = $true)][string]$HostName,
    [Parameter(Mandatory = $true)][int]$Port,
    [int]$TimeoutMs = 3000
  )
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($HostName, $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    $connected = $ok -and $client.Connected
    $client.Close()
    return $connected
  } catch {
    return $false
  }
}

if (-not $DeployUser) {
  $DeployUser = 'root'
}

if (-not (Test-Path -LiteralPath $RepoPath)) {
  throw "Repo path not found: $RepoPath"
}

if (-not $SkipPrompt) {
  $target = if ($SkipDeploy) { '(deploy skipped)' } else { "$DeployUser@$DeployHost`:$DeployPort" }
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
Write-Host "[release] Repo: $RepoPath"
Write-Host "[release] Branch: $branch"

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
  Write-Host '[release] Pulling latest main...'
  git pull --ff-only origin main
}

Set-Location (Join-Path $RepoPath 'frontend-v2')

if (-not $SkipTypecheck) {
  Write-Host '[release] Running typecheck...'
  npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw 'typecheck failed' }
}

if (-not $SkipBuild) {
  Write-Host '[release] Running build...'
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'build failed' }
}

if (-not $SkipTests) {
  Write-Host '[release] Running tests...'
  npm test
  if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
}

Set-Location $RepoPath

$head = (git rev-parse --short HEAD).Trim()

if (-not $SkipPush) {
  Write-Host "[release] Pushing main ($head)..."
  git push origin main
  if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
}

if (-not $SkipDeploy) {
  if (-not $DeployHost) {
    throw 'Deploy host missing. Set EDFINDER_DEPLOY_HOST or pass -DeployHost.'
  }
  if (-not (Test-TcpOpen -HostName $DeployHost -Port $DeployPort -TimeoutMs 3000)) {
    if ($DeployHost -eq 'ed-finder.app' -and $DeployPort -eq 22) {
      throw @"
SSH to ed-finder.app:22 is not reachable.
This domain is Cloudflare-proxied, so SSH usually must target the Hetzner origin host/IP.

Run again with the origin host, for example:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release-main-to-prod.ps1 -DeployHost <hetzner-ip-or-hostname> -DeployPort 22 -OpenApp

Or set defaults once:
setx EDFINDER_DEPLOY_HOST <hetzner-ip-or-hostname>
setx EDFINDER_DEPLOY_PORT 22
"@
    }
    throw "SSH is not reachable on $DeployHost`:$DeployPort. Check host/port/firewall."
  }

  $remote = "$DeployUser@$DeployHost"
  $remoteCmdParts = @(
    'set -euo pipefail',
    "cd ""$RemoteRepoPath""",
    'if ! git diff --quiet || ! git diff --cached --quiet; then',
    "echo ""[remote] Detected tracked local edits in $RemoteRepoPath""",
    'git status --short'
  )
  if ($RemoteDirtyPolicy -eq 'stash') {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stashMessage = "release-auto-stash-$stamp"
    $remoteCmdParts += "git stash push -u -m ""$stashMessage"" >/dev/null"
    $remoteCmdParts += "echo ""[remote] Stashed local edits ($stashMessage) and continuing deploy."""
    $remoteCmdParts += 'git stash list --max-count=1'
  } elseif ($RemoteDirtyPolicy -eq 'reset') {
    $remoteCmdParts += 'echo "[remote] Resetting tracked local edits to HEAD and continuing deploy."'
    $remoteCmdParts += 'git reset --hard HEAD >/dev/null'
  } else {
    $remoteCmdParts += 'echo "[remote] Refusing deploy because tracked local edits exist. Commit/stash/clean server repo first."'
    $remoteCmdParts += 'exit 25'
  }
  $remoteCmdParts += 'fi'
  $remoteCmdParts += 'bash scripts/deploy_main.sh'
  $remoteScript = ($remoteCmdParts -join "`n") + "`n"
  $remoteScriptLf = $remoteScript -replace "`r`n", "`n"
  if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw 'ssh is not available in PATH.'
  }
  Write-Host "[release] Starting remote deploy on $remote`:$DeployPort ..."
  Write-Host "[release] Remote dirty policy: $RemoteDirtyPolicy"
  Write-Host '[release] If prompted, complete SSH authentication in this terminal.'
  $sshArgs = @()
  if ($SshOptions.Trim()) {
    $sshArgs += $SshOptions.Trim().Split(' ')
  }
  $sshArgs += '-p'
  $sshArgs += "$DeployPort"
  $sshArgs += $remote
  $sshArgs += 'bash -s --'
  $remoteScriptLf | & ssh @sshArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed on $remote"
  }
  Write-Host '[release] Remote deploy finished.'
}

$healthUrl = "$PublicUrl/api/health"
Write-Host "[release] Probing public health: $healthUrl"
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
Write-Host "[release] Public planner probe OK: $plannerUrl ($($plannerProbe.StatusCode))"

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
