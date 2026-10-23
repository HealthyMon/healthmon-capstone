param(
    [string]$RuntimeRoot='E:/qwen-llm/healthmon-generation3d/Ai/Generation3D',
    [string]$Python='E:/qwen-llm/.venv/Scripts/python.exe'
)
$ErrorActionPreference='Stop'
$tls=Join-Path $RuntimeRoot 'outputs/unity_service/tls'
if (-not (Test-Path -LiteralPath (Join-Path $tls 'localhost.crt'))) { throw 'Run setup_tls.ps1 first, then copy its public certificate pin to Unity Resources/HealthMonEvolution.json.' }
& $Python (Join-Path $PSScriptRoot 'service.py') --runtime-root $RuntimeRoot --ssl-certfile (Join-Path $tls 'localhost.crt') --ssl-keyfile (Join-Path $tls 'localhost.key')
