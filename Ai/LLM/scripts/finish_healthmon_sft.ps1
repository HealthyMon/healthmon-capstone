$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $root 'Server/scripts/project_runtime.ps1')
Set-Location $root
$python = Join-Path $root '.runtime/qwen4b-venv/Scripts/python.exe'
$run = 'Ai/LLM/runs/qwen4b-healthmon-sft-v1'
for ($attempt=0; $attempt -lt 30 -and !(Test-Path "$run/pid"); $attempt++) { Start-Sleep -Seconds 2 }
$trainProcessId = [int](Get-Content "$run/pid")
Wait-Process -Id $trainProcessId -ErrorAction SilentlyContinue
if (!(Test-Path "$run/selection.json")) { throw 'Training incomplete; no model promotion.' }
$job = Start-Process -FilePath $python -ArgumentList '-X','utf8','-B','Ai/LLM/scripts/evaluate_healthmon_sft.py','--output',"$run/final-evaluation" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput '.runtime/qwen4b-live/healthmon-sft-evaluation.log' -RedirectStandardError '.runtime/qwen4b-live/healthmon-sft-evaluation.stderr.log' -Wait -PassThru
if ($job.ExitCode -ne 0) { throw 'Evaluation failed; no model promotion.' }
Write-Output 'Training and final evaluation finished; awaiting semantic review.'
