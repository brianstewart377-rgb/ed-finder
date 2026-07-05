param(
  [switch]$EnsureServices,
  [int]$ApiPort = 8001,
  [bool]$OpenBrowser = $true
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$apiScript = Join-Path $repoRoot 'scripts\dev\start_local_api.ps1'
$frontendDir = Join-Path $repoRoot 'frontend-v2'
$apiHealthUrl = "http://127.0.0.1:$ApiPort/api/health"
$frontendUrl = 'http://localhost:3000/'

if (-not (Test-Path -LiteralPath $apiScript)) {
  throw "API script not found at $apiScript"
}

if (-not (Test-Path -LiteralPath $frontendDir)) {
  throw "Frontend directory not found at $frontendDir"
}

function Test-ApiHealth {
  param([string]$Url)

  try {
    $health = Invoke-RestMethod -Uri $Url -ErrorAction Stop
    return $health.status -eq 'ok'
  } catch {
    return $false
  }
}

function Test-FrontendReady {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -ErrorAction Stop
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

if (-not (Test-ApiHealth -Url $apiHealthUrl)) {
  $apiArgs = @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $apiScript,
    '-Port',
    "$ApiPort"
  )

  if ($EnsureServices) {
    $apiArgs += '-EnsureServices'
  }

  Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList $apiArgs

  $healthy = $false
  1..120 | ForEach-Object {
    if (Test-ApiHealth -Url $apiHealthUrl) {
      $healthy = $true
      return
    }
    Start-Sleep -Milliseconds 500
  }

  if (-not $healthy) {
    throw "Health check failed at $apiHealthUrl"
  }
}

if ($OpenBrowser) {
  if (Test-FrontendReady -Url $frontendUrl) {
    Start-Process $frontendUrl
  } else {
    $browserCommand = @"
$ErrorActionPreference = 'SilentlyContinue'
1..120 | ForEach-Object {
  try {
    \$response = Invoke-WebRequest -Uri '$frontendUrl' -UseBasicParsing -ErrorAction Stop
    if (\$response.StatusCode -eq 200) {
      Start-Process '$frontendUrl'
      exit 0
    }
  } catch {}
  Start-Sleep -Milliseconds 500
}
"@
    Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList '-NoProfile', '-Command', $browserCommand
  }
}

Set-Location $frontendDir
if (-not $env:VITE_CACHE_DIR -and $env:LOCALAPPDATA) {
  $env:VITE_CACHE_DIR = Join-Path $env:LOCALAPPDATA 'ED-Finder\vite-cache'
}
npm run start
