$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $root 'Server/scripts/project_runtime.ps1')
Set-Location $root
$python = Join-Path $root '.runtime/qwen4b-venv/Scripts/python.exe'
$run = 'Ai/LLM/runs/qwen4b-natural-v2'
& $python -B Ai/LLM/scripts/train_qwen4b.py --data Ai/LLM/data/qwen4b_natural_v1 --run $run --init-adapter Ai/LLM/runs/qwen4b-common-v1/checkpoint-epoch-2 --epochs 2 --lr 0.00003 --final-only-validation *> .runtime/qwen4b-live/natural-training-v2.log
if ($LASTEXITCODE -ne 0) { throw 'Natural dialogue training failed; old adapter remains selected.' }
& $python -B Ai/LLM/scripts/evaluate_qwen4b_natural.py --adapter "$run/checkpoint-epoch-2" --output "$run/final-dialogue-evaluation.json" *> .runtime/qwen4b-live/natural-evaluation-v2.log
if ($LASTEXITCODE -ne 0) { throw 'Final dialogue evaluation failed; old adapter remains selected.' }
'Awaiting semantic review before activation' | Set-Content "$run/review-ready.txt"
