param(
    [ValidateSet('connect','disconnect','status')][string]$Action='connect',
    [string]$Serial,
    [string]$AdbPath
)
$ErrorActionPreference='Stop'
if (-not $AdbPath) {
    $candidates=@(
        (Join-Path "$env:LOCALAPPDATA" 'Android\Sdk\platform-tools\adb.exe'),
        "$env:ANDROID_HOME\platform-tools\adb.exe",
        "$env:ANDROID_SDK_ROOT\platform-tools\adb.exe"
    )
    $command=Get-Command adb -ErrorAction SilentlyContinue
    if ($command) { $candidates+= $command.Source }
    $AdbPath=$candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $AdbPath) { throw 'Android SDK platform-tools/adb.exe is required. Pass -AdbPath with its location.' }
$lines=& $AdbPath devices
if ($LASTEXITCODE -ne 0) { throw 'adb could not inspect connected devices.' }
$devices=@($lines | Select-String '^([^\s]+)\s+(device|unauthorized|offline)$' | ForEach-Object {
    [pscustomobject]@{serial=$_.Matches[0].Groups[1].Value;state=$_.Matches[0].Groups[2].Value}
})
if ($Serial) { $devices=@($devices | Where-Object { $_.serial -eq $Serial }) }
if ($devices.Count -eq 0) { throw 'No Android device found. Connect USB, enable USB debugging and approve this PC on the phone.' }
if ($devices.Count -ne 1) { throw 'Multiple devices found. Pass -Serial DEVICE_ID to select one.' }
if ($devices[0].state -ne 'device') { throw 'Unlock the phone and approve this PC for USB debugging, then retry.' }
$Serial=$devices[0].serial
$mapping=@(& $AdbPath -s $Serial reverse --list)
if ($LASTEXITCODE -ne 0) { throw 'Could not read reverse connections.' }
$poseMapping=@($mapping | Where-Object { $_ -match '\s+tcp:18095\s+' })
if ($poseMapping.Count -gt 0 -and $poseMapping[0] -notmatch '\s+tcp:18095\s+tcp:18095\s*$') {
    throw 'Phone port 18095 is already mapped elsewhere. Existing mapping was preserved.'
}
if ($Action -eq 'status') { Write-Output $mapping; exit 0 }
if ($Action -eq 'disconnect') {
    if ($poseMapping.Count -gt 0) {
        & $AdbPath -s $Serial reverse --remove tcp:18095
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove pose reverse connection.' }
    }
    Write-Output 'Pose USB connection removed. Use Stop-AI.cmd to stop all AI services.'
    exit 0
}
if ($poseMapping.Count -eq 0) {
    & $AdbPath -s $Serial reverse --no-rebind tcp:18095 tcp:18095
    if ($LASTEXITCODE -ne 0) { throw 'Could not create pose USB connection.' }
}
$verified=@(& $AdbPath -s $Serial reverse --list)
if ($LASTEXITCODE -ne 0 -or -not ($verified -match '\s+tcp:18095\s+tcp:18095\s*$')) { throw 'USB connection verification failed.' }
Write-Output 'Android USB mapping ready. Start all AI with Start-AI.cmd, then use Exercise -> Prepare -> Start in HealthMon.'
Write-Output 'Reconnect after unplugging/rebooting. Use Stop-AI.cmd for all AI; game backend remains separate.'
