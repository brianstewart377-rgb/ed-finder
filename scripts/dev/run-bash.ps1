param(
  [string]$Command,
  [string]$Script,
  [string[]]$ScriptArgs = @(),
  [string]$WorkingDirectory,
  [switch]$PrintCommand
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $WorkingDirectory) {
  $WorkingDirectory = $repoRoot
}

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
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  foreach ($name in @('bash.exe', 'bash')) {
    try {
      $command = Get-Command $name -ErrorAction Stop
      if ($command.Path) {
        return $command.Path
      }
    } catch {
    }
  }

  throw @"
Git Bash was not found.

Install Git for Windows, add bash.exe to PATH, or set EDFINDER_BASH to the full
path of bash.exe before running this wrapper.
"@
}

function Convert-ToBashLiteral {
  param([string]$Value)

  if ($null -eq $Value -or $Value.Length -eq 0) {
    return "''"
  }

  return "'" + $Value.Replace("'", "'""'""'") + "'"
}

function Convert-ToBashPath {
  param([string]$PathValue)

  $fullPath = [System.IO.Path]::GetFullPath($PathValue)
  $normalized = $fullPath.Replace('\', '/')

  if ($normalized -match '^([A-Za-z]):/(.*)$') {
    return '/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2]
  }

  return $normalized
}

if ([string]::IsNullOrWhiteSpace($Command) -and [string]::IsNullOrWhiteSpace($Script)) {
  throw 'Provide either -Command or -Script.'
}

if (-not [string]::IsNullOrWhiteSpace($Command) -and -not [string]::IsNullOrWhiteSpace($Script)) {
  throw 'Use either -Command or -Script, not both.'
}

$bashExe = Find-BashExecutable

if ($Script) {
  $candidateScript = $Script
  if (-not [System.IO.Path]::IsPathRooted($candidateScript)) {
    $candidateScript = Join-Path $repoRoot $candidateScript
  }

  if (-not (Test-Path -LiteralPath $candidateScript)) {
    throw "Script not found at $candidateScript"
  }

  $bashScriptPath = Convert-ToBashPath -PathValue $candidateScript
  $quotedArgs = @($ScriptArgs | ForEach-Object { Convert-ToBashLiteral $_ })
  $commandParts = @('bash', (Convert-ToBashLiteral $bashScriptPath)) + $quotedArgs
  $Command = ($commandParts -join ' ')
}

if ($PrintCommand) {
  Write-Host "Using bash: $bashExe"
  Write-Host "Working dir: $WorkingDirectory"
  Write-Host "Command: $Command"
}

Push-Location $WorkingDirectory
try {
  & $bashExe -lc $Command
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
