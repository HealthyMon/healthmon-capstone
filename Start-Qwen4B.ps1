param([switch]$LlmOnly)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Server/scripts/project_runtime.ps1')
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.runtime/qwen4b-venv/Scripts/python.exe'
$runtime = Join-Path $PSScriptRoot '.runtime/qwen4b-live'
if (!(Test-Path "$runtime/gateway.json")) { throw 'Run Server/scripts/connect_qwen4b_local.py to configure this checkout first.' }
if (!(Test-Path -LiteralPath $python)) { throw "Qwen4B Python environment not found: $python" }
$config = Get-Content -LiteralPath "$runtime/gateway.json" -Raw | ConvertFrom-Json
if (!(Test-Path -LiteralPath (Join-Path $config.adapter_path 'adapter_model.safetensors'))) {
    throw 'The trained Qwen4B LoRA checkpoint is missing. Restore the adapter backup or retrain before starting dialogue. See Ai/LLM/docs/RECOVERY_20261120_KO.md.'
}
$listener = Get-NetTCPConnection -LocalPort 18091 -State Listen -ErrorAction SilentlyContinue
if (!$listener) {
    $process = Start-Process -FilePath $python -ArgumentList '-B','-m','Server.local_probe.gpu_gateway','--config','.runtime/qwen4b-live/gateway.json' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$runtime/gateway.stdout.log" -RedirectStandardError "$runtime/gateway.stderr.log" -PassThru
    $process.Id | Set-Content "$runtime/gateway.pid"
}
Write-Host 'Waiting for the Qwen4B dialogue server...'
$deadline = [DateTime]::UtcNow.AddMinutes(3)
$ready = $false
do {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18091/health' -TimeoutSec 2
        $ready = $health.ready -eq $true -and $health.model.model_id -eq 'Qwen/Qwen3.5-4B'
    } catch { $ready = $false }
    if ($ready) { break }
    if ($process) {
        $process.Refresh()
        if ($process.HasExited) { throw "Qwen4B exited during startup. Inspect $runtime/gateway.stderr.log." }
    }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)
if (!$ready) { throw "Qwen4B did not become ready. Inspect $runtime/gateway.stderr.log (port 18091)." }
Write-Host 'Qwen4B dialogue server is ready on port 18091.'
if (!$LlmOnly) {
    docker compose up -d db api
    if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed.' }
}
