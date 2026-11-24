param(
    [ValidateSet('connect','disconnect','status')][string]$Action='connect',
    [string]$Serial,
    [string]$AdbPath,
    [string]$PackageName,
    [switch]$Auto
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $AdbPath) {
    $candidates=@(
        (Join-Path "$env:LOCALAPPDATA" 'Android\Sdk\platform-tools\adb.exe'),
        "$env:ANDROID_HOME\platform-tools\adb.exe",
        "$env:ANDROID_SDK_ROOT\platform-tools\adb.exe"
    )
    $command=Get-Command adb -ErrorAction SilentlyContinue
    if ($command) { $candidates+= $command.Source }
    $editors=Join-Path $env:ProgramFiles 'Unity/Hub/Editor'
    if (Test-Path -LiteralPath $editors) {
        Get-ChildItem -LiteralPath $editors -Directory | ForEach-Object {
            $candidates+=Join-Path $_.FullName 'Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools/adb.exe'
        }
    }
    $AdbPath=$candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
# Menu 1/2/3 only reuses an existing Android debugging session. Initial
# Android connection is explicit in menu 4; PC startup never creates a daemon.
if ($Auto) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $pending = $client.ConnectAsync('127.0.0.1',5037)
        if (-not $pending.Wait(500) -or -not $client.Connected) { exit 0 }
    } catch { exit 0 }
    finally { $client.Dispose() }
}
if (-not $AdbPath) {
    if ($Auto) { exit 0 }
    throw 'Android SDK platform-tools/adb.exe is required. Pass -AdbPath with its location.'
}
# Device discovery is optional during PC startup. A stuck ADB daemon must not
# hold the backend/AI menu open indefinitely. Stop only this discovery client.
$probe = New-Object Diagnostics.Process
$probe.StartInfo.FileName = $AdbPath
$probe.StartInfo.Arguments = 'devices'
$probe.StartInfo.UseShellExecute = $false
$probe.StartInfo.CreateNoWindow = $true
$probe.StartInfo.RedirectStandardOutput = $true
$probe.StartInfo.RedirectStandardError = $true
try {
    [void]$probe.Start()
    $output = $probe.StandardOutput.ReadToEndAsync()
    $errors = $probe.StandardError.ReadToEndAsync()
    if (-not $probe.WaitForExit(8000)) {
        $probe.Kill()
        if ($Auto) { Write-Warning 'Android discovery timed out. PC services remain ready; retry menu 4 later.'; exit 0 }
        throw 'Android device discovery timed out. Retry after checking the USB connection.'
    }
    if ($probe.ExitCode -ne 0) { throw 'adb could not inspect connected devices.' }
    if (-not $output.Wait(1000)) {
        if ($Auto) { Write-Warning 'Android discovery did not finish. PC services remain ready; retry menu 4 later.'; exit 0 }
        throw 'Android discovery output timed out.'
    }
    $lines = $output.GetAwaiter().GetResult() -split "`r?`n"
} finally { $probe.Dispose() }
$devices=@($lines | Select-String '^([^\s]+)\s+(device|unauthorized|offline)$' | ForEach-Object {
    [pscustomobject]@{serial=$_.Matches[0].Groups[1].Value;state=$_.Matches[0].Groups[2].Value}
})
if ($Serial) { $devices=@($devices | Where-Object { $_.serial -eq $Serial }) }
if ($devices.Count -eq 0 -and $Auto) { exit 0 }
if ($devices.Count -eq 0) { throw 'Connect USB, enable USB debugging and approve this PC on the phone.' }
if ($devices.Count -ne 1) {
    if ($Auto) { Write-Warning 'Multiple Android devices found; use menu 4 with -Serial to choose one.'; exit 0 }
    throw 'Multiple devices found. Pass -Serial DEVICE_ID to select one.'
}
if ($devices[0].state -ne 'device') {
    if ($Auto) { Write-Warning 'Approve USB debugging on the phone, then retry menu 4.'; exit 0 }
    throw 'Unlock the phone and approve this PC for USB debugging, then retry.'
}
$Serial=$devices[0].serial
if ($Serial -notmatch '^[a-zA-Z0-9_.:-]+$') { throw 'Unsupported Android device identifier.' }
$mapping=@(& $AdbPath -s $Serial reverse --list)
if ($LASTEXITCODE -ne 0) { throw 'Could not read reverse connections.' }
if ($Action -eq 'status') { Write-Output $mapping; exit 0 }

