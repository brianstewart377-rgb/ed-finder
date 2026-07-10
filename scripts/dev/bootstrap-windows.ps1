param(
  [switch]$StartServices,
  [switch]$InstallPlaywright,
  [switch]$RunDoctor,
  [switch]$ForceEnvFile
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envExample = Join-Path $repoRoot 'env.example'
$envFile = Join-Path $repoRoot '.env'
$venvDir = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$frontendDir = Join-Path $repoRoot 'frontend'
$composeLocal = Join-Path $repoRoot 'docker-compose.local.yml'
$doctorScript = Join-Path $repoRoot 'scripts\dev\doctor.ps1'

function Find-BasePython {
  try {
    $version = (& py -3.12 --version 2>&1 | Select-Object -First 1).ToString().Trim()
    return @{
      command = 'py'
      args = @('-3.12')
      version = $version
    }
  } catch {
  }

  try {
    $command = Get-Command python -ErrorAction Stop
    $version = (& $command.Path --version 2>&1 | Select-Object -First 1).ToString().Trim()
    if ($version -notmatch 'Python 3\.1[2-9]') {
      throw "Expected Python 3.12+, found $version"
    }
    return @{
      command = $command.Path
      args = @()
      version = $version
    }
  } catch {
  }

  throw 'Python 3.12+ was not found. Install Python 3.12 and ensure py.exe or python.exe is available.'
}

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory = $repoRoot
  )

  Write-Host ("-> {0} {1}" -f $FilePath, ($Arguments -join ' '))
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Get-FrontendInstallCommand {
  try {
    $yarn = Get-Command yarn -ErrorAction Stop
    return @{
      command = $yarn.Path
      args = @('install', '--frozen-lockfile')
    }
  } catch {
  }

  try {
    $corepack = Get-Command corepack -ErrorAction Stop
    return @{
      command = $corepack.Path
      args = @('yarn', 'install', '--frozen-lockfile')
    }
  } catch {
  }

  throw 'Neither yarn nor corepack was found. Install Node.js with Corepack support or install Yarn classic.'
}

if (-not (Test-Path -LiteralPath $envExample)) {
  throw "env.example not found at $envExample"
}

$python = Find-BasePython
Write-Host "Using base Python: $($python.version)"

if ($ForceEnvFile -or -not (Test-Path -LiteralPath $envFile)) {
  Copy-Item -LiteralPath $envExample -Destination $envFile -Force
  Write-Host "Prepared .env from env.example"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
  Invoke-Checked -FilePath $python.command -Arguments ($python.args + @('-m', 'venv', $venvDir))
}

if (-not (Test-Path -LiteralPath $venvPython)) {
  throw "Virtualenv creation failed: missing $venvPython"
}

Invoke-Checked -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip', 'wheel')
Invoke-Checked -FilePath $venvPython -Arguments @(
  '-m', 'pip', 'install',
  '-r', 'apps\api\requirements.txt',
  '-r', 'apps\eddn\requirements.txt',
  '-r', 'apps\importer\requirements.txt',
  '-r', 'tests\requirements-ci.txt'
)

$frontendInstall = Get-FrontendInstallCommand
Invoke-Checked -FilePath $frontendInstall.command -Arguments $frontendInstall.args -WorkingDirectory $frontendDir

if ($InstallPlaywright) {
  if ($frontendInstall.command -like '*corepack*') {
    Invoke-Checked -FilePath $frontendInstall.command -Arguments @('yarn', 'e2e:install') -WorkingDirectory $frontendDir
  } else {
    Invoke-Checked -FilePath $frontendInstall.command -Arguments @('e2e:install') -WorkingDirectory $frontendDir
  }
}

if ($StartServices) {
  if (-not (Test-Path -LiteralPath $composeLocal)) {
    throw "Local compose file not found at $composeLocal"
  }
  Invoke-Checked -FilePath 'docker' -Arguments @('compose', '-f', $composeLocal, 'up', '-d', 'postgres', 'redis')
}

Write-Host ''
Write-Host 'Bootstrap complete.'
Write-Host 'Next commands:'
Write-Host ' - powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight'
Write-Host ' - powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices'
Write-Host ' - powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices'

if ($RunDoctor) {
  $doctorArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $doctorScript)
  if ($StartServices) {
    $doctorArgs += '-RunPreflight'
    $doctorArgs += '-Strict'
  }
  Invoke-Checked -FilePath 'powershell.exe' -Arguments $doctorArgs
}
