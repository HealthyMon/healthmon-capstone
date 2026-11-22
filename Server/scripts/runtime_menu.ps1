# Root launchers share this menu; services remain independently controllable.
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop')][string]$Action = 'Start',
    [ValidateSet('All', 'Backend', 'AI', 'Android', 'Setup')][string]$Target,
    [string]$Serial,
    [string]$AdbPath,
    [string]$BundlePath,
    [switch]$NoPause,
    [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$resultCode = 0
try {
    if (-not $Target) {
        Write-Host ''
        Write-Host ('HealthMon - ' + $Action)
        Write-Host '  1. All (Backend + AI)'
        Write-Host '  2. Backend only (API + database)'
        Write-Host '  3. AI only (Dialogue + Food + Evolution + Pose)'
        Write-Host ('  4. Android USB - ' + $(if ($Action -eq 'Start') { 'connect' } else { 'disconnect' }))
        if ($Action -eq 'Start') { Write-Host '  5. First-time setup (all AI environments + models)' }
        Write-Host '  0. Exit'
        while (-not $Target) {
            $choice = Read-Host 'Select [1]'
            switch ($choice) {
                ''  { $Target = 'All' }
                '1' { $Target = 'All' }
                '2' { $Target = 'Backend' }
                '3' { $Target = 'AI' }
                '4' { $Target = 'Android' }
                '5' { if ($Action -eq 'Start') { $Target = 'Setup' } else { Write-Host 'Choose 0-4.' } }
                '0' { exit 0 }
                default { Write-Host 'Invalid selection.' }
            }
        }
    }
    $commandArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File')
    switch ($Target) {
        'Android' {
            $commandArgs += @((Join-Path $ProjectRoot 'Ai/Pose/android-device.ps1'), '-Action',
                $(if ($Action -eq 'Start') { 'connect' } else { 'disconnect' }))
            if ($Serial) { $commandArgs += @('-Serial', $Serial) }
            if ($AdbPath) { $commandArgs += @('-AdbPath', $AdbPath) }
        }
        'Setup' {
            if ($Action -ne 'Start') { throw 'Setup is available from Start-HealthMon.cmd only.' }
            $commandArgs += @((Join-Path $ProjectRoot 'Server/portable/setup.ps1'))
            if ($BundlePath) { $commandArgs += @('-BundlePath', $BundlePath) }
        }
        default {
            $launcher = if (Test-Path -LiteralPath (Join-Path $ProjectRoot '.runtime/portable/enabled')) {
                Join-Path $ProjectRoot 'Server/portable/runtime.ps1'
            } else { Join-Path $PSScriptRoot 'local_server.ps1' }
            $commandArgs += @($launcher, '-Action', $Action, '-Target', $Target)
            if ($NoOpen -or $Action -eq 'Start') { $commandArgs += '-NoOpen' }
        }
    }
    & powershell.exe @commandArgs
    $resultCode = $LASTEXITCODE
    if ($resultCode -eq 0 -and $Action -eq 'Start' -and $Target -in @('All','Backend','AI')) {
        # Optional USB handoff: absence of a phone must never block the PC game.
        $usbArgs = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',
            (Join-Path $ProjectRoot 'Ai/Pose/android-device.ps1'),'-Action','connect','-Auto')
        if ($Serial) { $usbArgs += @('-Serial',$Serial) }
        if ($AdbPath) { $usbArgs += @('-AdbPath',$AdbPath) }
        & powershell.exe @usbArgs
        if ($LASTEXITCODE -ne 0) { Write-Warning 'PC services are ready. Android USB setup can be retried with menu 4.' }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $resultCode = 1
}
if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
exit $resultCode
