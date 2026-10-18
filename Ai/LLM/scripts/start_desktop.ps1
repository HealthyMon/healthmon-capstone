param([string]$RuntimeRoot = 'E:\qwen-llm')
$ErrorActionPreference = 'Stop'
$llmRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $RuntimeRoot '.env'
$model = Join-Path $RuntimeRoot 'models\qwen3.5-9b'
$embedding = Join-Path $RuntimeRoot 'models\bge-m3'
$serving = Get-Content (Join-Path $llmRoot 'config\serving.json') -Raw | ConvertFrom-Json
$adapter = Join-Path $RuntimeRoot $serving.adapter_path
$existingHealth = $null
try { $existingHealth = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3 } catch { }
if ($null -ne $existingHealth) {
    if (!$existingHealth.loaded -or $existingHealth.backend -ne 'qwen3.5-9b-bf16-lora' -or
        [IO.Path]::GetFullPath($existingHealth.adapter) -ne [IO.Path]::GetFullPath($adapter)) {
        throw 'Port 8000 already has a different server. Inspect it before starting another GPU process.'
    }
    Write-Output 'The selected Qwen + LoRA API is already running at http://127.0.0.1:8000.'
    return
}
foreach ($required in @($python, $envFile, "$model\config.json", "$embedding\config.json", "$adapter\adapter_config.json", "$RuntimeRoot\runtime\pgdata\PG_VERSION")) {
    if (!(Test-Path -LiteralPath $required)) { throw "Required existing resource missing: $required" }
}
$pgCtl = Join-Path $RuntimeRoot 'runtime\pgsql\bin\pg_ctl.exe'
& $pgCtl -D "$RuntimeRoot\runtime\pgdata" status
if ($LASTEXITCODE -ne 0) {
    & $pgCtl -D "$RuntimeRoot\runtime\pgdata" -l "$RuntimeRoot\runs\postgres.log" -o '-h 127.0.0.1 -p 55432' -w start
    if ($LASTEXITCODE -ne 0) { throw 'Existing PostgreSQL could not start; no database was initialized.' }
}
$env:PYTHONUTF8 = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
Push-Location $llmRoot
try {
    & $python scripts/serve.py --env-file $envFile --model-path $model --embedding-path $embedding --adapter $adapter --warmup
    if ($LASTEXITCODE -ne 0) { throw "API exited with code $LASTEXITCODE" }
} finally { Pop-Location }
