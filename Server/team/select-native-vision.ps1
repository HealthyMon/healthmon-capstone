[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$servicesPath = Join-Path $projectRoot '.runtime/local-services.json'
if (-not (Test-Path -LiteralPath $servicesPath)) { return }
$services = Get-Content -LiteralPath $servicesPath -Raw | ConvertFrom-Json
$privatePath = $services.vision_config
if (-not $privatePath) { throw 'Existing AI configuration has no food configuration path.' }
if (-not [IO.Path]::IsPathRooted($privatePath)) { $privatePath = Join-Path $projectRoot $privatePath }
$privatePath = [IO.Path]::GetFullPath($privatePath)
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.runtime')) + [IO.Path]::DirectorySeparatorChar
if (-not $privatePath.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Food configuration must stay inside this checkout runtime.'
}
$private = Get-Content -LiteralPath $privatePath -Raw | ConvertFrom-Json
if ($private.environment -ne 'test' -or -not $private.server_token) { throw 'Existing food service is not a configured local test service.' }
$python = $services.python
if (-not [IO.Path]::IsPathRooted($python)) { $python = Join-Path $projectRoot $python }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing control Python is unavailable.' }
$assets = Join-Path $projectRoot 'Ai/Vision/multifood'
if (-not (Test-Path -LiteralPath (Join-Path $assets 'models/classifier.pkl'))) { throw 'Run menu 5 to install the new food model first.' }
if ($private.vision_backend -eq 'multifood' -and $private.vision_container -eq $true -and $private.vision_assets -eq $assets) {
    Write-Host 'Native food service already selects the isolated multi-food runtime.'
    return
}
Copy-Item -LiteralPath $privatePath -Destination ($privatePath + '.before-multifood-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))
foreach ($item in @{vision_backend='multifood';vision_container=$true;vision_assets=$assets;vision_python=$python}.GetEnumerator()) {
    $private | Add-Member -NotePropertyName $item.Key -NotePropertyValue $item.Value -Force
}
[IO.File]::WriteAllText($privatePath, ($private | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
Write-Host 'Native food service now uses the isolated CPU multi-food image. Other AI settings were retained.'
