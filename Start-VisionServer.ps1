param([int]$Port=8001,[string]$Device='cuda:0')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Server/scripts/project_runtime.ps1')
& (Join-Path $PSScriptRoot 'Ai/Vision/Vision/Start-VisionServer.ps1') -Port $Port -Device $Device
