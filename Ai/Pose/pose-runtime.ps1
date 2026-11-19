param([ValidateSet('setup','start','stop','status')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtimeRoot = Join-Path $repoRoot '.runtime'
$pythonPath = Join-Path $runtimeRoot 'pose-venv\Scripts\python.exe'
$statePath = Join-Path $runtimeRoot 'pose-process.json'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Get-OwnedPoseProcess {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $processes = @()
    $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        $ticks = if ($state.started_ticks) { [long]$state.started_ticks } else { ([datetime]$state.started).ToUniversalTime().Ticks }
        if ($process.Path -ne $pythonPath -or $process.StartTime.ToUniversalTime().Ticks -ne $ticks) {
            throw 'Pose process ownership does not match; refusing to stop an unrelated process.'
        }
        $processes += $process
        # Windows venv python.exe is a redirector; its interpreter is a child.
        foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id)")) {
            if ($child.CommandLine -match '(?:^|\s)-m\s+Ai\.Pose\.unity_service(?:\s|$)') {
                $worker = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
                if ($null -ne $worker) { $processes += $worker }
            }
        }
    }
    if ($state.worker_pid -and $state.worker_pid -notin $processes.Id) {
        $worker = Get-Process -Id $state.worker_pid -ErrorAction SilentlyContinue
        if ($null -ne $worker) {
            if ($worker.Path -ne $state.worker_path -or $worker.StartTime.ToUniversalTime().Ticks -ne [long]$state.worker_started_ticks) {
                throw 'Pose worker ownership does not match.'
            }
            $processes += $worker
        }
    }
    return $processes
}

if ($Action -eq 'setup') {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & py -3.12 -m venv (Join-Path $runtimeRoot 'pose-venv')
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 for Windows first.' }
    }
    & $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-windows.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Pose package installation failed.' }
    & $pythonPath (Join-Path $PSScriptRoot 'mac-exercise-counter\scripts\download_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Pose model verification failed.' }
    Write-Output 'HealthMon Pose setup complete.'
    exit 0
}

$owned = Get-OwnedPoseProcess
if ($Action -eq 'stop') {
    foreach ($process in @($owned | Sort-Object StartTime -Descending)) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        $process.WaitForExit(10000) | Out-Null
    }
    if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath }
    Write-Output 'HealthMon Pose stopped.'
    exit 0
}
if ($Action -eq 'status') {
    if ($null -eq $owned) { Write-Output 'HealthMon Pose stopped.'; exit 0 }
    Invoke-RestMethod -Uri 'http://127.0.0.1:18095/health' -TimeoutSec 2 | ConvertTo-Json -Compress
    exit 0
}
if ($null -ne $owned) { Write-Output 'HealthMon Pose is already running.'; exit 0 }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run Start-HealthMon.cmd -Target Setup first.' }
$listener = Get-NetTCPConnection -LocalPort 18095 -State Listen -ErrorAction SilentlyContinue
if ($null -ne $listener) { throw 'Port 18095 is already occupied. No existing process was stopped.' }
$process = Start-Process -FilePath $pythonPath -ArgumentList '-m Ai.Pose.unity_service' -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'pose.stdout.log') -RedirectStandardError (Join-Path $runtimeRoot 'pose.stderr.log')
$processState = @{pid=$process.Id; started_ticks=$process.StartTime.ToUniversalTime().Ticks.ToString()}
$processState | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
for ($attempt=0; $attempt -lt 40; $attempt++) {
    if ($process.HasExited) { throw 'Pose service failed. See .runtime/pose.stderr.log.' }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18095/health' -TimeoutSec 1
        if ($health.service -eq 'healthmon-pose') {
            $listener = Get-NetTCPConnection -LocalPort 18095 -State Listen -ErrorAction Stop | Select-Object -First 1
            $worker = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
            $workerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($worker.Id)"
            if ($worker.Id -ne $process.Id -and $workerInfo.ParentProcessId -ne $process.Id) { throw 'Unexpected port owner' }
            $processState.worker_pid=$worker.Id; $processState.worker_started_ticks=$worker.StartTime.ToUniversalTime().Ticks.ToString(); $processState.worker_path=$worker.Path
            $processState | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
            Write-Output 'HealthMon Pose ready at http://127.0.0.1:18095'; exit 0
        }
    } catch { }
    Start-Sleep -Milliseconds 250
}
throw 'Pose startup timed out. See .runtime/pose.stderr.log.'
