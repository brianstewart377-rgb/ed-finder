param(
  [switch]$SkipPull,
  [switch]$NoPrompt,
  [switch]$OpenPlanner,
  [string]$PlannerUrl = 'http://localhost:3000/#colony-planner/system/1453586352459'
)

$ErrorActionPreference = 'Stop'

$repo = 'C:\Users\brian\Documents\Codex\2026-05-20\files-mentioned-by-the-user-edfinder'
$frontend = Join-Path $repo 'frontend-v2'

if (-not (Test-Path -LiteralPath $repo)) {
  throw "Repo not found: $repo"
}
if (-not (Test-Path -LiteralPath $frontend)) {
  throw "Frontend path not found: $frontend"
}

if (-not $NoPrompt) {
  $answer = Read-Host "Start ED-Finder dev from $repo ? (y/N)"
  if ($answer -notin @('y', 'Y')) {
    throw 'Cancelled by user.'
  }
}

Set-Location $repo

if (-not $SkipPull) {
  git pull --ff-only
}

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') {
  throw "Expected branch main but found: $branch"
}

# Ensure nothing stale is left on :3000.
$listeners = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
  $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
    try {
      Stop-Process -Id $_ -Force -ErrorAction Stop
    } catch {
      throw "Unable to stop process $_ on port 3000. Run PowerShell as Administrator once and retry."
    }
  }
}

Set-Location $frontend

Start-Process -FilePath powershell -WindowStyle Hidden -WorkingDirectory $frontend -ArgumentList '-NoProfile', '-Command', 'npm run dev'

# Wait until API health responds.
$healthy = $false
1..80 | ForEach-Object {
  try {
    $health = Invoke-RestMethod -Uri 'http://localhost:3000/api/health' -ErrorAction Stop
    if ($health.status -eq 'ok') {
      $healthy = $true
      return
    }
  } catch {
    Start-Sleep -Milliseconds 500
  }
}
if (-not $healthy) {
  throw 'Health check failed at http://localhost:3000/api/health'
}

# Verify the runtime is serving the Stage 17F planner source markers.
$servedSource = (Invoke-WebRequest -Uri 'http://localhost:3000/src/features/colony-planner/BodySlotPlanner.tsx' -UseBasicParsing -ErrorAction Stop).Content
if ($servedSource -notmatch 'BodyRingMap' -or $servedSource -notmatch 'LaneAddNode' -or $servedSource -notmatch 'Body core') {
  throw 'Runtime mismatch: Stage 17F markers not detected in served source.'
}

if ($OpenPlanner) {
  Start-Process $PlannerUrl
}

[PSCustomObject]@{
  repo = $repo
  branch = $branch
  commit = (git -C $repo rev-parse --short HEAD)
  plannerUrl = $PlannerUrl
  stage17fRuntimeVerified = $true
  health = (Invoke-RestMethod -Uri 'http://localhost:3000/api/health' -ErrorAction Stop)
} | ConvertTo-Json -Depth 6
