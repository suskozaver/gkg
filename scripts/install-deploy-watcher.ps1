<#
  Registers the GKG deploy watcher as a task that starts when you sign in to
  Windows, hidden, and starts it now. Run once in PowerShell:

    powershell -ExecutionPolicy Bypass -File C:\googlekeep-garmin\scripts\install-deploy-watcher.ps1

  To remove it:  Unregister-ScheduledTask -TaskName "GKG deploy watcher" -Confirm:$false
#>

$Name   = "GKG deploy watcher"
$Script = Join-Path $PSScriptRoot "deploy-watcher.ps1"

$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Description "Pushes, deploys (docker compose up -d --build) and builds the watch app for GKG when a request file appears in its repo." -Force | Out-Null
Start-ScheduledTask -TaskName $Name

Start-Sleep -Seconds 2
$state = (Get-ScheduledTask -TaskName $Name).State
Write-Host "$Name is $state, watching $(Split-Path -Parent $PSScriptRoot). Claude can now push and deploy with request files there."
