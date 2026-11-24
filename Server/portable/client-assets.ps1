[CmdletBinding()]
param([string]$DockerPath)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'lfs-assets.json') -Raw | ConvertFrom-Json
$needed = $false
foreach ($asset in $manifest.files) {
    if ($asset.group -ne 'client') { continue }
    $path = Join-Path $root $asset.path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $needed = $true; break }
    if ((Get-Item -LiteralPath $path).Length -le 1024 -and
        [IO.File]::ReadAllText($path).StartsWith('version https://git-lfs.github.com/spec/v1')) {
        $needed = $true; break
    }
}
if (-not $needed) { exit 0 }
. (Join-Path $PSScriptRoot 'docker-prerequisites.ps1')
if (-not $DockerPath) { $DockerPath = Get-HealthMonDocker; Wait-HealthMonDocker $DockerPath }
Write-Host 'Restoring Unity assets missing from the source ZIP. AI models are not downloaded by backend-only startup.'
& $DockerPath build -f (Join-Path $root 'Server/team/Dockerfile.setup') -t healthmon-team-setup:local (Join-Path $root 'Server/team')
if ($LASTEXITCODE -ne 0) { throw 'Asset setup image build failed.' }
& $DockerPath run --rm --mount ('type=bind,src=' + $root + ',dst=/app') healthmon-team-setup:local client-assets
if ($LASTEXITCODE -ne 0) { throw 'Unity asset download failed. Run Start again to resume.' }
