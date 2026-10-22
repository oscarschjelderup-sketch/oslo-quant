# Register (or remove) the Windows scheduled task that writes the Sunday summary.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_weekly.ps1            # register
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_weekly.ps1 -Remove    # remove
#
# Sundays at 18:00 in this computer's local time; if the computer was asleep, the run starts when it wakes.
# The task runs as you, only while you are logged in, without administrator rights. It only reads and writes
# files in ~/osloquant-home; it never trades and never steps the paper accounts.

param([switch]$Remove)

$name = "oslo-quant weekly"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\run_weekly.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed the scheduled task '$name' (if it existed)."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "18:00"
# no UTC offset in the start time, so 18:00 stays 18:00 when summer time ends
$trigger.StartBoundary = (Get-Date "18:00").ToString("yyyy-MM-ddTHH:mm:ss")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "oslo-quant Sunday summary: what changed this week, judgements logged and judgements that should have been. Reads only; no real money." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $name
$next = ($task | Get-ScheduledTaskInfo).NextRunTime
Write-Output "Registered '$name'. Next run: $next"
Write-Output "Summaries: $(Join-Path $HOME 'osloquant-home\weekly')"
