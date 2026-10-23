# Windows PowerShell 5.1: no host Python installation is required.
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop')][string]$Action = 'Start',
    [ValidateRange(1024, 65535)][int]$Port = 18092,
    [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$DockerInstallUrl = 'https://docs.docker.com/desktop/setup/install/windows-install/'
$Utf8 = New-Object Text.UTF8Encoding($false)

function New-LocalSecret {
    $bytes = New-Object byte[] 36
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Initialize-LocalEnvironment {
    $path = Join-Path $ProjectRoot '.env'
    if (Test-Path -LiteralPath $path) { return }
    $tokens = [ordered]@{}
    $tokens[(New-LocalSecret)] = 'dev-test-a'
    $tokens[(New-LocalSecret)] = 'dev-test-b'
    $values = [ordered]@{
        COMPOSE_PROJECT_NAME = ('healthmon-' + [guid]::NewGuid().ToString('N').Substring(0, 12))
        API_BIND = '127.0.0.1'; API_PORT = [string]$Port; PUBLIC_BASE_URL = "http://localhost:$Port"
        POSTGRES_PASSWORD = (New-LocalSecret); POSTGRES_DB = 'healthmon'; APP_ENV = 'test'
        AI_MODE = 'disabled'; AI_BASE_URL = ''; AI_SERVER_TOKEN = ''; AI_TIMEOUT_SECONDS = '30'
        AI_CONTRACT_VERSION = 'healthmon.ai.v1'; ALLOW_HTTP_AI = 'false'
        DEV_TOKENS = ($tokens | ConvertTo-Json -Compress); AUTH_TOKEN_HASHES = '{}'
        TEST_OWNERS = '["dev-test-a","dev-test-b"]'; SERVER_INSTANCE_ID = [guid]::NewGuid().ToString()
        EMBEDDING_MODEL_ID = 'BAAI/bge-m3'; EMBEDDING_MODEL_VERSION = '1'; WORKER_ENABLED = 'true'
    }
    $content = (($values.GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value }) -join "`n") + "`n"
    # CreateNew also protects a concurrent first launch from replacing credentials.
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $bytes = $Utf8.GetBytes($content); $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
    Write-Host 'Created this PC''s test settings. Existing settings and saved pets are kept on later starts.'
}

function Invoke-Compose {
    param([string[]]$Arguments, [switch]$Capture)
    # Native stderr must remain visible without PowerShell 5.1 treating progress as a terminating error.
    $ErrorActionPreference = 'Continue'
    if ($Capture) { $output = & $script:Docker compose --project-directory $ProjectRoot --env-file (Join-Path $ProjectRoot '.env') @Arguments 2>&1 }
    else { & $script:Docker compose --project-directory $ProjectRoot --env-file (Join-Path $ProjectRoot '.env') @Arguments }
    if ($LASTEXITCODE -ne 0) {
        if ($Capture) { throw ('Docker Compose failed: ' + ($Arguments -join ' ') + '. Check Docker Desktop and the project .env.') }
        throw ('Docker Compose failed: ' + ($Arguments -join ' '))
    }
    if ($Capture) { return ($output | Out-String) }
}

function Get-LocalAIConfiguration {
    $directory = Join-Path $ProjectRoot '.runtime'
    $path = Join-Path $directory 'local-services.json'
    if (Test-Path -LiteralPath $path) { return $path }
    # Reuse an already prepared local installation. Machine paths and secrets
    # remain ignored; fresh PCs can supply the documented example configuration.
    $llm = Join-Path $directory 'local-gpu-probe/base-only/private-base.json'
    $vision = Join-Path $directory 'local-vision-probe/private.json'
    $priorEvolution = Join-Path $directory 'evolution-stage-matrix.json'
    $gpu = @((Join-Path $ProjectRoot '.venv/Scripts/python.exe'),
             (Join-Path $ProjectRoot '../.venv-healthmon-v2/Scripts/python.exe'),
             (Join-Path $ProjectRoot '../.venv/Scripts/python.exe')) |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $gpu) { return $null }
    $cpu = [IO.Path]::GetFullPath($gpu)
    foreach ($required in @($llm, $vision, $priorEvolution)) {
        if (-not (Test-Path -LiteralPath $required)) { return $null }
    }
    $evolutionPath = Join-Path $directory 'local-evolution.json'
    if (-not (Test-Path -LiteralPath $evolutionPath)) {
        $prior = Get-Content -LiteralPath $priorEvolution -Raw | ConvertFrom-Json
        $evolution = [ordered]@{work_root=(Join-Path $directory 'local-evolution'); model_root=$prior.model_root; vendor_root=$prior.vendor_root}
        [IO.File]::WriteAllText($evolutionPath, ($evolution | ConvertTo-Json), $Utf8)
    }
    $value = [ordered]@{python=$cpu; llm_python=([IO.Path]::GetFullPath($gpu)); llm_config=$llm; vision_config=$vision; evolution_config=$evolutionPath}
    [IO.File]::WriteAllText($path, ($value | ConvertTo-Json), $Utf8)
    return $path
}

