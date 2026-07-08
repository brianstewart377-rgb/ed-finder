param(
  [string]$DeployTarget = $env:EDFINDER_DEPLOY_TARGET,
  [string]$DeployHost = $(if ($env:EDFINDER_DEPLOY_HOST) { $env:EDFINDER_DEPLOY_HOST } else { '' }),
  [string]$DeployUser = $(if ($env:EDFINDER_DEPLOY_USER) { $env:EDFINDER_DEPLOY_USER } else { 'root' }),
  [int]$DeployPort = $(if ($env:EDFINDER_DEPLOY_PORT) { [int]$env:EDFINDER_DEPLOY_PORT } else { 22 }),
  [string]$RemoteRepoPath = '/opt/ed-finder',
  [string]$PublicUrl = 'https://ed-finder.app',
  [switch]$SkipPrompt,
  [switch]$SkipPull,
  [switch]$SkipMigrations,
  [switch]$SkipFrontend,
  [switch]$OpenApp,
  [string]$SshOptions = '-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4'
)

$ErrorActionPreference = 'Stop'

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
      UsesAlias = $true
    }
  }

  if (-not $DeployHost) {
    throw 'Missing SSH target. Set EDFINDER_DEPLOY_TARGET to an SSH alias like ed-finder-prod, or pass -DeployHost.'
  }

  return @{
    Display = "$DeployUser@$DeployHost`:$DeployPort"
    SshArgs = @('-p', "$DeployPort", "$DeployUser@$DeployHost")
    UsesAlias = $false
  }
}

function Invoke-HttpProbe {
  param(
    [Parameter(Mandatory = $true)][string]$Uri
  )

  $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 20
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
    throw "HTTP probe failed: $Uri ($($response.StatusCode))"
  }
  return $response
}

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
  throw 'ssh is not available in PATH.'
}

$resolvedTarget = Resolve-SshTarget -DeployTarget $DeployTarget -DeployHost $DeployHost -DeployUser $DeployUser -DeployPort $DeployPort

if (-not $SkipPrompt) {
  $answer = Read-Host "Run remote deploy on $($resolvedTarget.Display) ? (y/N)"
  if ($answer -notin @('y', 'Y')) {
    throw 'Cancelled by user.'
  }
}

$remoteCmdParts = @(
  'set -euo pipefail',
  "cd ""$RemoteRepoPath"""
)

$deployArgs = @()
if ($SkipPull) { $deployArgs += '--skip-pull' }
if ($SkipMigrations) { $deployArgs += '--skip-migrations' }
if ($SkipFrontend) { $deployArgs += '--skip-frontend' }

$deployCommand = 'bash scripts/deploy_main.sh'
if ($deployArgs.Count -gt 0) {
  $deployCommand += ' ' + ($deployArgs -join ' ')
}
$remoteCmdParts += $deployCommand

$remoteScript = ($remoteCmdParts -join "`n") + "`n"
$remoteScriptLf = $remoteScript -replace "`r`n", "`n"

$sshArgs = @()
if ($SshOptions.Trim()) {
  $sshArgs += $SshOptions.Trim().Split(' ')
}
$sshArgs += $resolvedTarget.SshArgs
$sshArgs += 'bash -s --'

Write-Host "[deploy] Starting remote deploy on $($resolvedTarget.Display) ..."
Write-Host '[deploy] If prompted, complete SSH authentication in this terminal.'
$remoteScriptLf | & ssh @sshArgs
if ($LASTEXITCODE -ne 0) {
  throw "Remote deploy failed on $($resolvedTarget.Display)"
}

$baseUrl = $PublicUrl.TrimEnd('/')
$health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 20
if ($health.status -ne 'ok') {
  throw "Public health check did not return status=ok from $baseUrl/api/health"
}

$rootProbe = Invoke-HttpProbe -Uri "$baseUrl/"
$indexProbe = Invoke-HttpProbe -Uri "$baseUrl/index.html?deploy_check=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$legacyProbe = Invoke-HttpProbe -Uri "$baseUrl/v2/"

if ($OpenApp) {
  Start-Process "$baseUrl/"
}

[PSCustomObject]@{
  deployTarget = $resolvedTarget.Display
  remoteRepoPath = $RemoteRepoPath
  publicHealth = $health
  rootStatus = $rootProbe.StatusCode
  indexStatus = $indexProbe.StatusCode
  legacyRedirectFinalUrl = $legacyProbe.BaseResponse.ResponseUri.AbsoluteUri
} | ConvertTo-Json -Depth 6
