param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ManageArgs
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$managePy = Join-Path $repoRoot "backend\\manage.py"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python executable not found at $pythonExe. Run scripts/dev/bootstrap.ps1 first."
    exit 1
}

if (-not (Test-Path $managePy)) {
    Write-Error "Django entry file not found at $managePy."
    exit 1
}

Push-Location $repoRoot
try {
    & $pythonExe $managePy @ManageArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
