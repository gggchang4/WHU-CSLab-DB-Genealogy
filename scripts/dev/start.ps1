param(
    [string]$BackendAddrPort = "127.0.0.1:8000",
    [string]$FrontendHost = "127.0.0.1",
    [int]$FrontendPort = 5173,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"

if ($BackendOnly -and $FrontendOnly) {
    Write-Error "BackendOnly and FrontendOnly cannot be used together."
    exit 1
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runserverScript = Join-Path $repoRoot "scripts\dev\runserver.ps1"
$frontendDir = Join-Path $repoRoot "frontend"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$nodeModulesDir = Join-Path $frontendDir "node_modules"

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    if (Get-Command taskkill.exe -ErrorAction SilentlyContinue) {
        taskkill.exe /PID $ProcessId /T /F | Out-Null
    }
    else {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (-not $FrontendOnly -and -not (Test-Path $pythonExe)) {
    Write-Error "Python virtual environment not found. Run scripts/dev/bootstrap.cmd first."
    exit 1
}

if (-not $BackendOnly) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm was not found. Install Node.js before starting the Vite frontend."
        exit 1
    }

    if (-not (Test-Path $nodeModulesDir) -and -not $SkipFrontendInstall) {
        Write-Host "Installing frontend dependencies ..."
        Push-Location $frontendDir
        try {
            npm install
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend dependency installation failed."
            }
        }
        finally {
            Pop-Location
        }
    }
}

$processes = @()
$exitCode = 0

try {
    if (-not $FrontendOnly) {
        Write-Host "Starting Django backend at http://$BackendAddrPort ..."
        $backendProcess = Start-Process `
            -FilePath "powershell" `
            -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $runserverScript, "-AddrPort", $BackendAddrPort) `
            -WorkingDirectory $repoRoot `
            -NoNewWindow `
            -PassThru
        $processes += [PSCustomObject]@{
            Name = "Django backend"
            Process = $backendProcess
        }
    }

    if (-not $BackendOnly) {
        Write-Host "Starting Vite frontend at http://$FrontendHost`:$FrontendPort ..."
        $frontendProcess = Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList @("/c", "npm", "run", "dev", "--", "--host", $FrontendHost, "--port", $FrontendPort) `
            -WorkingDirectory $frontendDir `
            -NoNewWindow `
            -PassThru
        $processes += [PSCustomObject]@{
            Name = "Vite frontend"
            Process = $frontendProcess
        }
    }

    Write-Host ""
    Write-Host "Development servers are starting. Press Ctrl+C to stop them."
    if (-not $FrontendOnly) {
        Write-Host "Backend:  http://$BackendAddrPort/"
    }
    if (-not $BackendOnly) {
        Write-Host "Frontend: http://$FrontendHost`:$FrontendPort/app/"
    }
    Write-Host ""

    while ($true) {
        foreach ($entry in $processes) {
            $entry.Process.Refresh()
        }

        $stoppedProcesses = $processes | Where-Object { $_.Process.HasExited }
        if ($stoppedProcesses) {
            foreach ($entry in $stoppedProcesses) {
                Write-Warning "$($entry.Name) stopped with exit code $($entry.Process.ExitCode)."
            }
            $exitCode = ($stoppedProcesses | Select-Object -First 1).Process.ExitCode
            break
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($entry in $processes) {
        $process = $entry.Process
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Write-Host "Stopping $($entry.Name) ..."
                Stop-ProcessTree -ProcessId $process.Id
            }
        }
    }
}

exit $exitCode
