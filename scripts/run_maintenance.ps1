param(
    [switch]$Execute,
    [int]$RunsOlderThanDays = 30,
    [int]$EventsOlderThanDays = 7
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("maintenance-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    throw 'uv was not found on PATH.'
}

$arguments = @(
    'run', '--no-sync', 'python', 'scripts/prune_agent_history.py',
    '--runs-older-than-days', $RunsOlderThanDays,
    '--events-older-than-days', $EventsOlderThanDays
)
if (-not $Execute) { $arguments += '--dry-run' }

Push-Location $root
try {
    & $uv @arguments 2>&1 | Tee-Object -FilePath $logFile
    if ($LASTEXITCODE -ne 0) { throw "Maintenance command failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Write-Output "Maintenance log: $logFile"
