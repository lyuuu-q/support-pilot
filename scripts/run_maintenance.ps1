param(
    [switch]$Execute,
    [int]$RunsOlderThanDays = 30,
    [int]$EventsOlderThanDays = 7,
    [int]$SessionsOlderThanDays = 30
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

function Invoke-Prune {
    param(
        [string]$Script,
        [string[]]$ScriptArguments
    )
    $arguments = @('run', '--no-sync', 'python', $Script) + $ScriptArguments
    if (-not $Execute) { $arguments += '--dry-run' }
    & $uv @arguments 2>&1 | Tee-Object -FilePath $logFile -Append
    if ($LASTEXITCODE -ne 0) { throw "$Script failed with exit code $LASTEXITCODE" }
}

Push-Location $root
try {
    Invoke-Prune -Script 'scripts/prune_agent_history.py' -ScriptArguments @(
        '--runs-older-than-days', $RunsOlderThanDays,
        '--events-older-than-days', $EventsOlderThanDays
    )
    Invoke-Prune -Script 'scripts/prune_auth_sessions.py' -ScriptArguments @(
        '--sessions-older-than-days', $SessionsOlderThanDays
    )
}
finally {
    Pop-Location
}

Write-Output "Maintenance log: $logFile"
