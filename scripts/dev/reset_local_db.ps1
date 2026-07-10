param(
  [string]$DatabaseName = 'edfinder',
  [switch]$ConfirmReset,
  [switch]$SchemaOnly
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envFile = Join-Path $repoRoot '.env'
$composeLocal = Join-Path $repoRoot 'docker-compose.local.yml'
$runBash = Join-Path $repoRoot 'scripts\dev\run-bash.ps1'

function Require-Path {
  param([string]$PathValue, [string]$Label)

  if (-not (Test-Path -LiteralPath $PathValue)) {
    throw "$Label not found at $PathValue"
  }
}

function Get-EnvValue {
  param([string]$Name)

  $line = Get-Content -LiteralPath $envFile |
    Where-Object {
      $trimmed = $_.Trim()
      $trimmed -and -not $trimmed.StartsWith('#') -and $trimmed.StartsWith("$Name=")
    } |
    Select-Object -First 1

  if (-not $line) {
    return $null
  }

  return ($line -split '=', 2)[1].Trim()
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

Require-Path -PathValue $envFile -Label '.env'
Require-Path -PathValue $composeLocal -Label 'Local compose file'
Require-Path -PathValue $runBash -Label 'Git Bash wrapper'

if (-not $ConfirmReset) {
  throw 'Refusing destructive local DB reset without -ConfirmReset.'
}

$postgresPassword = Get-EnvValue -Name 'POSTGRES_PASSWORD'
if (-not $postgresPassword) {
  throw 'POSTGRES_PASSWORD is missing in .env'
}

Invoke-Checked -FilePath 'docker' -Arguments @('compose', '-f', $composeLocal, 'up', '-d', 'postgres', 'redis')

Invoke-Checked -FilePath 'docker' -Arguments @(
  'compose', '-f', $composeLocal, 'exec', '-T', 'postgres',
  'sh', '-lc',
  "dropdb -U edfinder --if-exists $DatabaseName && createdb -U edfinder $DatabaseName"
)

$env:COMPOSE_FILE = $composeLocal
$env:MIGRATION_DB_NAME = $DatabaseName
try {
  Invoke-Checked -FilePath 'powershell.exe' -Arguments @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $runBash,
    '-Script',
    'scripts/apply_migrations.sh',
    '-ScriptArgs',
    '--include-manual'
  )
} finally {
  Remove-Item Env:COMPOSE_FILE -ErrorAction SilentlyContinue
  Remove-Item Env:MIGRATION_DB_NAME -ErrorAction SilentlyContinue
}

if (-not $SchemaOnly) {
  Invoke-Checked -FilePath 'docker' -Arguments @(
    'compose', '-f', $composeLocal, 'exec', '-T', 'postgres',
    'sh', '-lc',
    "psql -U edfinder -d $DatabaseName -v ON_ERROR_STOP=1 -q -f /docker-entrypoint-initdb.d/seed_preview.sql"
  )
  Invoke-Checked -FilePath 'docker' -Arguments @(
    'compose', '-f', $composeLocal, 'exec', '-T', 'postgres',
    'psql', '-U', 'edfinder', '-d', $DatabaseName,
    '-v', 'ON_ERROR_STOP=1', '-q',
    '-c', 'SELECT refresh_map_mviews();'
  )
  Invoke-Checked -FilePath 'docker' -Arguments @(
    'compose', '-f', $composeLocal, 'exec', '-T', 'postgres',
    'psql', '-U', 'edfinder', '-d', $DatabaseName,
    '-v', 'ON_ERROR_STOP=1', '-q',
    '-c', 'REFRESH MATERIALIZED VIEW mv_archetype_rankings;'
  )
}

Write-Host ''
Write-Host "Local database reset complete: $DatabaseName"
Write-Host "Compose file: $composeLocal"
Write-Host ("Seeded preview data: {0}" -f ($(if ($SchemaOnly) { 'false' } else { 'true' })))
