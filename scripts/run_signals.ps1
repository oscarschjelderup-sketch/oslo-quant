# The signal watch: refresh the daily bars and the dashboard's feeds, scan the universe, write the digest (the
# dashboard's front page as latest.html) and raise a toast.
#
# Run by the Windows scheduled task that scripts\schedule_signals.ps1 registers, or by hand:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_signals.ps1"
#
# It does not touch the paper accounts (those run on GitHub Actions). Exit code 0 = fine, 2 = the download failed.

$repo = Split-Path -Parent $PSScriptRoot
$oq = Join-Path $repo ".venv\Scripts\oq.exe"
$storeHome = if ($env:OSLOQUANT_HOME) { $env:OSLOQUANT_HOME } else { Join-Path $HOME "osloquant-home" }
$logDir = Join-Path $storeHome "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("signals-output-{0}.log" -f (Get-Date -Format "yyyy-MM"))

$env:PYTHONIOENCODING = "utf-8"
$env:COLUMNS = "160"
$ErrorActionPreference = "Continue"

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $log -Append -Encoding utf8
if (-not (Test-Path $oq)) {
    "oq is not installed at $oq. Create the environment first: uv venv; uv pip install -e ." | Out-File -FilePath $log -Append -Encoding utf8
    exit 3
}
$output = & $oq record 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$output | Out-File -FilePath $log -Append -Encoding utf8
"record exit code $code" | Out-File -FilePath $log -Append -Encoding utf8
if ($code -ne 0) { exit 2 }

# announcements, rates, FX, salmon price, Brent and headlines for the dashboard; a failed feed keeps its old cache
$output = & $oq dashboard --refresh-only 2>&1 | ForEach-Object { "$_" }
$output | Out-File -FilePath $log -Append -Encoding utf8
"feeds exit code $LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8

# latest.html is the dashboard's front page (oq dashboard serves the live version at http://127.0.0.1:8060)
$output = & $oq signals digest --notify --open --quiet 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$output | Out-File -FilePath $log -Append -Encoding utf8
"digest exit code $code" | Out-File -FilePath $log -Append -Encoding utf8
exit $code
