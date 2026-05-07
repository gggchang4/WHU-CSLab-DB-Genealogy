$manageScript = (Resolve-Path (Join-Path $PSScriptRoot "manage.ps1")).Path
& $manageScript prepare_coursework_artifacts --create-smoke-data @args
exit $LASTEXITCODE
