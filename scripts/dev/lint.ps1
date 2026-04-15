$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python executable not found at $pythonExe. Run scripts/dev/bootstrap.ps1 first."
    exit 1
}

Push-Location $repoRoot
try {
    & $pythonExe -m ruff check backend
    if ($LASTEXITCODE -eq 0) {
        exit 0
    }

    Write-Error "Ruff check failed. If ruff is missing, install it with: .\\.venv\\Scripts\\python.exe -m pip install ruff"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
