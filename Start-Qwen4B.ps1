param([switch]$LlmOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path (Split-Path $PSScriptRoot -Parent) '.runtime/qwen4b-venv/Scripts/python.exe'
$runtime = Join-Path $PSScriptRoot '.runtime/qwen4b-live'
if (!(Test-Path "$runtime/gateway.json")) { throw 'Run Server/scripts/connect_qwen4b_local.py to configure this checkout first.' }
if (!(Test-Path -LiteralPath $python)) { throw "Qwen4B Python environment not found: $python" }
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
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)
if (!$ready) { throw "Qwen4B did not become ready. Inspect $runtime/gateway.stderr.log (port 18091)." }
Write-Host 'Qwen4B dialogue server is ready on port 18091.'
if (!$LlmOnly) {
    docker compose up -d db api
    if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed.' }
}
