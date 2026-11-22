param()
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$manifest=Join-Path $root '.runtime/python-environments.json'
if (!(Test-Path -LiteralPath $manifest)) { throw 'Project-local Python runtime manifest is missing.' }
foreach($entry in (Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json)) {
    $runtimeHome=Join-Path $root $entry.python_home
    $config=Join-Path (Join-Path $root $entry.environment) 'pyvenv.cfg'
    if (!(Test-Path -LiteralPath (Join-Path $runtimeHome 'python.exe'))) { throw "Missing bundled runtime: $runtimeHome" }
    $text=[IO.File]::ReadAllText($config)
    $text=[regex]::Replace($text,'(?m)^home\s*=.*$',('home = '+$runtimeHome))
    [IO.File]::WriteAllText($config,$text,(New-Object Text.UTF8Encoding($false)))
}
$env:HF_HOME=Join-Path $root '.runtime/cache/huggingface'
$env:TORCH_HOME=Join-Path $root '.runtime/cache/torch'
$env:PIP_CACHE_DIR=Join-Path $root '.runtime/cache/pip'
