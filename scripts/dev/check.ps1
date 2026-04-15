$manageScript = (Resolve-Path (Join-Path $PSScriptRoot "manage.ps1")).Path
& $manageScript check
exit $LASTEXITCODE
