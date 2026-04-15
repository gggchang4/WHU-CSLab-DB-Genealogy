$manageScript = (Resolve-Path (Join-Path $PSScriptRoot "manage.ps1")).Path
& $manageScript test apps.accounts apps.genealogy
exit $LASTEXITCODE
