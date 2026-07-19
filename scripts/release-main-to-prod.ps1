param(
  [string]$RepoPath = '',
  [string]$DeployTarget = $env:EDFINDER_DEPLOY_TARGET,
  [string]$DeployHost = $(if ($env:EDFINDER_DEPLOY_HOST) { $env:EDFINDER_DEPLOY_HOST } else { '' }),
  [string]$DeployUser = $env:EDFINDER_DEPLOY_USER,
  [int]$DeployPort = $(if ($env:EDFINDER_DEPLOY_PORT) { [int]$env:EDFINDER_DEPLOY_PORT } else { 22 }),
  [string]$PublicUrl = 'https://ed-finder.app',
  [string]$AppProbePath = '/',
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
  [switch]$SkipFrontendArtifact,
  [switch]$OpenApp,
  [string]$SshOptions = '-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4'
)

$ErrorActionPreference = 'Stop'

if (-not $RepoPath) {
  $RepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

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

function Resolve-SshTarget {
  param(
    [string]$DeployTarget,
    [string]$DeployHost,
    [string]$DeployUser,
    [int]$DeployPort
  )

  if ($DeployTarget) {
    return @{
      Display = $DeployTarget
      SshArgs = @($DeployTarget)
      ScpOptions = @()
      Destination = $DeployTarget
      CanProbeTcp = $false
    }
  }

  if (-not $DeployHost) {
    throw 'Deploy host missing. Set EDFINDER_DEPLOY_TARGET to an SSH alias like ed-finder-prod, or pass -DeployHost.'
  }

  return @{
    Display = "$DeployUser@$DeployHost`:$DeployPort"
    SshArgs = @('-p', "$DeployPort", "$DeployUser@$DeployHost")
    ScpOptions = @('-P', "$DeployPort")
    Destination = "$DeployUser@$DeployHost"
    CanProbeTcp = $true
  }
}

if (-not $DeployUser) {
  $DeployUser = 'root'
}

if (-not (Test-Path -LiteralPath $RepoPath)) {
  throw "Repo path not found: $RepoPath"
}

if (-not $SkipPrompt) {
  $previewTarget = if ($DeployTarget) {
    $DeployTarget
  } elseif ($DeployHost) {
    "$DeployUser@$DeployHost`:$DeployPort"
  } else {
    '(deploy target not set)'
  }
  $target = if ($SkipDeploy) { '(deploy skipped)' } else { $previewTarget }
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

Set-Location (Join-Path $RepoPath 'frontend')

Write-Host '[release] Ensuring frontend dependencies are installed...'
yarn install --frozen-lockfile
if ($LASTEXITCODE -ne 0) { throw 'yarn install failed' }

if (-not $SkipTypecheck) {
  Write-Host '[release] Running typecheck...'
  yarn typecheck
  if ($LASTEXITCODE -ne 0) { throw 'typecheck failed' }
}

if (-not $SkipBuild) {
  Write-Host '[release] Running build...'
  yarn build
  if ($LASTEXITCODE -ne 0) { throw 'build failed' }
}

if (-not $SkipTests) {
  Write-Host '[release] Running tests...'
  yarn test:ci
  if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
}

Set-Location $RepoPath

$head = (git rev-parse --short HEAD).Trim()
$frontendArchiveLocal = Join-Path $RepoPath "artifacts\frontend-bundles\frontend-dist-$head.tar.gz"
$runBash = Join-Path $RepoPath 'scripts\dev\run-bash.ps1'

if (-not $SkipFrontendArtifact) {
  if (-not (Test-Path -LiteralPath $runBash)) {
    throw "Git Bash wrapper not found: $runBash"
  }
  Write-Host "[release] Packaging frontend artifact: $frontendArchiveLocal"
  & $runBash `
    -Script 'scripts/package_frontend_bundle.sh' `
    -ScriptArgs @('--output', $frontendArchiveLocal)
  if ($LASTEXITCODE -ne 0) { throw 'frontend artifact packaging failed' }
}

if (-not $SkipPush) {
  Write-Host "[release] Pushing main ($head)..."
  git push origin main
  if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
}

if (-not $SkipDeploy) {
  $resolvedTarget = Resolve-SshTarget -DeployTarget $DeployTarget -DeployHost $DeployHost -DeployUser $DeployUser -DeployPort $DeployPort
  if ($resolvedTarget.CanProbeTcp -and -not (Test-TcpOpen -HostName $DeployHost -Port $DeployPort -TimeoutMs 3000)) {
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

  $remoteFrontendArchive = "/tmp/frontend-dist-$head.tar.gz"
  if (-not $SkipFrontendArtifact) {
    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
      throw 'scp is not available in PATH.'
    }
    Write-Host "[release] Uploading frontend artifact to $($resolvedTarget.Display): $remoteFrontendArchive"
    $scpArgs = @()
    if ($SshOptions.Trim()) {
      $scpArgs += $SshOptions.Trim().Split(' ')
    }
    $scpArgs += $resolvedTarget.ScpOptions
    $scpArgs += $frontendArchiveLocal
    $scpArgs += "$($resolvedTarget.Destination)`:$remoteFrontendArchive"
    & scp @scpArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to upload frontend artifact to $($resolvedTarget.Display)"
    }
  }

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
  if ($SkipFrontendArtifact) {
    $remoteCmdParts += 'bash scripts/deploy_main.sh'
  } else {
    $remoteCmdParts += "bash scripts/deploy_main.sh --frontend-archive ""$remoteFrontendArchive"""
    $remoteCmdParts += "rm -f ""$remoteFrontendArchive"""
  }
  $remoteScript = ($remoteCmdParts -join "`n") + "`n"
  $remoteScriptLf = $remoteScript -replace "`r`n", "`n"
  if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw 'ssh is not available in PATH.'
  }
  Write-Host "[release] Starting remote deploy on $($resolvedTarget.Display) ..."
  Write-Host "[release] Remote dirty policy: $RemoteDirtyPolicy"
  Write-Host '[release] If prompted, complete SSH authentication in this terminal.'
  $sshArgs = @()
  if ($SshOptions.Trim()) {
    $sshArgs += $SshOptions.Trim().Split(' ')
  }
  $sshArgs += $resolvedTarget.SshArgs
  $sshArgs += 'bash -s --'
  $remoteScriptLf | & ssh @sshArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed on $($resolvedTarget.Display)"
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
$probePath = if ($AppProbePath.StartsWith('/')) { $AppProbePath } else { "/$AppProbePath" }
$appUrl = "$baseUrl$probePath"
$appProbe = Invoke-WebRequest -Uri $appUrl -UseBasicParsing -TimeoutSec 20
if ($appProbe.StatusCode -lt 200 -or $appProbe.StatusCode -ge 400) {
  throw "App probe failed: $appUrl ($($appProbe.StatusCode))"
}
Write-Host "[release] Public app probe OK: $appUrl ($($appProbe.StatusCode))"

$releaseCheckStamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$appShell = Invoke-WebRequest -Uri "$baseUrl/index.html?release_check=$releaseCheckStamp" -UseBasicParsing -TimeoutSec 20
$scriptMatch = [regex]::Match($appShell.Content, '<script[^>]+src="([^"]+)"')
if (-not $scriptMatch.Success) {
  throw 'App shell validation failed: could not find a module script src in /index.html.'
}
$scriptSrc = $scriptMatch.Groups[1].Value
$scriptUrl = if ($scriptSrc.StartsWith('http')) { $scriptSrc } else { "$baseUrl$scriptSrc" }
$scriptProbe = Invoke-WebRequest -Uri $scriptUrl -UseBasicParsing -TimeoutSec 20
$scriptContentType = [string]$scriptProbe.Headers['Content-Type']
$scriptLooksLikeHtml = $scriptProbe.Content -match '^\s*<!doctype html'
if ($scriptLooksLikeHtml -or ($scriptContentType -notmatch 'javascript')) {
  throw "App shell validation failed: script URL resolved to non-JS payload ($scriptUrl, content-type=$scriptContentType)."
}
if ($appShell.Content -match '/assets/') {
  Write-Host '[release] App shell asset base OK (/assets/* detected).'
} else {
  Write-Warning 'App shell does not clearly advertise /assets/*; continuing because script probe succeeded.'
}

if ($OpenApp) {
  Start-Process $appUrl
}

[PSCustomObject]@{
  repo = $RepoPath
  commit = $head
  branch = $branch
  deployHost = if ($SkipDeploy) { '(skipped)' } else { if ($DeployTarget) { $DeployTarget } else { "$DeployUser@$DeployHost" } }
  publicHealth = $health
  appUrl = $appUrl
  appHttpStatus = $appProbe.StatusCode
} | ConvertTo-Json -Depth 6