function Start-LocalAI {
    param($Configuration)
    $path = Get-LocalAIConfiguration
    if (-not $path) {
        $environment = $Configuration.services.api.environment
        if ($environment.AI_MODE -ne 'remote' -or -not $environment.AI_BASE_URL) {
            throw 'AI is not configured. Prepare .runtime/local-services.json using Server/local_probe/local-services.example.json, or set a shared AI Gateway in .env. See Server/local_probe/README.md. No AI-ready result was reported.'
        }
        $probeUrl = ([string]$environment.AI_BASE_URL).Replace('host.docker.internal', '127.0.0.1').TrimEnd('/') + '/health'
        $null = Invoke-RestMethod -Uri $probeUrl -TimeoutSec 10
        Write-Host 'Configured remote AI Gateway is reachable.'
        return
    }
    $local = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $python = if ([IO.Path]::IsPathRooted($local.python)) { $local.python } else { [IO.Path]::GetFullPath((Join-Path $ProjectRoot $local.python)) }
    Write-Host 'Checking local dialogue, food analysis and 3D prerequisites...'
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $python -B -m Server.local_probe.local_services configure --config '.runtime/local-services.json'
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedPreference
    if ($code -ne 0) { throw 'Local AI prerequisites failed. See the message above; model files and their environments must be installed on this PC.' }
    $directory = Join-Path $ProjectRoot '.runtime'
    $statusPath = Join-Path $directory 'local-services-status.json'
    $running = $false
    if (Test-Path -LiteralPath $statusPath) {
        $previous = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        $running = (([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$previous.updated_at) -lt 15) -and
            $previous.phase -notin @('stopped','failed') -and (Get-Process -Id $previous.pid -ErrorAction SilentlyContinue)
    }
    if (-not $running) {
        $null = Start-Process -FilePath $python -ArgumentList @('-B','-m','Server.local_probe.local_services','run','--config','.runtime/local-services.json') -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $directory 'local-services.stdout.log') -RedirectStandardError (Join-Path $directory 'local-services.stderr.log') -PassThru
    }
    Write-Host 'Starting dialogue, food analysis, 3D Gateway and automatic generation worker. Model loading can take a few minutes...'
    $deadline = [DateTime]::UtcNow.AddMinutes(6)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $statusPath) {
            $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
            $fresh = ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$status.updated_at) -lt 15
            if ($fresh -and $status.phase -eq 'ready') { Write-Host 'All local AI services are ready.'; return }
            if ($fresh -and $status.phase -eq 'generating_3d') { Write-Host 'Local AI is running; a requested 3D generation currently owns the GPU.'; return }
            if ($fresh -and $status.phase -eq 'failed') { throw ('Local AI failed: ' + $status.message) }
        }
        Start-Sleep -Seconds 2
    }
    throw 'Local AI did not become ready. Inspect .runtime/local-services.stderr.log and local-*.stderr.log.'
}

function Stop-LocalAI {
    $path = Join-Path $ProjectRoot '.runtime/local-services.json'
    if (-not (Test-Path -LiteralPath $path)) { return }
    [IO.File]::WriteAllText((Join-Path $ProjectRoot '.runtime/local-services.stop'), '', $Utf8)
    Write-Host 'Local AI shutdown requested. An active 3D generation finishes before shutdown.'
}

function Get-DockerEngine {
    # A stalled WSL engine can also stall docker.exe; bound each probe itself.
    $probe = New-Object Diagnostics.Process
    $probe.StartInfo.FileName = $script:Docker
    $probe.StartInfo.Arguments = 'info --format "{{.OSType}}"'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    try {
        $probe.Start() | Out-Null
        $output = $probe.StandardOutput.ReadToEndAsync()
        $errors = $probe.StandardError.ReadToEndAsync()
        if (-not $probe.WaitForExit(5000)) { $probe.Kill(); return '' }
        if ($probe.ExitCode -eq 0) { return $output.GetAwaiter().GetResult().Trim() }
        return ''
    } finally { $probe.Dispose() }
}

