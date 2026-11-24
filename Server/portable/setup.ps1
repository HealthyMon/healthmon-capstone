[CmdletBinding()]
param([string]$BundlePath, [switch]$SkipDownloads, [switch]$SkipGenerationBuild, [switch]$NoActivate)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $PSScriptRoot 'docker-prerequisites.ps1')
$docker = Get-HealthMonDocker
function Invoke-Docker([string[]]$Arguments) {
    & $docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Installation stopped: docker ' + ($Arguments -join ' ')) }
}
Push-Location $root
try {
    Wait-HealthMonDocker $docker
    # Existing native installs have live journals/assets. Preserve their launcher
    # until migration is explicitly validated; fresh clones enable Docker AI.
    $existingNative = (Test-Path -LiteralPath (Join-Path $root '.runtime/native-server.json')) -or
        (Test-Path -LiteralPath (Join-Path $root '.runtime/local-services.json'))
    $activate = (-not $NoActivate) -and (-not $existingNative)
    # Advanced full AI installation only; the root menu uses Server/team/setup.ps1.
    $bundle = $null
    if (-not $SkipDownloads -and -not $BundlePath) { throw 'Full AI installation requires -BundlePath. For team testing, use Start-HealthMon.cmd menu 5.' }
    if ($BundlePath -and -not $SkipDownloads) {
        if (-not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) { throw 'The selected offline bundle does not exist.' }
        $bundle = Get-Item -LiteralPath $BundlePath
    }
    $backendWasRunning = $false
    if ($activate -and (Test-Path -LiteralPath (Join-Path $root '.env'))) {
        $running = & $docker compose --project-directory $root --env-file (Join-Path $root '.env') ps --status running -q api
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the existing backend before first-time AI setup.' }
        $backendWasRunning = [bool]$running
    }
    Invoke-Docker @('build','-f','Server/portable/Dockerfile.setup','-t','healthmon-setup:local','Server/portable')
    $mount = 'type=bind,src=' + $root + ',dst=/app'
    if (-not $SkipDownloads) {
        $arguments = @('run','--rm','--mount',$mount)
        if ($bundle) { $arguments += @('--mount',('type=bind,src=' + $bundle.DirectoryName + ',dst=/input,readonly')) }
        if ($env:HF_TOKEN) { $arguments += @('--env','HF_TOKEN') }
        $arguments += @('healthmon-setup:local','assets')
        if ($bundle) { $arguments += @('--bundle',('/input/' + $bundle.Name)) }
        Invoke-Docker $arguments
    }
    if (-not $SkipGenerationBuild) {
        Invoke-Docker @('run','--rm','--mount',$mount,'--entrypoint','python','healthmon-setup:local','Ai/Generation3D/migration/tools/fetch_sources.py')
        $architecture = '8.6'
        $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
        if ($smi) {
            $detected = @(& $smi.Source --query-gpu=compute_cap --format=csv,noheader)
            if ($LASTEXITCODE -eq 0 -and $detected.Count -eq 1 -and $detected[0].Trim() -match '^\d+\.\d+$') { $architecture = $detected[0].Trim() }
        }
        Invoke-Docker @('build','--build-arg',('TARGET_CUDA_ARCHS=' + $architecture),'-t','healthmon-3d:3090','Ai/Generation3D')
    }
    Invoke-Docker @('build','-f','Ai/Generation3D/Dockerfile.evolution2511','-t','healthmon-evolution-2511:local','Ai/Generation3D')
    Invoke-Docker @('build','-f','Server/portable/Dockerfile','-t','healthmon-ai:local','.')
    # Credentials and saved pets are retained. This action does not start servers.
    if ($activate) {
        Invoke-Docker @('run','--rm','--network','none','--mount',$mount,'healthmon-setup:local','connection')
        Invoke-Docker @('compose','build','api')
        Invoke-Docker @('compose','pull','db')
    }
    $state = Join-Path $root '.runtime/portable'
    New-Item -ItemType Directory -Force -Path $state | Out-Null
    $status = @{environment_prepared=$true; inference_verified=$false; activated=$activate} | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $state 'installation.json'),$status)
    if ($activate) { [IO.File]::WriteAllText((Join-Path $state 'enabled'),'portable-v1') }
    if ($backendWasRunning) {
        Write-Host 'Applying the new AI connection to the already running backend. Saved game data is retained.'
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'Server/scripts/local_server.ps1') -Action Start -Target Backend -NoOpen
        if ($LASTEXITCODE -ne 0) { throw 'AI setup finished, but backend connection refresh failed. Retry Start option 2.' }
    }
    if ($existingNative) { Write-Host 'Existing native settings and game records preserved. Docker AI is prepared but not activated; validate migration before switching.' }
    Write-Host 'Environment prepared. No AI inference or game test was run. Start-HealthMon: 1 All / 2 Backend / 3 AI.'
} finally { Pop-Location }
