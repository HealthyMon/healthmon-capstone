$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $root 'Server/scripts/project_runtime.ps1')
Set-Location $root
$python=Join-Path $root '.runtime/qwen4b-venv/Scripts/python.exe'
$run='Ai/LLM/runs/qwen4b-axis-priority-v1'
for ($attempt=0; $attempt -lt 30 -and !(Test-Path "$run/pid"); $attempt++) { Start-Sleep -Seconds 2 }
$trainProcessId=[int](Get-Content "$run/pid")
Wait-Process -Id $trainProcessId -ErrorAction SilentlyContinue
if (Test-Path "$run/selection.json") {
    & $python -X utf8 Ai/LLM/scripts/promote_axis_priority.py
    if ($LASTEXITCODE -ne 0) { throw 'Promotion failed; previous configuration retained where not updated.' }
} else { Write-Warning 'Training incomplete; restarting the previous selected model.' }
$gpu=Start-Process -FilePath $python -ArgumentList '-B','-m','Server.local_probe.gpu_gateway','--config','.runtime/qwen4b-live/gateway.json' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput '.runtime/qwen4b-live/gateway.stdout.log' -RedirectStandardError '.runtime/qwen4b-live/gateway.stderr.log' -PassThru
$gpu.Id | Set-Content '.runtime/qwen4b-live/gateway.pid'
Write-Output 'GPU server startup requested. No dialogue comparison or validation performed.'
