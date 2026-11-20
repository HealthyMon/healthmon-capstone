param([int]$Port = 8001, [string]$Device = 'cuda:0')
$ErrorActionPreference = 'Stop'
$env:VISION_DEVICE = $Device
Set-Location -LiteralPath $PSScriptRoot
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m uvicorn unity_api:app --host 0.0.0.0 --port $Port --workers 1
if ($LASTEXITCODE -ne 0) { throw 'Vision server failed' }
