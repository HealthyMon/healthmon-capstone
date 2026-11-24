[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')
Set-Location -LiteralPath $root
$config = Join-Path $root '.runtime/local-services.json'
$settings = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
$visionPath = $settings.vision_config
if ($visionPath -and -not [IO.Path]::IsPathRooted($visionPath)) { $visionPath = Join-Path $root $visionPath }
if ($visionPath -and (Test-Path -LiteralPath $visionPath)) {
    $visionSettings = Get-Content -LiteralPath $visionPath -Raw | ConvertFrom-Json
    if ($visionSettings.vision_backend -eq 'multifood' -and $visionSettings.vision_container -eq $true) {
        try {
            $docker = Get-HealthMonDocker
            Wait-HealthMonDocker $docker
        } catch {
            Write-Warning 'Food Docker runtime is unavailable. Other installed AI services will still be checked.'
        }
    }
}
$python = if ([IO.Path]::IsPathRooted($settings.python)) { $settings.python } else { Join-Path $root $settings.python }
& $python -B -m Server.local_probe.local_services check --config $config --available-only
if ($LASTEXITCODE -ne 0) { throw 'Local AI configuration could not be read.' }
$statusPath = Join-Path $root '.runtime/local-services-status.json'
$status = if (Test-Path -LiteralPath $statusPath) { Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json } else { $null }
if ($status -and ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$status.updated_at) -lt 15 -and $status.phase -in @('ready','generating_3d','starting','degraded')) {
    Write-Host 'Existing AI services are already running.'
    exit 0
}
$started = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$process = Start-Process -FilePath $python -ArgumentList '-B -m Server.local_probe.local_services run --config .runtime/local-services.json --available-only' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root '.runtime/available-ai.stdout.log') -RedirectStandardError (Join-Path $root '.runtime/available-ai.stderr.log')
$deadline = [DateTime]::UtcNow.AddSeconds(330)
while ([DateTime]::UtcNow -lt $deadline) {
    if ($process.HasExited) { throw 'AI supervisor exited; inspect .runtime/available-ai.stderr.log.' }
    if (Test-Path -LiteralPath $statusPath) {
        $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ([double]$status.updated_at -ge $started) {
            if ($status.phase -in @('ready','generating_3d')) {
                foreach ($item in $status.skipped.PSObject.Properties) { Write-Host ('SKIP ' + $item.Name + ': ' + $item.Value) }
                if ($status.failed -and @($status.failed.PSObject.Properties).Count -gt 0) {
                    foreach ($item in $status.failed.PSObject.Properties) { Write-Host ('FAILED ' + $item.Name + ': ' + $item.Value) -ForegroundColor Red }
                    Write-Host 'Other ready AI services remain running.'
                    exit 1
                }
                Write-Host 'Installed AI services are ready. Missing models were skipped; nothing was downloaded.'
                exit 0
            }
            if ($status.phase -eq 'failed') { throw 'AI supervisor failed; inspect .runtime/available-ai.stderr.log.' }
        }
    }
    Start-Sleep -Seconds 2
}
throw 'AI readiness timed out; inspect .runtime/local-services-status.json.'
