# Run with Windows PowerShell 5.1; no Pester, Python or running Docker is needed.
$ErrorActionPreference = 'Stop'
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$source = Join-Path $repository 'Server/scripts/local_server.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
# Load helpers without executing the launcher entry point or starting real services.
foreach ($definition in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}
function Assert-Launcher($condition, [string]$message) { if (-not $condition) { throw $message } }
$fixture = Join-Path $repository ('.runtime/launcher check ' + [guid]::NewGuid().ToString('N'))
$ProjectRoot = Join-Path $fixture 'first'
[IO.Directory]::CreateDirectory($ProjectRoot) | Out-Null
$Utf8 = New-Object Text.UTF8Encoding($false)
$NoOpen = $true
$Port = 18765
Initialize-LocalEnvironment
$firstPath = Join-Path $ProjectRoot '.env'
$first = [IO.File]::ReadAllText($firstPath)
Assert-Launcher ($first.Contains('API_PORT=18765') -and $first.Contains('APP_ENV=test')) 'New settings ignored the selected local test port.'
$firstTokens = (($first -split "`n" | Where-Object { $_.StartsWith('DEV_TOKENS=') }) -replace '^DEV_TOKENS=', '') | ConvertFrom-Json
Assert-Launcher (@($firstTokens.PSObject.Properties).Count -eq 2) 'Local test users were not provisioned.'
foreach ($entry in $firstTokens.PSObject.Properties) {
    Assert-Launcher ($entry.Name -match '^[A-Za-z0-9_-]{48}$') 'A generated token is not a URL-safe random secret.'
}
$Port = 18766
Initialize-LocalEnvironment
Assert-Launcher ([IO.File]::ReadAllText($firstPath) -ceq $first) 'A repeated launch replaced existing settings or credentials.'
$ProjectRoot = Join-Path $fixture 'second'
[IO.Directory]::CreateDirectory($ProjectRoot) | Out-Null
Initialize-LocalEnvironment
$second = [IO.File]::ReadAllText((Join-Path $ProjectRoot '.env'))
Assert-Launcher ($second -cne $first) 'Independent local installations reused credentials or identity.'
$configuration = [pscustomobject]@{ services = [pscustomobject]@{ api = [pscustomobject]@{ environment = [pscustomobject]@{
    DEV_TOKENS = '{"fixture-token":"<owner>"}'; AI_MODE = 'disabled'
} } } }
Write-ConnectionGuide -Configuration $configuration -BaseUrl 'http://127.0.0.1:18766' -Pets @([pscustomobject]@{owner='<owner>';pet_id=('e' * 32)})
$guide = [IO.File]::ReadAllText((Join-Path $ProjectRoot '.runtime/local-server-connection.html'))
Assert-Launcher ($guide.Contains('http://127.0.0.1:18766/health/ready') -and $guide.Contains('fixture-token') -and $guide.Contains(('e' * 32))) 'The guide omitted the actual API address or matching token and pet.'
Assert-Launcher ($guide.Contains('&lt;owner&gt;') -and -not $guide.Contains('<h2><owner></h2>')) 'The guide did not escape server owner text.'
$unconfiguredRejected = $false
try { Start-LocalAI -Configuration $configuration } catch { $unconfiguredRejected = $_.Exception.Message.Contains('AI is not configured') }
Assert-Launcher $unconfiguredRejected 'An unconfigured AI stack was incorrectly reported as ready.'
Stop-LocalAI
Stop-LocalAI
Assert-Launcher (Test-Path -LiteralPath (Join-Path $ProjectRoot '.runtime/local-services.stop')) 'AI stop incorrectly required model configuration or Docker.'
Assert-Launcher ([IO.File]::ReadAllText((Join-Path $ProjectRoot '.env')) -ceq $second) 'Stopping AI changed API settings or credentials.'
# Simulate a stalled Docker CLI: the helper must kill only its own probe and return.
$script:Docker = Join-Path $fixture 'stalled-docker.exe'
Add-Type -TypeDefinition 'public class StalledDockerProbe { public static void Main() { System.Threading.Thread.Sleep(30000); } }' -OutputAssembly $script:Docker -OutputType ConsoleApplication
$elapsed = [Diagnostics.Stopwatch]::StartNew()
$engine = Get-DockerEngine
$elapsed.Stop()
Assert-Launcher ($engine -eq '' -and $elapsed.Elapsed.TotalSeconds -lt 10) 'A stalled Docker CLI bypassed the readiness timeout.'
Assert-Launcher (-not (Get-Process -Name 'stalled-docker' -ErrorAction SilentlyContinue)) 'The timed-out Docker probe was left running.'
# Exercise the real dispatcher without launching models: stop failures must not
# strand the other AI group, and backend-only commands must never touch Pose.
$script:Calls = New-Object System.Collections.Generic.List[string]
$script:CoreFails = $false; $script:PoseFails = $false
function Invoke-ConfiguredRuntime {
    $script:Calls.Add('core:' + $Action + ':' + $Target)
    if ($script:CoreFails) { throw 'fixture core failure' }
}
function Invoke-PoseRuntime {
    param([string]$Operation)
    $script:Calls.Add('pose:' + $Operation)
    if ($script:PoseFails) { throw 'fixture pose failure' }
}
foreach ($Target in @('Backend', 'AI', 'All')) {
    foreach ($Action in @('Start', 'Stop')) {
        $script:Calls.Clear()
        Invoke-SelectedServices
        $core = 'core:' + $Action + ':' + $Target
        $expected = if ($Target -eq 'Backend') { $core } elseif ($Action -eq 'Start') { $core + ',pose:Start' } else { 'pose:Stop,' + $core }
        Assert-Launcher (($script:Calls -join ',') -eq $expected) 'AI/Pose dispatch or backend isolation failed.'
    }
}
$Target = 'AI'; $Action = 'Stop'
foreach ($failure in @('core', 'pose', 'both')) {
    $script:Calls.Clear(); $script:CoreFails = $failure -ne 'pose'; $script:PoseFails = $failure -ne 'core'
    $rejected = $false
    try { Invoke-SelectedServices } catch { $rejected = $true }
    Assert-Launcher ($rejected -and ($script:Calls -join ',') -eq 'pose:Stop,core:Stop:AI') 'A failed stop skipped another group or reported success.'
}
$Action = 'Start'; $script:CoreFails = $true; $script:PoseFails = $false; $script:Calls.Clear()
try { Invoke-SelectedServices } catch { }
Assert-Launcher (($script:Calls -join ',') -eq 'core:Start:AI') 'Pose was started after the core AI startup failed.'
$script:CoreFails = $false; $script:PoseFails = $true; $script:Calls.Clear(); $rejected = $false
try { Invoke-SelectedServices } catch { $rejected = $_.Exception.Message.Contains('incomplete') }
Assert-Launcher ($rejected -and ($script:Calls -join ',') -eq 'core:Start:AI,pose:Start') 'Partial AI startup was reported as complete.'
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $repository '.runtime')) + [IO.Path]::DirectorySeparatorChar
$fixturePath = [IO.Path]::GetFullPath($fixture)
Assert-Launcher ($fixturePath.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase) -and
    (Split-Path $fixturePath -Leaf) -match '^launcher check [0-9a-f]{32}$') 'Fixture cleanup escaped this checkout runtime.'
Remove-Item -LiteralPath $fixturePath -Recurse -Force
Write-Host 'Launcher checks PASS: setup, preserved settings, bounded Docker probe, unified AI/Pose dispatch, backend isolation, independent stop attempts, partial failure reporting.'
