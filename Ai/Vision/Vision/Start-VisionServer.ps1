param([int]$Port = 8000, [string]$Device = 'cuda:0')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../../Server/scripts/project_runtime.ps1')
$env:VISION_DEVICE = $Device
Set-Location -LiteralPath $PSScriptRoot
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m uvicorn unity_api:app --host 0.0.0.0 --port $Port --workers 1
if ($LASTEXITCODE -ne 0) { throw 'Vision server failed' }
