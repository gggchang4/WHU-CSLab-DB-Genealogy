param(
    [switch]$SkipMigrate
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$venvDir = Join-Path $repoRoot ".venv"
$pythonExe = Join-Path $venvDir "Scripts\\python.exe"
$envExample = Join-Path $repoRoot "backend\\.env.example"
$envFile = Join-Path $repoRoot "backend\\.env"
$requirementsFile = Join-Path $repoRoot "requirements.txt"
$manageScript = Join-Path $repoRoot "scripts\\dev\\manage.ps1"

Push-Location $repoRoot
try {
    if (-not (Test-Path $venvDir)) {
        Write-Host "Creating virtual environment .venv ..."
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Virtual environment creation failed. Make sure Python is installed."
        }
    }

    Write-Host "Installing Python dependencies ..."
    & $pythonExe -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }

    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample $envFile
        Write-Host "Created backend/.env. Update it with your local PostgreSQL credentials."
    }
    else {
        Write-Host "backend/.env already exists. Skipping template copy."
    }

    if (-not $SkipMigrate) {
        Write-Host "Running Django migrate ..."
        & $manageScript migrate
        if ($LASTEXITCODE -ne 0) {
            throw "Database migration failed. Check PostgreSQL, database creation, and backend/.env."
        }
    }
}
finally {
    Pop-Location
}
