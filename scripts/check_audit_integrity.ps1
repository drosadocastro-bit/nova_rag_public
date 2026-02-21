param(
    [string]$DbPath = "",
    [int]$Limit = 0,
    [switch]$IncludeDetails,
    [switch]$StrictUnhashed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe"
}

$argsList = @("scripts/check_audit_integrity.py")
if (-not [string]::IsNullOrWhiteSpace($DbPath)) {
    $argsList += @("--db-path", $DbPath)
}
if ($Limit -gt 0) {
    $argsList += @("--limit", $Limit)
}
if ($IncludeDetails) {
    $argsList += "--include-details"
}
if ($StrictUnhashed) {
    $argsList += "--strict-unhashed"
}

Push-Location $repoRoot
try {
    & $pythonExe @argsList
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
