# PowerShell entrypoint wrapper for Scout CLI tool
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (Test-Path $PythonPath) {
    & $PythonPath -m python.main @args
} else {
    Write-Error "Virtual environment not found. Please ensure .venv is configured."
}
