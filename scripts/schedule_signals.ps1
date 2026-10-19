# Register (or remove) the Windows scheduled task that runs the signal watch after the Oslo close.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_signals.ps1            # register
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_signals.ps1 -Remove    # remove
#
# Two runs on weekdays, in this computer's local time:
#   17:45   after the close (Oslo closes at 16:25; in Lisbon or London 17:45 is 18:45 Oslo time, the bars are final)
#   21:45   in case the first one had no network
# A run that finds nothing new rewrites the same digest, so the second one costs a download and no more.
# If the computer was asleep at the time, the run starts when it wakes. The task runs as you, only while you
# are logged in, without administrator rights. It never steps the paper accounts.

param([switch]$Remove)

$name = "oslo-quant signals"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\run_signals.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed the scheduled task '$name' (if it existed)."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -WorkingDirectory $repo
$weekdays = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
$triggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "17:45"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "21:45")
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
    -Description "oslo-quant signal watch: refreshes the daily bars, scans for technical signals, writes the digest and shows a notification. Reads only; no real money." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $name
$next = ($task | Get-ScheduledTaskInfo).NextRunTime
Write-Output "Registered '$name'. Next run: $next"
Write-Output "Digests: $(Join-Path $HOME 'osloquant-home\signals')"
