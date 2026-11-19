# Monthly refresh of Arivazhai's knowledge base on Windows: crawl the official website again, index what
# changed, and email the admin (REPORT_EMAIL_TO in .env) what was updated. Output goes to data\logs.
#
# Run it once by hand:
#   powershell -ExecutionPolicy Bypass -File scripts\refresh.ps1
#
# Schedule it on the 1st of every month at 2 AM (run once in PowerShell, from the project folder):
#   schtasks /Create /TN "Arivazhai monthly refresh" /SC MONTHLY /D 1 /ST 02:00 /F `
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\refresh.ps1`""
# Check it:   schtasks /Query /TN "Arivazhai monthly refresh"
# Run now:    schtasks /Run /TN "Arivazhai monthly refresh"
# Remove it:  schtasks /Delete /TN "Arivazhai monthly refresh" /F
#
# The computer must be on (not asleep) at that time; if it was off, Task Scheduler's "Run task as soon as
# possible after a scheduled start is missed" (task Properties > Settings) catches up.
# If the API server runs all the time, REFRESH_EVERY_DAYS=30 in .env does the same without this script.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$Logs = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs ("refresh-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

Set-Location (Join-Path $Root "backend")
$env:PYTHONIOENCODING = "utf-8"
& $Python -m rag.cli refresh *>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
