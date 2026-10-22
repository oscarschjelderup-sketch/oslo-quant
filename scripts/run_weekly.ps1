# The Sunday summary: what changed this week, the judgements logged, and the ones that should have been.
#
# Run by the Windows scheduled task that scripts\schedule_weekly.ps1 registers, or by hand:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_weekly.ps1"
#
# Reads the store, the research book and the judgement log; writes ~/osloquant-home/weekly/<year>-W<week>.md/.html,
# opens the page and shows a notification. It never trades and never steps the paper accounts.

$repo = Split-Path -Parent $PSScriptRoot
$oq = Join-Path $repo ".venv\Scripts\oq.exe"
$storeHome = if ($env:OSLOQUANT_HOME) { $env:OSLOQUANT_HOME } else { Join-Path $HOME "osloquant-home" }
$logDir = Join-Path $storeHome "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("weekly-output-{0}.log" -f (Get-Date -Format "yyyy"))

$env:PYTHONIOENCODING = "utf-8"
$env:COLUMNS = "160"
$ErrorActionPreference = "Continue"

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $log -Append -Encoding utf8
if (-not (Test-Path $oq)) {
    "oq is not installed at $oq. Create the environment first: uv venv; uv pip install -e ." | Out-File -FilePath $log -Append -Encoding utf8
    exit 3
}
$output = & $oq dashboard --refresh-only 2>&1 | ForEach-Object { "$_" }
$output | Out-File -FilePath $log -Append -Encoding utf8
$output = & $oq book weekly --open --notify 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$output | Out-File -FilePath $log -Append -Encoding utf8
"weekly exit code $code" | Out-File -FilePath $log -Append -Encoding utf8
exit $code
