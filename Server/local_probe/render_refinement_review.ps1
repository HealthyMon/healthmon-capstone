param([Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference='Stop'
$repoRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$reportPath=[IO.Path]::GetFullPath($Report)
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $repoRoot '.runtime'))+[IO.Path]::DirectorySeparatorChar
if(-not $reportPath.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)){
 throw 'Review reports and images must stay under this checkout .runtime.'
}
$data=Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
$outputDirectory=[IO.Path]::GetDirectoryName($reportPath)
$renderedCandidates=[Collections.Generic.List[object]]::new()
$semanticLabel='semantic judgment pending'
$modelVersion=[string]$data.expected_identity.model_version
if(-not $modelVersion){$modelVersion=[string]$data.model.model_version}
if(-not $modelVersion){$modelVersion='existing model'}
if($data.semantic_quality_passed -eq $false){$semanticLabel='manual semantic FAIL'}
elseif($data.semantic_quality_passed -eq $true){$semanticLabel='manual semantic PASS'}
Add-Type -AssemblyName System.Drawing

# Select RectangleF overloads explicitly; PointF overloads ignore layout bounds.
$drawBounded=[Drawing.Graphics].GetMethod('DrawString',[type[]]@([string],[Drawing.Font],[Drawing.Brush],[Drawing.RectangleF],[Drawing.StringFormat]))
$measureBounded=[Drawing.Graphics].GetMethod('MeasureString',[type[]]@([string],[Drawing.Font],[Drawing.SizeF],[Drawing.StringFormat],[int].MakeByRefType(),[int].MakeByRefType()))
$format=[Drawing.StringFormat]::GenericDefault.Clone()
$format.FormatFlags=[Drawing.StringFormatFlags]::LineLimit
$format.Trimming=[Drawing.StringTrimming]::None

function Measure-ReviewText([Drawing.Graphics]$graphics,[string]$text,[Drawing.Font]$font,[single]$width){
 if([string]::IsNullOrEmpty($text)){return [pscustomobject]@{height=0;measured_height=0;characters_fitted=0;line_count=0}}
 $arguments=[object[]]@($text,$font,[Drawing.SizeF]::new($width,100000),$format,0,0)
 $size=$measureBounded.Invoke($graphics,$arguments)
 if([int]$arguments[4] -ne $text.Length){throw 'The complete text must fit in the measured layout.'}
 return [pscustomobject]@{height=([Math]::Ceiling($size.Height)+8);measured_height=$size.Height;characters_fitted=[int]$arguments[4];line_count=[int]$arguments[5]}
}

function Draw-ReviewText([Drawing.Graphics]$graphics,[string]$text,[Drawing.Font]$font,[Drawing.Brush]$brush,[Drawing.RectangleF]$rectangle){
 if([string]::IsNullOrEmpty($text)){return}
 $saved=$graphics.Save()
 try{
  $graphics.SetClip($rectangle)
  $null=$drawBounded.Invoke($graphics,[object[]]@($text,$font,$brush,$rectangle,$format))
 }finally{$graphics.Restore($saved)}
}

