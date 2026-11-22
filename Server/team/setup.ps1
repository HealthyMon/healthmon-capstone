[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')
$docker = Get-HealthMonDocker
Wait-HealthMonDocker $docker
Set-TeamIdentity
$compose = Get-TeamCompose
$mount = 'type=bind,src=' + $root + ',dst=/app'
Write-Host 'Preparing backend, food and pose environments. No dialogue/evolution models or Hugging Face login.'
Invoke-TeamDocker @('build','-f',(Join-Path $PSScriptRoot 'Dockerfile.setup'),'-t','healthmon-team-setup:local',$PSScriptRoot)
Invoke-TeamDocker @('run','--rm','--mount',$mount,'healthmon-team-setup:local','assets')
Invoke-TeamDocker ($compose + @('build','food','pose'))
$nativePath = Join-Path $root '.runtime/native-server.json'
if (Test-Path -LiteralPath $nativePath) {
    $native = Get-Content -LiteralPath $nativePath -Raw | ConvertFrom-Json
    $apiPath = if ([IO.Path]::IsPathRooted($native.api_env)) { $native.api_env } else { Join-Path $root $native.api_env }
    $api = Get-Content -LiteralPath $apiPath -Raw | ConvertFrom-Json
    if ($api.APP_ENV -ne 'test' -or $api.AI_MODE -ne 'remote' -or
        $api.AI_BASE_URL.TrimEnd('/') -notin @('http://127.0.0.1:18090','http://localhost:18090') -or -not $api.AI_SERVER_TOKEN) {
        throw 'Existing native backend connection differs. It was preserved; no setup success was recorded.'
    }
    [IO.File]::WriteAllText((Join-Path $state 'server-token'), $api.AI_SERVER_TOKEN, (New-Object Text.UTF8Encoding($false)))
    Invoke-TeamDocker @('run','--rm','--network','none','--mount',$mount,'healthmon-team-setup:local','connection','--native')
    Write-Host 'Reusing the existing native backend environment and database.'
} else {
    Invoke-TeamDocker @('run','--rm','--network','none','--mount',$mount,'healthmon-team-setup:local','connection')
    $backend = @('compose','--project-directory',$root,'--env-file',(Join-Path $root '.env'),'-f',(Join-Path $root 'compose.yaml'))
    Invoke-TeamDocker ($backend + @('build','api'))
    Invoke-TeamDocker ($backend + @('pull','db'))
}
[IO.File]::WriteAllText((Join-Path $state 'enabled'),'food-pose-v1')
Write-Host 'Setup complete. 2 = Backend, 3 = All installed AI (skip missing), 1 = Both. No servers were started.'
