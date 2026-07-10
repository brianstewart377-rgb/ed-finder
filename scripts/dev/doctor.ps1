param(
  [switch]$Json,
  [switch]$RunPreflight,
  [switch]$Strict
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$frontendDir = Join-Path $repoRoot 'frontend'
$envFile = Join-Path $repoRoot '.env'
$envExample = Join-Path $repoRoot 'env.example'
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$preflightScript = Join-Path $repoRoot 'scripts\dev\test_env_preflight.py'
$composeLocal = Join-Path $repoRoot 'docker-compose.local.yml'

function Find-BashExecutable {
  $candidates = @(
    $env:EDFINDER_BASH,
    (Join-Path ${env:ProgramFiles} 'Git\bin\bash.exe'),
    (Join-Path ${env:ProgramFiles} 'Git\usr\bin\bash.exe'),
    (Join-Path ${env:ProgramW6432} 'Git\bin\bash.exe'),
    (Join-Path ${env:ProgramW6432} 'Git\usr\bin\bash.exe'),
    (Join-Path ${env:LOCALAPPDATA} 'Programs\Git\bin\bash.exe'),
    (Join-Path ${env:LOCALAPPDATA} 'Programs\Git\usr\bin\bash.exe')
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return @{
        ok = $true
        path = (Resolve-Path -LiteralPath $candidate).Path
        source = 'explicit_or_known_location'
      }
    }
  }

  foreach ($name in @('bash.exe', 'bash')) {
    try {
      $command = Get-Command $name -ErrorAction Stop
      if ($command.Path) {
        return @{
          ok = $true
          path = $command.Path
          source = 'PATH'
        }
      }
    } catch {
    }
  }

  return @{
    ok = $false
    path = $null
    source = $null
    failure = 'git_bash_not_found'
  }
}

function Get-CommandRecord {
  param(
    [string]$Name,
    [string[]]$VersionArgs = @('--version')
  )

  try {
    $command = Get-Command $Name -ErrorAction Stop
    $versionText = ''
    try {
      $result = & $command.Path @VersionArgs 2>&1 | Select-Object -First 1
      $versionText = [string]$result
    } catch {
      $versionText = ''
    }
    return @{
      ok = $true
      path = $command.Path
      version = $versionText.Trim()
    }
  } catch {
    return @{
      ok = $false
      path = $null
      version = $null
      failure = ($Name + '_not_found')
    }
  }
}

function Find-PythonRecord {
  if (Test-Path -LiteralPath $venvPython) {
    $version = (& $venvPython --version 2>&1 | Select-Object -First 1).ToString().Trim()
    return @{
      ok = $true
      path = $venvPython
      source = 'venv'
      version = $version
    }
  }

  try {
    $version = (& py -3.12 --version 2>&1 | Select-Object -First 1).ToString().Trim()
    return @{
      ok = $true
      path = 'py -3.12'
      source = 'py_launcher'
      version = $version
    }
  } catch {
  }

  try {
    $command = Get-Command python -ErrorAction Stop
    $version = (& $command.Path --version 2>&1 | Select-Object -First 1).ToString().Trim()
    return @{
      ok = $true
      path = $command.Path
      source = 'PATH'
      version = $version
    }
  } catch {
  }

  return @{
    ok = $false
    path = $null
    source = $null
    version = $null
    failure = 'python_not_found'
  }
}

function Get-YarnRecord {
  $yarn = Get-CommandRecord -Name 'yarn'
  if ($yarn.ok) {
    $yarn.source = 'yarn'
    return $yarn
  }

  $corepack = Get-CommandRecord -Name 'corepack'
  if ($corepack.ok) {
    $versionText = ''
    try {
      $versionText = (& $corepack.path yarn --version 2>&1 | Select-Object -First 1).ToString().Trim()
    } catch {
      $versionText = ''
    }
    return @{
      ok = $true
      path = $corepack.path
      source = 'corepack_yarn'
      version = $versionText
    }
  }

  return @{
    ok = $false
    path = $null
    source = $null
    version = $null
    failure = 'yarn_not_found'
  }
}

function Get-DockerComposeRecord {
  $docker = Get-CommandRecord -Name 'docker'
  if (-not $docker.ok) {
    return @{
      ok = $false
      path = $null
      version = $null
      failure = 'docker_not_found'
    }
  }

  try {
    $version = (& $docker.path compose version 2>&1 | Select-Object -First 1).ToString().Trim()
    return @{
      ok = $true
      path = $docker.path
      version = $version
    }
  } catch {
    return @{
      ok = $false
      path = $docker.path
      version = $null
      failure = 'docker_compose_unavailable'
    }
  }
}

function Get-EnvFileRecord {
  $record = @{
    ok = Test-Path -LiteralPath $envFile
    path = $envFile
    postgres_password_present = $false
  }

  if ($record.ok) {
    $hasPassword = Select-String -Path $envFile -Pattern '^\s*POSTGRES_PASSWORD\s*=\s*\S+' -Quiet
    $record.postgres_password_present = $hasPassword
  }

  return $record
}

