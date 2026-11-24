# Shared by first-use installation; no system-wide changes are made.
function Get-HealthMonDocker {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in @((Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin/docker.exe'),
                        (Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'))) {
        if (Test-Path -LiteralPath $path) { return $path }
    }
    throw 'Docker Desktop is required once. Install it from https://docs.docker.com/desktop/setup/install/windows-install/ and finish WSL2 setup, then run Start again. Python and Git LFS are not required on the host.'
}
function Get-HealthMonDockerEngine([string]$Docker) {
    $probe = New-Object Diagnostics.Process
    $probe.StartInfo.FileName = $Docker
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
function Wait-HealthMonDocker([string]$Docker) {
    $engine = Get-HealthMonDockerEngine $Docker
    if ($engine -eq 'linux') { return }
    if ($engine -eq 'windows') { throw 'Switch Docker Desktop to Linux containers, then run Start again.' }
    $desktop = Join-Path ([IO.Path]::GetFullPath((Join-Path (Split-Path $Docker -Parent) '../..'))) 'Docker Desktop.exe'
    if (Test-Path -LiteralPath $desktop) { Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null }
    Write-Host 'Waiting for Docker Desktop. Finish any WSL2 or first-run prompts in Docker Desktop.'
    $deadline = [DateTime]::UtcNow.AddMinutes(3)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 3
        $engine = Get-HealthMonDockerEngine $Docker
        if ($engine -eq 'linux') { return }
        if ($engine -eq 'windows') { throw 'Switch Docker Desktop to Linux containers, then run Start again.' }
    }
    throw 'Docker Desktop is not ready. Finish WSL2 setup and restart Windows if requested, then run Start again.'
}