$font=[Drawing.Font]::new('Malgun Gothic',18)
$header=[Drawing.Font]::new('Malgun Gothic',19,[Drawing.FontStyle]::Bold)
$measureBitmap=[Drawing.Bitmap]::new(1,1)
$measureGraphics=[Drawing.Graphics]::FromImage($measureBitmap)
try{
 foreach($suite in @('neutral','native')){
  $rows=[Collections.Generic.List[object]]::new()
  $top=130
  foreach($case in @($data.cases | Where-Object {$_.suite -eq $suite})){
   $heading=$case.case_id+' | selected quality='+$case.automatic_quality.passed+' | selected='+$case.metrics.quality_refinement.selected_candidate
   $headingLayout=Measure-ReviewText $measureGraphics $heading $header 2230
   $columns=[Collections.Generic.List[object]]::new()
   foreach($candidatePhase in @('original','refined')){
    $left=35
    $candidate=@($case.model_candidates | Where-Object {$_.phase -eq 'original'} | Select-Object -First 1)
    if($candidatePhase -eq 'refined'){
     $left=1180
     $candidate=@($case.model_candidates | Where-Object {$_.candidate_sha256 -eq $case.metrics.quality_refinement.selected_candidate_sha256} | Select-Object -First 1)
    }
    if($candidate.Count -ne 1){throw 'The displayed candidate must resolve to a generated model candidate.'}
    $speech=[string]$candidate[0].result.speech
    $codes=[string]::Join(', ',@($candidate[0].quality.failures))
    if(-not $candidate[0].contract_valid){$codes='REJECTED: invalid contract or changed classification'}
    $speechLayout=Measure-ReviewText $measureGraphics $speech $font 1070
    $codesLayout=Measure-ReviewText $measureGraphics $codes $font 1070
    $columns.Add([pscustomobject]@{phase=$candidatePhase;left=$left;candidate=$candidate[0];speech=$speech;codes=$codes;speech_layout=$speechLayout;codes_layout=$codesLayout})
   }
   $speechHeight=($columns | ForEach-Object {$_.speech_layout.height} | Measure-Object -Maximum).Maximum
   $codesHeight=($columns | ForEach-Object {$_.codes_layout.height} | Measure-Object -Maximum).Maximum
   $speechTop=$top+16+$headingLayout.height+12
   $codesTop=$speechTop+$speechHeight+16
   $rowHeight=[Math]::Max(160,($codesTop+$codesHeight+20-$top))
   $rows.Add([pscustomobject]@{case=$case;top=$top;height=$rowHeight;heading=$heading;heading_layout=$headingLayout;speech_top=$speechTop;codes_top=$codesTop;columns=$columns})
   $top+=$rowHeight+16
  }
  $canvasHeight=[int][Math]::Ceiling([Math]::Max(350,$top+20))
  $bitmap=[Drawing.Bitmap]::new(2300,$canvasHeight)
  $graphics=[Drawing.Graphics]::FromImage($bitmap)
  try{
   $graphics.Clear([Drawing.Color]::White)
   Draw-ReviewText $graphics ('Real '+$modelVersion+' refinement review - '+$suite+' - '+$semanticLabel) $header ([Drawing.Brushes]::Navy) ([Drawing.RectangleF]::new(25,20,2250,40))
   Draw-ReviewText $graphics 'Original model candidate' $header ([Drawing.Brushes]::Navy) ([Drawing.RectangleF]::new(35,65,1070,55))
   Draw-ReviewText $graphics 'Actual selected model candidate (original or refined)' $header ([Drawing.Brushes]::Navy) ([Drawing.RectangleF]::new(1180,65,1070,55))
   foreach($row in $rows){
    $graphics.FillRectangle([Drawing.Brushes]::AliceBlue,20,$row.top,2260,$row.height)
    Draw-ReviewText $graphics $row.heading $header ([Drawing.Brushes]::Navy) ([Drawing.RectangleF]::new(35,($row.top+16),2230,$row.heading_layout.height))
    foreach($column in $row.columns){
     $speechRect=[Drawing.RectangleF]::new($column.left,$row.speech_top,1070,$column.speech_layout.height)
     $codesRect=[Drawing.RectangleF]::new($column.left,$row.codes_top,1070,$column.codes_layout.height)
     Draw-ReviewText $graphics $column.speech $font ([Drawing.Brushes]::Black) $speechRect
     Draw-ReviewText $graphics $column.codes $font ([Drawing.Brushes]::DarkRed) $codesRect
     $speechHasher=[Security.Cryptography.SHA256]::Create()
     try{$speechHash=[BitConverter]::ToString($speechHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($column.speech))).Replace('-','').ToLowerInvariant()}
     finally{$speechHasher.Dispose()}
     $renderedCandidates.Add([pscustomobject]@{case_id=$row.case.case_id;suite=$suite;column=$column.phase;candidate_sha256=$column.candidate.candidate_sha256;speech_sha256=$speechHash;characters_fitted=$column.speech_layout.characters_fitted;text_length=$column.speech.Length;line_count=$column.speech_layout.line_count;measured_height=$column.speech_layout.measured_height;layout_height=$speechRect.Height;layout_width=$speechRect.Width;left=$speechRect.Left;right=$speechRect.Right;top=$speechRect.Top;bottom=$speechRect.Bottom;codes_top=$codesRect.Top;codes_bottom=$codesRect.Bottom;row_top=$row.top;row_bottom=($row.top+$row.height);canvas_width=$bitmap.Width;canvas_height=$bitmap.Height;word_wrap=$true})
    }
   }
   $imagePath=Join-Path $outputDirectory ($suite+'-original-refined.png')
   $bitmap.Save($imagePath,[Drawing.Imaging.ImageFormat]::Png)
   Write-Output ('Review image: '+$imagePath)
  }finally{$graphics.Dispose();$bitmap.Dispose()}
 }
}finally{$measureGraphics.Dispose();$measureBitmap.Dispose();$font.Dispose();$header.Dispose();$format.Dispose()}
$renderedCandidates | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $outputDirectory 'rendered-candidate-audit.json') -Encoding UTF8
