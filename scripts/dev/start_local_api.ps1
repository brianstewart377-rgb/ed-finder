param(
  [switch]$EnsureServices,
  [int]$Port = 8001
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $repoRoot '.env'

if (-not (Test-Path -LiteralPath $venvPython)) {
  throw "Virtualenv not found at $venvPython"
}

if (-not (Test-Path -LiteralPath $envFile)) {
  throw "Expected repo .env at $envFile"
}

$envValues = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith('#')) {
    return
  }
  $parts = $line.Split('=', 2)
  if ($parts.Count -eq 2) {
    $envValues[$parts[0].Trim()] = $parts[1].Trim()
  }
}

$postgresPassword = $envValues['POSTGRES_PASSWORD']
if (-not $postgresPassword) {
  throw 'POSTGRES_PASSWORD is missing in .env'
}

if ($EnsureServices) {
  docker compose -f (Join-Path $repoRoot 'docker-compose.local.yml') up -d postgres redis
}

$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DATABASE_URL = "postgresql://edfinder:$postgresPassword@127.0.0.1:55432/edfinder"
$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
$env:CORS_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5174,http://127.0.0.1:5174'
$env:EXPOSE_ERROR_DETAIL = 'false'
$env:LOG_LEVEL = 'INFO'
$env:PORT = "$Port"

Set-Location $repoRoot
& $venvPython -m uvicorn main:app --app-dir apps/api/src --host 127.0.0.1 --port $Port
