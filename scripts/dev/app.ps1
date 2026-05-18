param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status",
    [string]$AddrPort = "127.0.0.1:8000"
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$managePy = Join-Path $repoRoot "backend\manage.py"
$stateDir = Join-Path $repoRoot "output\dev"
$pidFile = Join-Path $stateDir "runserver.json"
$stdoutLog = Join-Path $stateDir "runserver.out.log"
$stderrLog = Join-Path $stateDir "runserver.err.log"

function Read-RunserverState {
    if (-not (Test-Path $pidFile)) {
        return $null
    }

    try {
        return Get-Content -Path $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-RunserverProcess($state) {
    if ($null -eq $state -or -not $state.pid) {
        return $null
    }

    try {
        return Get-Process -Id ([int]$state.pid) -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Start-Runserver {
    if (-not (Test-Path $pythonExe)) {
        Write-Error "Python executable not found at $pythonExe. Run scripts/dev/bootstrap.cmd first."
        exit 1
    }
    if (-not (Test-Path $managePy)) {
        Write-Error "Django entry file not found at $managePy."
        exit 1
    }

    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

    $state = Read-RunserverState
    $running = Get-RunserverProcess $state
    if ($null -ne $running) {
        Write-Host "Django dev server is already running. PID: $($running.Id)"
        Write-Host "URL: http://$($state.addrPort)"
        return
    }

    if (Test-Path $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }

    $arguments = @("backend\manage.py", "runserver", $AddrPort, "--noreload")
    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $arguments `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -WindowStyle Hidden `
        -PassThru

    $stateObject = [ordered]@{
        pid = $process.Id
        addrPort = $AddrPort
        startedAt = (Get-Date).ToString("s")
        stdoutLog = $stdoutLog
        stderrLog = $stderrLog
    }
    $stateObject | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

    Start-Sleep -Seconds 2
    $running = Get-RunserverProcess (Read-RunserverState)
    if ($null -eq $running) {
        Write-Error "Django dev server failed to start. Check $stderrLog"
        exit 1
    }

    Write-Host "Django dev server started. PID: $($process.Id)"
    Write-Host "URL: http://$AddrPort"
    Write-Host "Logs: $stdoutLog"
}

function Stop-Runserver {
    $state = Read-RunserverState
    $running = Get-RunserverProcess $state

    if ($null -eq $running) {
        if (Test-Path $pidFile) {
            Remove-Item -LiteralPath $pidFile -Force
        }
        Write-Host "Django dev server is not running."
        return
    }

    Stop-Process -Id $running.Id
    Start-Sleep -Seconds 1
    if (Test-Path $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }
    Write-Host "Django dev server stopped. PID: $($running.Id)"
}

function Show-RunserverStatus {
    $state = Read-RunserverState
    $running = Get-RunserverProcess $state

    if ($null -eq $running) {
        Write-Host "Django dev server is not running."
        if (Test-Path $pidFile) {
            Write-Host "Stale state file: $pidFile"
        }
        return
    }

    Write-Host "Django dev server is running. PID: $($running.Id)"
    Write-Host "URL: http://$($state.addrPort)"
    Write-Host "Started at: $($state.startedAt)"
    Write-Host "Logs: $($state.stdoutLog)"
}

switch ($Action) {
    "start" { Start-Runserver }
    "stop" { Stop-Runserver }
    "restart" {
        Stop-Runserver
        Start-Runserver
    }
    "status" { Show-RunserverStatus }
}
