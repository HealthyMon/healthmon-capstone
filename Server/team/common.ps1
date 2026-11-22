$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$state = Join-Path $root '.runtime/team'
. (Join-Path $root 'Server/portable/docker-prerequisites.ps1')
function Invoke-TeamDocker([string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    & $docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Docker command failed: ' + ($Arguments -join ' ')) }
}
function Get-TeamCompose {
    return @('compose','--project-directory',$root,'--env-file',(Join-Path $state 'compose.env'),'-f',(Join-Path $root 'compose.team.yaml'))
}
function Set-TeamIdentity {
    [IO.Directory]::CreateDirectory($state) | Out-Null
    $identity = Join-Path $state 'compose.env'
    if (-not (Test-Path -LiteralPath $identity)) {
        $stream = [IO.File]::Open($identity,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $bytes = [Text.Encoding]::ASCII.GetBytes(('HEALTHMON_TEAM_PROJECT=healthmon-team-' + [guid]::NewGuid().ToString('N').Substring(0,12) + "`n"))
            $stream.Write($bytes,0,$bytes.Length)
        } finally { $stream.Dispose() }
    }
}
