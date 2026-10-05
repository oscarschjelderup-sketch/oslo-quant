# Register (or remove) the Windows scheduled task that drives the intraday paper accounts.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_intraday.ps1            # register
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schedule_intraday.ps1 -Remove    # remove
#
# The task runs `python -m osloquant.tick` every 15 minutes, around the clock, at :01, :16, :31 and :46.
# Each run is one look at the market (`oq intraday poll`): fill, value, raise signals, send orders. Outside
# Oslo's trading hours a run does nothing and is over in milliseconds. The minutes are one minute after each
# 15-minute bar has come through Yahoo's delayed feed, in any time zone a whole number of hours from Oslo.
#
# Why around the clock and not "weekdays from 07:46": a repetition that hangs on a daily start time never
# begins on a day the computer was asleep at that time. That is how the first trading day was missed.
# This one has no daily start to miss. If the computer was asleep at a quarter, the look happens when it wakes.
#
# One short run every quarter of an hour, rather than one program running all day, because a laptop sleeps:
# a look that is missed is a signal that is missed, and the next look carries on from the saved state.
#
# The task runs as you, only while you are logged in, without administrator rights and without a window.
# What each run printed is kept in ~/osloquant-home/logs/headless-YYYY-MM.log, one line per look in intraday.log.
# `oq doctor` tells you whether it has been running. Play money only.

param([switch]$Remove)

$name = "oslo-quant intraday"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\pythonw.exe"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed the scheduled task '$name' (if it existed)."
    exit 0
}
if (-not (Test-Path $python)) {
    Write-Output "No Python environment at $python. Create it first: uv venv; uv pip install -e ."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $python -Argument "-m osloquant.tick" -WorkingDirectory $repo
# one start in the past, repeated every 15 minutes without end
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Looks at Oslo every 15 minutes for the oslo-quant intraday paper accounts (python -m osloquant.tick). Play money only." -Force | Out-Null

$next = (Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo).NextRunTime
Write-Output "Registered '$name'. Next run: $next"
