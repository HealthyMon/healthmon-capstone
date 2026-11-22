param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$EnvFile,
    [Parameter(Mandatory=$true)][string]$EmbeddingPath,
    [string]$Run = 'runs/qwen4b-common-v1'
)
$ErrorActionPreference = 'Stop'
$llmRoot = Split-Path $PSScriptRoot -Parent
$runPath = if ([IO.Path]::IsPathRooted($Run)) { $Run } else { Join-Path $llmRoot $Run }
$selection = Get-Content -LiteralPath (Join-Path $runPath 'selection.json') -Raw | ConvertFrom-Json
if ($selection.trained -ne $true) { throw 'The selected run has not completed training.' }
$adapter = $selection.selected.path
if (-not (Test-Path -LiteralPath (Join-Path $adapter 'adapter_model.safetensors'))) { throw 'Selected LoRA weights are missing.' }
& $Python (Join-Path $PSScriptRoot 'serve.py') --env-file $EnvFile `
    --model-path (Join-Path $llmRoot 'models/qwen3.5-4b') --quantization nf4 `
    --adapter $adapter --embedding-path $EmbeddingPath
exit $LASTEXITCODE
