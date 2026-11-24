[CmdletBinding()]
param([ValidateSet('Start','Stop')][string]$Action='Start',
      [ValidateSet('All','Backend','AI')][string]$Target='All', [switch]$NoOpen)
. (Join-Path $PSScriptRoot 'common.ps1')
$failures = New-Object System.Collections.Generic.List[string]
# Backend remains independently usable even if AI installation/startup fails.
if ($Target -in @('All','Backend')) {
    $arguments=@('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $root 'Server/scripts/local_server.ps1'),'-Action',$Action,'-Target','Backend')
    if ($NoOpen) { $arguments += '-NoOpen' }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) { $failures.Add('Backend command failed.') }
}
if ($Target -in @('All','AI')) {
    try {
        if ($Action -eq 'Start' -and (Test-Path -LiteralPath (Join-Path $root '.runtime/local-services.json'))) {
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'native-ai.ps1')
            if ($LASTEXITCODE -ne 0) { throw 'Existing AI launch failed.' }
        } elseif ($Action -eq 'Start' -and (Test-Path -LiteralPath (Join-Path $root '.runtime/portable/enabled'))) {
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'Server/portable/runtime.ps1') -Action Start -Target AI -NoOpen
            if ($LASTEXITCODE -ne 0) { throw 'Existing portable AI launch failed.' }
        } elseif ($Action -eq 'Stop' -and -not (Test-Path -LiteralPath (Join-Path $state 'compose.env'))) {
            Write-Host 'No team AI installation to stop.'
        } elseif ($Action -eq 'Start' -and -not (Test-Path -LiteralPath (Join-Path $state 'enabled'))) {
            throw 'Run Start-HealthMon.cmd menu 5 once, then menu 3. Backend operation is independent.'
        } else {
            $docker = Get-HealthMonDocker
            $compose = Get-TeamCompose
            if ($Action -eq 'Start') {
                Wait-HealthMonDocker $docker
                # No dependency downloads on start; only menu 5 installs files.
                $selection = & $docker run --rm --pull never --network none --mount ('type=bind,src=' + $root + ',dst=/app') healthmon-team-setup:local available
                if ($LASTEXITCODE -ne 0) { throw 'Installed model inspection failed. Run menu 5.' }
                $selection = ($selection | Out-String) | ConvertFrom-Json
                Write-Host 'SKIP dialogue / evolution: optional models and their runtime are not installed.'
                foreach ($item in $selection.skipped.PSObject.Properties) { Write-Host ('SKIP ' + $item.Name + ': ' + $item.Value) }
                foreach ($service in $selection.ready) {
                    try { Invoke-TeamDocker ($compose + @('up','-d','--no-build','--pull','never','--wait','--wait-timeout','180',$service)); Write-Host ($service + ' ready.') }
                    catch { $failures.Add($service + ' could not start: ' + $_.Exception.Message) }
                }
            } else {
                Invoke-TeamDocker ($compose + @('stop','food','pose'))
                Write-Host 'Food and Pose AI stopped. Models and game records are retained.'
            }
        }
    } catch { $failures.Add($_.Exception.Message) }
    if ($Action -eq 'Stop') {
        # Also retire any earlier native/full-AI processes, without dropping data.
        $legacy = if (Test-Path -LiteralPath (Join-Path $root '.runtime/portable/enabled')) {
            Join-Path $root 'Server/portable/runtime.ps1'
        } else { Join-Path $root 'Server/scripts/local_server.ps1' }
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $legacy -Action Stop -Target AI -NoOpen
        if ($LASTEXITCODE -ne 0) { $failures.Add('Previous AI shutdown could not be confirmed.') }
    }
}
if ($failures.Count) { Write-Host ($failures -join ' | ') -ForegroundColor Red; exit 1 }
exit 0