function Wait-LocalDocker {
    $engine = Get-DockerEngine
    if ($engine -eq 'linux') { return }
    if ($engine -eq 'windows') { throw 'In Docker Desktop, switch to Linux containers and run Start-HealthMon.cmd again.' }
    $desktop = @(
        (Join-Path ([IO.Path]::GetFullPath((Join-Path (Split-Path $script:Docker -Parent) '../..'))) 'Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($desktop) {
        Write-Host 'Starting Docker Desktop. Waiting for the Linux engine...'
        Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
    } else { throw 'Open Docker Desktop, then run Start-HealthMon.cmd again.' }
    $deadline = [DateTime]::UtcNow.AddMinutes(3)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 3
        $engine = Get-DockerEngine
        if ($engine -eq 'linux') { return }
        if ($engine -eq 'windows') { throw 'Switch Docker Desktop to Linux containers, then retry.' }
    }
    throw 'Docker Desktop did not become ready. Finish its WSL/setup prompts and run Start-HealthMon.cmd again.'
}

function Write-ConnectionGuide {
    param($Configuration, [string]$BaseUrl, [object[]]$Pets)
    $environment = $Configuration.services.api.environment
    $cards = New-Object System.Collections.Generic.List[string]
    $tokens = $null
    if ($environment.DEV_TOKENS) { $tokens = $environment.DEV_TOKENS | ConvertFrom-Json }
    if ($tokens) {
        foreach ($entry in $tokens.PSObject.Properties) {
            $pet = $Pets | Where-Object { $_.owner -eq $entry.Value } | Select-Object -First 1
            if (-not $pet) { continue }
            $owner = [Net.WebUtility]::HtmlEncode([string]$entry.Value)
            $token = [Net.WebUtility]::HtmlEncode([string]$entry.Name)
            $petId = [Net.WebUtility]::HtmlEncode([string]$pet.pet_id)
            $cards.Add("<section><h2>$owner</h2><label>User bearer token<input readonly value='$token'></label><label>Pet ID<input readonly value='$petId'></label></section>")
        }
    }
    if ($cards.Count -eq 0) { $cards.Add('<p>DEV_TOKENS 설정에 대응하는 계정이 없습니다. 기존 서버의 발급 토큰을 사용하세요.</p>') }
    $safeUrl = [Net.WebUtility]::HtmlEncode($BaseUrl)
    $aiMode = [Net.WebUtility]::HtmlEncode([string]$environment.AI_MODE)
    $html = @"
<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HealthMon 서버 연결</title><style>
body{max-width:760px;margin:40px auto;padding:0 24px;font:17px/1.65 system-ui,sans-serif;background:#edf5fa;color:#193147}
h1{color:#087851}section{padding:16px 24px;background:white;border-radius:14px;margin:20px 0}label{display:block;margin:14px 0}
input{display:block;width:100%;box-sizing:border-box;padding:12px;border:1px solid #9bafbf;border-radius:8px;font:15px monospace;background:#f7fafc}
button{padding:8px 16px;margin-top:7px;cursor:pointer}small{display:block}code{background:white;padding:3px 7px}
</style><h1>서버가 켜졌어요</h1><p>Unity의 설정 → COMMON SERVER 패널에서 아래 주소와 같은 계정의 토큰·펫 ID를 넣고 <b>Connect / change connection</b>을 누르세요.</p>
<section><label>API_BASE_URL<input readonly value='$safeUrl'></label><a href='$safeUrl/health/ready' target='_blank'>서버 준비 상태 확인</a></section>
$($cards -join "`n")
<p>입력칸을 누르면 전체 선택됩니다. 복사 버튼 또는 Ctrl+C로 복사하세요.</p>
<p>이 PC의 서버 연결 정보입니다. 인증 토큰이 있으니 이 페이지 파일을 다른 사람에게 보내지 마세요.</p>
<p>다음에도 <code>Start-HealthMon.cmd</code>를 더블클릭하면 됩니다. 서버를 끄려면 <code>Stop-HealthMon.cmd</code>를 실행하세요. 펫과 기록은 유지됩니다.</p>
<small>AI 모드: $aiMode. disabled이면 기본 서버·DB·펫·규칙만 실행합니다. AI 대화·음식 분석·진화 생성은 별도 AI 서버 설정이 필요합니다.</small>
<script>document.querySelectorAll('input').forEach(input=>{input.onclick=()=>input.select();const b=document.createElement('button');b.textContent='복사';b.onclick=()=>{input.select();document.execCommand('copy');b.textContent='복사됨';};input.after(b);});</script></html>
"@
    $directory = Join-Path $ProjectRoot '.runtime'
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $path = Join-Path $directory 'local-server-connection.html'
    [IO.File]::WriteAllText($path, $html, $Utf8)
    Write-Host "Ready: $BaseUrl"
    Write-Host "Unity connection guide: $path"
    if (-not $NoOpen) { Start-Process -FilePath $path | Out-Null }
}

try {
    Set-Location -LiteralPath $ProjectRoot
    $nativeProfile = Join-Path $ProjectRoot '.runtime/native-server.json'
    if (Test-Path -LiteralPath $nativeProfile) {
        $native = Get-Content -LiteralPath $nativeProfile -Raw | ConvertFrom-Json
        $nativePython = if ([IO.Path]::IsPathRooted($native.python)) { $native.python } else { Join-Path $ProjectRoot $native.python }
        $nativeArguments = @('-B', '-m', 'Server.local_probe.native_runtime', $Action.ToLowerInvariant(), '--profile', $nativeProfile)
        if ($NoOpen) { $nativeArguments += '--no-open' }
        & $nativePython @nativeArguments
        exit $LASTEXITCODE
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'compose.yaml'))) { throw 'Run this launcher from the complete HealthMon project.' }
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    $script:Docker = if ($command) { $command.Source } else {
        @((Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'),
          (Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin/docker.exe')) |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $script:Docker) {
        if (-not $NoOpen) { Start-Process $DockerInstallUrl | Out-Null }
        throw 'Install Docker Desktop once (Windows x86_64 for Intel/AMD), finish its WSL setup, then double-click Start-HealthMon.cmd again. Python is not required.'
    }
    if ($Action -eq 'Stop') {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot '.env'))) { Write-Host 'This project has no local server to stop.'; exit 0 }
        Invoke-Compose -Arguments @('stop')
        Stop-LocalAI
        Write-Host 'Server stopped. Saved pets, records and credentials are kept.'
        exit 0
    }
    Wait-LocalDocker
    Initialize-LocalEnvironment
    $configuration = Invoke-Compose -Arguments @('config', '--format', 'json') -Capture | ConvertFrom-Json
    if ($configuration.services.api.environment.APP_ENV -eq 'production') { throw 'This launcher is for a local development/test server. Existing production settings were kept.' }
    Start-LocalAI -Configuration $configuration
    # Local AI setup supplies the shared server credential and Docker-to-host URL.
    $configuration = Invoke-Compose -Arguments @('config', '--format', 'json') -Capture | ConvertFrom-Json
    $apiPort = $configuration.services.api.ports | Where-Object { $_.target -eq 8000 } | Select-Object -First 1
    if (-not $apiPort -or -not $apiPort.published) { throw 'The API port is missing from compose.yaml/.env.' }
    $hostAddress = [string]$apiPort.host_ip
    if (-not $hostAddress -or $hostAddress -eq '0.0.0.0' -or $hostAddress -eq '::') { $hostAddress = '127.0.0.1' }
    elseif ($hostAddress.Contains(':')) { $hostAddress = '[' + $hostAddress + ']' }
    $baseUrl = 'http://' + $hostAddress + ':' + [string]$apiPort.published
    Write-Host 'Starting the local server. The first run downloads and builds images; later runs reuse them.'
    Invoke-Compose -Arguments @('up', '-d', '--build', '--wait', '--wait-timeout', '180', 'api')
    $ready = Invoke-RestMethod -Uri ($baseUrl + '/health/ready') -TimeoutSec 10
    if (-not $ready.ready) { throw 'The API did not report ready. Run docker compose logs --tail 80 api migrate to inspect startup.' }
    $seed = Invoke-Compose -Arguments @('exec', '-T', 'api', 'python', 'Server/scripts/manage.py', 'seed-in-container') -Capture
    $pets = @($seed -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json })
    Write-ConnectionGuide -Configuration $configuration -BaseUrl $baseUrl -Pets $pets
    exit 0
} catch {
    Write-Host ''
    Write-Host ('HealthMon could not start: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
