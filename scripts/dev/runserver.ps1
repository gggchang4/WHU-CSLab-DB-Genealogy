param(
    [string]$AddrPort = "127.0.0.1:8000"
)

$manageScript = (Resolve-Path (Join-Path $PSScriptRoot "manage.ps1")).Path
& $manageScript runserver $AddrPort
exit $LASTEXITCODE
