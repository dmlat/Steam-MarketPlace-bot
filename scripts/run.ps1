param(
    [Parameter(Position = 0)]
    [ValidateSet("continue", "bulk", "pipeline")]
    [string]$Command = "continue",
    [Parameter(Position = 1)]
    [int]$RequestCap = 8000
)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 | Out-Null
Set-Location (Join-Path $PSScriptRoot "..")
switch ($Command) {
    "continue" { & "$PWD\.venv\Scripts\python.exe" "scripts\run_continue.py" $RequestCap }
    "bulk"     { & "$PWD\.venv\Scripts\python.exe" "scripts\run_bulk_collect.py" 10000 $RequestCap }
    "pipeline" { & "$PWD\.venv\Scripts\python.exe" "scripts\run_full_pipeline.py" "--resume" "--skip-discovery" "--request-cap" $RequestCap }
}