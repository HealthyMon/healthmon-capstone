param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$visionRoot = Join-Path $projectRoot 'Ai\Vision\Vision'
$python = Join-Path $visionRoot '.venv\Scripts\python.exe'
$logRoot = Join-Path $projectRoot '.runtime\food-gateway'
$healthUrl = "http://127.0.0.1:$Port/health"
function Test-FoodReady {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return ($health.status -eq 'ok' -and $health.service -eq 'healthmon-multifood')
    } catch { return $false }
}
try {
    if (Test-FoodReady) { Write-Host "Food AI already ready: $healthUrl"; exit 0 }
    if (-not (Test-Path -LiteralPath $python)) { throw "Food AI Python not found: $python" }
    if (-not (Test-Path -LiteralPath (Join-Path $visionRoot 'unity_api.py'))) { throw 'Food AI source is missing.' }
    [IO.Directory]::CreateDirectory($logRoot) | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $errorLog = Join-Path $logRoot "food-$stamp-error.log"
    $process = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','unity_api:app','--host','0.0.0.0','--port',"$Port",'--workers','1') -WorkingDirectory $visionRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "food-$stamp-out.log") -RedirectStandardError $errorLog
    $deadline = (Get-Date).AddSeconds(45)
    do {
        if (Test-FoodReady) {
            Write-Host "Food AI ready: $healthUrl"
            Write-Host "Food AI runs in the background. Logs: $logRoot"
            exit 0
        }
        $process.Refresh()
        if ($process.HasExited) { throw "Food AI exited. Check $errorLog" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Food AI did not become ready within 45 seconds. Check $errorLog"
} catch {
    Write-Host ('Food AI could not start: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
