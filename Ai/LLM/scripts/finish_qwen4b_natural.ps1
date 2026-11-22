$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $root 'Server/scripts/project_runtime.ps1')
Set-Location $root
$python = Join-Path $root '.runtime/qwen4b-venv/Scripts/python.exe'
$run = 'Ai/LLM/runs/qwen4b-natural-v1'
for ($attempt = 0; $attempt -lt 30 -and !(Test-Path "$run/pid"); $attempt++) { Start-Sleep -Seconds 2 }
$trainProcessId = [int](Get-Content "$run/pid")
Wait-Process -Id $trainProcessId -ErrorAction SilentlyContinue
if (!(Test-Path "$run/selection.json")) { throw 'Training did not complete; existing adapter remains selected.' }
$evaluation = Start-Process -FilePath $python -ArgumentList '-B','Ai/LLM/scripts/evaluate_qwen4b_natural.py','--adapter',"$run/checkpoint-epoch-2",'--output',"$run/final-generation.json" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput '.runtime/qwen4b-live/natural-evaluation.log' -RedirectStandardError '.runtime/qwen4b-live/natural-evaluation.stderr.log' -Wait -PassThru
if ($evaluation.ExitCode -ne 0) { throw 'Final evaluation failed; existing adapter remains selected.' }
Write-Output 'Final generation complete; ready for semantic review and model replacement.'
