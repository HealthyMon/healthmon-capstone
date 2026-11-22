[CmdletBinding()]
param([ValidateSet('Start','Stop')][string]$Action='Start',
      [ValidateSet('All','Backend','AI')][string]$Target='All', [switch]$NoOpen)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$command=Get-Command docker.exe -ErrorAction SilentlyContinue
$docker=if ($command) { $command.Source } else { Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin/docker.exe' }
$compose=@('compose','--project-directory',$root)
$backendEnv=Join-Path $root '.env'
if (Test-Path -LiteralPath $backendEnv) { $compose+=@('--env-file',$backendEnv) }
$paths=Join-Path $root '.runtime/portable/model-paths.env'
if (Test-Path -LiteralPath $paths) { $compose+=@('--env-file',$paths) }
$compose+=@('-f',(Join-Path $root 'compose.ai.yaml'))
function Invoke-AI([string[]]$Arguments) {
    & $docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'AI container command failed. Inspect docker compose -f compose.ai.yaml logs --tail 80.' }
}
$stopErrors = New-Object System.Collections.Generic.List[string]
if ($Target -in @('AI','All') -and $Action -eq 'Stop') {
    try {
        $running = & $docker @compose ps --status running -q ai
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the AI container.' }
        if ($running) {
            Invoke-AI @('exec','-T','ai','/opt/healthmon-envs/control/bin/python','-B','-m','Server.portable.bootstrap','stop')
            Write-Host 'AI shutdown requested. An active evolution finishes, then the AI container exits.'
        }
    } catch {
        $stopErrors.Add($_.Exception.Message)
    }
}
if ($Target -in @('Backend','All')) {
    $arguments=@('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $root 'Server/scripts/local_server.ps1'),'-Action',$Action,'-Target','Backend')
    if ($NoOpen) { $arguments+='-NoOpen' }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        if ($Action -eq 'Stop') { $stopErrors.Add('Backend command failed.') }
        else { throw 'Backend command failed.' }
    }
}
if ($stopErrors.Count) { throw ($stopErrors -join ' | ') }
if ($Target -in @('AI','All') -and $Action -eq 'Start') {
    Invoke-AI @('up','-d','--wait','--wait-timeout','600','ai')
    Write-Host 'AI container ready. Dialogue pauses during evolution; CPU food and Pose services stay available.'
}
