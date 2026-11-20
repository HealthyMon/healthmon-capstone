param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [string]$OutputPath,
    [string]$Device = 'cuda:0',
    [ValidateSet('food2k','aihub')][string]$Classifier = 'food2k',
    [ValidateSet('auto','csv','imagefolder','numeric')][string]$ClassOrder = 'auto',
    [ValidateSet('fpb','legacy','none')][string]$WeightBackend = 'fpb'
)
$ErrorActionPreference = 'Stop'
$foodPython = Join-Path $PSScriptRoot '.venv-aihub\Scripts\python.exe'
$foodModel = Join-Path $PSScriptRoot 'runs\food_regions_pilot\food_regions.pth'
$foodSelection = Join-Path $PSScriptRoot 'active_region.json'
if (Test-Path -LiteralPath $foodSelection) {
    $foodModel = (Get-Content -LiteralPath $foodSelection -Raw -Encoding utf8 | ConvertFrom-Json).path
}
if (-not [IO.Path]::IsPathRooted($foodModel)) { $foodModel = Join-Path $PSScriptRoot $foodModel }
$foodEntry = Join-Path $PSScriptRoot 'aihub\detect.py'
if (-not (Test-Path -LiteralPath $ImagePath -PathType Leaf)) { throw 'Image file not found' }
if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot ('outputs\meal_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
}
& $foodPython $foodEntry $ImagePath --regions $foodModel --device $Device --output $OutputPath --classifier $Classifier --class-order $ClassOrder --weight-backend $WeightBackend
if ($LASTEXITCODE -ne 0) { throw 'Food inference failed; see error above' }
Write-Host "Saved annotated.jpg, overview.jpg (Food2K), result.json and food crops in: $OutputPath"
