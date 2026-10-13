param(
    [string]$TaskName = 'SupportPilotMaintenance',
    [string]$At = '03:30',
    [switch]$Remove,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$maintenance = Join-Path $root 'scripts\run_maintenance.ps1'
if (-not (Test-Path $maintenance)) {
    throw "maintenance script not found: $maintenance"
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -WhatIf:$WhatIf
    Write-Output "Requested removal of scheduled task '$TaskName'."
    exit 0
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$maintenance`" -Execute"
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
$description = 'SupportPilot daily maintenance: prune agent history and expired auth sessions.'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description $description -WhatIf:$WhatIf

Write-Output "Scheduled task '$TaskName' configured for $At daily (requires an elevated shell)."
