# The evening job: step the paper accounts forward and keep everything it printed.
#
# Run by the Windows scheduled task that scripts\schedule_live.ps1 registers, or by hand:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_live.ps1"
#
# Running it more than once an evening is harmless: an account that is already at the last session is left alone.
# Exit code 0 = fine, 1 = an account failed, 2 = the download failed (the task then tries again a little later).

$repo = Split-Path -Parent $PSScriptRoot
$oq = Join-Path $repo ".venv\Scripts\oq.exe"
$storeHome = if ($env:OSLOQUANT_HOME) { $env:OSLOQUANT_HOME } else { Join-Path $HOME "osloquant-home" }
$logDir = Join-Path $storeHome "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("live-output-{0}.log" -f (Get-Date -Format "yyyy-MM"))

$env:PYTHONIOENCODING = "utf-8"
$env:COLUMNS = "160"
$ErrorActionPreference = "Continue"

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $log -Append -Encoding utf8
if (-not (Test-Path $oq)) {
    "oq is not installed at $oq. Create the environment first: uv venv; uv pip install -e ." | Out-File -FilePath $log -Append -Encoding utf8
    exit 3
}
$output = & $oq live 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$output | Out-File -FilePath $log -Append -Encoding utf8
"exit code $code" | Out-File -FilePath $log -Append -Encoding utf8
exit $code