function Invoke-PreflightRecord {
  if (-not (Test-Path -LiteralPath $preflightScript)) {
    return @{
      ok = $false
      skipped = $false
      failure = 'preflight_script_missing'
    }
  }

  if (-not (Test-Path -LiteralPath $venvPython)) {
    return @{
      ok = $false
      skipped = $true
      failure = 'venv_missing'
    }
  }

  $jsonText = ''
  Push-Location $repoRoot
  try {
    $jsonText = & $venvPython -B $preflightScript 2>&1
    $exitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }

  $outputText = ($jsonText | Out-String).Trim()
  $parsed = $null
  try {
    $parsed = $outputText | ConvertFrom-Json -Depth 20
  } catch {
  }

  return @{
    ok = ($exitCode -eq 0)
    skipped = $false
    exit_code = $exitCode
    failure = if ($parsed) { $parsed.failure_category } else { 'preflight_failed' }
    summary = if ($parsed) { $parsed.failure_category } else { $outputText.Substring(0, [Math]::Min(300, $outputText.Length)) }
  }
}

$records = [ordered]@{
  bash = Find-BashExecutable
  python = Find-PythonRecord
  venv = @{
    ok = Test-Path -LiteralPath $venvPython
    path = $venvPython
  }
  node = Get-CommandRecord -Name 'node'
  yarn = Get-YarnRecord
  git = Get-CommandRecord -Name 'git'
  docker = Get-CommandRecord -Name 'docker'
  docker_compose = Get-DockerComposeRecord
  pg_isready = Get-CommandRecord -Name 'pg_isready'
  env_file = Get-EnvFileRecord
  env_example = @{
    ok = Test-Path -LiteralPath $envExample
    path = $envExample
  }
  docker_compose_local = @{
    ok = Test-Path -LiteralPath $composeLocal
    path = $composeLocal
  }
  frontend_package = @{
    ok = Test-Path -LiteralPath (Join-Path $frontendDir 'package.json')
    path = Join-Path $frontendDir 'package.json'
  }
  frontend_yarn_lock = @{
    ok = Test-Path -LiteralPath (Join-Path $frontendDir 'yarn.lock')
    path = Join-Path $frontendDir 'yarn.lock'
  }
}

if ($RunPreflight) {
  $records.python_preflight = Invoke-PreflightRecord
} else {
  $records.python_preflight = @{
    ok = $null
    skipped = $true
    failure = $null
  }
}

$requiredChecks = @(
  'bash',
  'python',
  'node',
  'yarn',
  'git',
  'docker',
  'docker_compose',
  'env_example',
  'docker_compose_local',
  'frontend_package',
  'frontend_yarn_lock'
)

$overallOk = $true
foreach ($name in $requiredChecks) {
  if (-not $records[$name].ok) {
    $overallOk = $false
  }
}

if ($RunPreflight -and $records.python_preflight.ok -ne $true) {
  $overallOk = $false
}

$recommendations = New-Object System.Collections.Generic.List[string]
if (-not $records.bash.ok) {
  $recommendations.Add('Install Git for Windows or set EDFINDER_BASH to bash.exe.')
}
if (-not $records.venv.ok) {
  $recommendations.Add('Create the virtualenv with scripts/dev/bootstrap-windows.ps1.')
}
if (-not $records.env_file.ok) {
  $recommendations.Add('Create .env from env.example before starting the local API.')
} elseif (-not $records.env_file.postgres_password_present) {
  $recommendations.Add('.env exists but POSTGRES_PASSWORD is missing.')
}
if (-not $records.pg_isready.ok) {
  $recommendations.Add('Install PostgreSQL client tools if you want full DB readiness checks.')
}
if (-not $RunPreflight) {
  $recommendations.Add('Re-run with -RunPreflight after dependencies and local services are ready.')
}

$result = [ordered]@{
  repo_root = $repoRoot
  overall_ok = $overallOk
  checks = $records
  recommendations = @($recommendations)
}

if ($Json) {
  $result | ConvertTo-Json -Depth 10
} else {
  Write-Host "ED-Finder Windows doctor"
  Write-Host "Repo: $repoRoot"
  foreach ($name in $records.Keys) {
    $record = $records[$name]
    if ($record.Contains('skipped') -and $record.skipped) {
      Write-Host ("[skip] {0}" -f $name)
      continue
    }

    if ($record.ok -eq $true) {
      $detail = @()
      if ($record.path) {
        $detail += $record.path
      }
      if ($record.version) {
        $detail += $record.version
      }
      if ($record.source) {
        $detail += "source=$($record.source)"
      }
      Write-Host ("[ ok ] {0} {1}" -f $name, ($detail -join ' | '))
    } elseif ($record.ok -eq $false) {
      $failure = if ($record.failure) { $record.failure } else { 'check_failed' }
      Write-Host ("[fail] {0} {1}" -f $name, $failure)
    } else {
      Write-Host ("[info] {0}" -f $name)
    }
  }

  if ($recommendations.Count -gt 0) {
    Write-Host ''
    Write-Host 'Next actions:'
    foreach ($item in $recommendations) {
      Write-Host (" - {0}" -f $item)
    }
  }
}

if ($Strict -and -not $overallOk) {
  exit 1
}
