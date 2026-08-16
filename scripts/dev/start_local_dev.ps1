param(
  [switch]$EnsureServices,
  [int]$ApiPort = 8001,
  [int]$FrontendPort = 3000,
  [bool]$OpenBrowser = $true
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$apiScript = Join-Path $repoRoot 'scripts\dev\start_local_api.ps1'
$frontendDir = Join-Path $repoRoot 'frontend'
$apiHealthUrl = "http://127.0.0.1:$ApiPort/api/health"
$frontendUrl = "http://localhost:$FrontendPort/"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting ED-Finder Local Dev Environment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $apiScript)) {
  Write-Host "✗ API script not found" -ForegroundColor Red
  Write-Host "  Expected: $apiScript" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path -LiteralPath $frontendDir)) {
  Write-Host "✗ Frontend directory not found" -ForegroundColor Red
  Write-Host "  Expected: $frontendDir" -ForegroundColor Red
  exit 1
}

function Test-PortInUse {
  param([int]$Port)
  $result = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
  return $result -ne $null
}

function Get-PortOwner {
  param([int]$Port)
  try {
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connection) {
      $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
      return $process.Name
    }
  } catch {}
  return "unknown"
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

# Port availability check
Write-Host "Checking port availability..." -ForegroundColor Gray

if (Test-PortInUse -Port $ApiPort) {
  $owner = Get-PortOwner -Port $ApiPort
  Write-Host "⚠ Port $ApiPort already in use (owned by: $owner)" -ForegroundColor Yellow
  Write-Host "  Trying to use existing API on that port..." -ForegroundColor Gray
}

if (Test-PortInUse -Port $FrontendPort) {
  $owner = Get-PortOwner -Port $FrontendPort
  Write-Host "⚠ Port $FrontendPort already in use (owned by: $owner)" -ForegroundColor Yellow
  Write-Host "  Trying to use existing frontend on that port..." -ForegroundColor Gray
}

Write-Host ""

if (-not (Test-ApiHealth -Url $apiHealthUrl)) {
  Write-Host "Starting API server (port $ApiPort)..." -ForegroundColor Cyan
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
  $attempts = 0
  1..120 | ForEach-Object {
    $attempts = $_
    if (Test-ApiHealth -Url $apiHealthUrl) {
      $healthy = $true
      Write-Host "✓ API healthy after $attempts attempts" -ForegroundColor Green
      return
    }
    if ($attempts % 10 -eq 0) {
      Write-Host "  Waiting for API... ($attempts/120)" -ForegroundColor Gray
    }
    Start-Sleep -Milliseconds 500
  }

  if (-not $healthy) {
    Write-Host "✗ API health check failed after 60 seconds" -ForegroundColor Red
    Write-Host "  Check: $apiHealthUrl" -ForegroundColor Red
    Write-Host "  Run: make test-env-check" -ForegroundColor Yellow
    exit 1
  }
} else {
  Write-Host "✓ API already running" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting frontend dev server (port $FrontendPort)..." -ForegroundColor Cyan
Write-Host "Open browser: $frontendUrl" -ForegroundColor Gray

if ($OpenBrowser) {
  if (Test-FrontendReady -Url $frontendUrl) {
    Write-Host "✓ Frontend already running, opening browser..." -ForegroundColor Green
    Start-Process $frontendUrl
  } else {
    Write-Host "  Launching after frontend ready..." -ForegroundColor Gray
    $browserCommand = @"
`$ErrorActionPreference = 'SilentlyContinue'
1..120 | ForEach-Object {
  try {
    `$response = Invoke-WebRequest -Uri '$frontendUrl' -UseBasicParsing -ErrorAction Stop
    if (`$response.StatusCode -eq 200) {
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

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Development environment ready!" -ForegroundColor Green
Write-Host "API:      http://127.0.0.1:$ApiPort" -ForegroundColor Cyan
Write-Host "Frontend: $frontendUrl" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $frontendDir
if (-not $env:VITE_CACHE_DIR -and $env:LOCALAPPDATA) {
  $env:VITE_CACHE_DIR = Join-Path $env:LOCALAPPDATA 'ED-Finder\vite-cache'
}
$env:VITE_DEV_API_TARGET = "http://127.0.0.1:$ApiPort"
npm run start
