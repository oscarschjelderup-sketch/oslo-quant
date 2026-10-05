# Register (or remove) the Windows scheduled task that runs the evening job.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_live.ps1            # register
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_live.ps1 -Remove    # remove
#
# Three runs a day, all in this computer's local time:
#   Monday to Friday 17:30   the main run. Oslo closes at 16:25; in Lisbon or London this is 18:30 Oslo time.
#   Monday to Friday 21:30   in case the first one had no network.
#   every day        07:30   the last chance to write the decisions down before Oslo opens at 09:00.
# A run that finds nothing new does nothing, so the extra ones cost a download and no more.
# If the computer was asleep at the time, the run starts when it wakes.
#
# The task runs as you, only while you are logged in, without administrator rights.

param([switch]$Remove)

$name = "oslo-quant live"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\run_live.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed the scheduled task '$name' (if it existed)."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -WorkingDirectory $repo
$weekdays = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
$triggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "17:30"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "21:30"),
    (New-ScheduledTaskTrigger -Daily -At "07:30")
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
    -Description "Steps the oslo-quant paper accounts forward after each Oslo close (oq live). No real money is involved." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $name
$next = ($task | Get-ScheduledTaskInfo).NextRunTime
Write-Output "Registered '$name'. Next run: $next"
Write-Output "Output of each run: $(Join-Path $HOME 'osloquant-home\logs')"
