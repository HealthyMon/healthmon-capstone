$ErrorActionPreference = 'Stop'
& python "$PSScriptRoot/manage.py" @args
exit $LASTEXITCODE