$connection=$null
$profilePath=Join-Path $root '.runtime/client-connection.json'
if (Test-Path -LiteralPath $profilePath) {
    $connection=Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $base=[Uri]$connection.api_base_url
    if ($connection.schema_version -ne 1 -or $connection.environment -ne 'test' -or -not $base.IsLoopback -or
        $base.Scheme -notin @('http','https') -or $base.UserInfo -or $base.Query -or $base.Fragment -or
        -not $connection.bearer_token -or -not $connection.server_instance_id -or -not $connection.owner_id) {
        throw 'Invalid local client connection profile. Start the backend again to regenerate it.'
    }
}
$ports=@(@{phone=18095;hostPort=18095})
if ($connection) { $ports+=@{phone=18092;hostPort=$base.Port} }
elseif ($Action -eq 'disconnect') { $ports+=@{phone=18092;hostPort=18092} }
# Check every requested mapping before changing any existing mapping.
foreach ($port in $ports) {
    $existing=@($mapping | Where-Object { $_ -match ('\s+tcp:'+$port.phone+'\s+') })
    if ($existing.Count -gt 0 -and $existing[0] -notmatch ('\s+tcp:'+$port.phone+'\s+tcp:'+$port.hostPort+'\s*$')) {
        throw ('Phone port '+$port.phone+' is already mapped elsewhere. Existing mapping preserved.')
    }
}
foreach ($port in $ports) {
    $existing=@($mapping | Where-Object { $_ -match ('\s+tcp:'+$port.phone+'\s+') })
    if ($Action -eq 'disconnect' -and $existing.Count -gt 0) {
        & $AdbPath -s $Serial reverse --remove ('tcp:'+$port.phone)
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove the USB connection.' }
    } elseif ($Action -eq 'connect' -and $existing.Count -eq 0) {
        & $AdbPath -s $Serial reverse --no-rebind ('tcp:'+$port.phone) ('tcp:'+$port.hostPort)
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the USB connection.' }
    }
}
if ($Action -eq 'disconnect') { Write-Output 'HealthMon backend/Pose USB connections removed. Saved game data retained.'; exit 0 }
$verified=@(& $AdbPath -s $Serial reverse --list)
if ($LASTEXITCODE -ne 0) { throw 'Could not verify the USB connection.' }
foreach ($port in $ports) {
    if (-not ($verified -match ('\s+tcp:'+$port.phone+'\s+tcp:'+$port.hostPort+'\s*$'))) { throw 'USB connection verification failed.' }
}
if (-not $connection) { Write-Warning 'Pose USB is ready. Start backend (menu 2) to prepare game auto-connect.'; exit 0 }

function Write-PrivateConnection([string]$Package, [string]$Payload) {
    if ($Package -notmatch '^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$') { throw 'Invalid application package name.' }
    # Credentials travel on stdin into app-private storage, never command arguments.
    $remote="run-as $Package sh -c 'umask 077; mkdir -p files; cat > files/healthmon-connection.json.tmp && mv files/healthmon-connection.json.tmp files/healthmon-connection.json'"
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$AdbPath
    $info.Arguments="-s $Serial shell -T `"$remote`""
    $info.UseShellExecute=$false; $info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process
    $process.StartInfo=$info
    try {
        [void]$process.Start()
        $bytes=[Text.Encoding]::UTF8.GetBytes($Payload)
        $process.StandardInput.BaseStream.Write($bytes,0,$bytes.Length)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000)) { $process.Kill(); $process.WaitForExit(); return $false }
        return $process.ExitCode -eq 0
    } catch { return $false }
    finally { $process.Dispose() }
}
$connection.api_base_url=$base.Scheme+'://127.0.0.1:18092'+$base.AbsolutePath.TrimEnd('/')
$payload=$connection | ConvertTo-Json -Compress
$packages=if ($PackageName) { @($PackageName) } else { @('com.healthmon.capstone.posepreview','com.healthmon.capstone') }
foreach ($package in $packages) {
    if (Write-PrivateConnection $package $payload) {
        Write-Output ('Android auto-connect ready for '+$package+'. Open the game; no address or token entry is needed.')
        exit 0
    }
}
Write-Warning 'USB ports are ready. Install the updated development APK, then use menu 4 to provision its private connection. Release APKs require normal account login.'
if (-not $Auto) { exit 1 }
