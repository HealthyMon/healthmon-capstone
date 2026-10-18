param([Parameter(Mandatory=$true)][string]$Name,[Parameter(Mandatory=$true)][string[]]$Arguments)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$stdout = Join-Path $root "runs\$Name.stdout.log"
$stderr = Join-Path $root "runs\$Name.stderr.log"
if (Test-Path -LiteralPath $stdout) { throw 'Existing job logs: choose a new name' }
$env:PYTHONUTF8 = '1'
$proc = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -ArgumentList $Arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$proc.Id | Set-Content -LiteralPath (Join-Path $root "runs\$Name.pid")
Write-Output "Started $Name PID=$($proc.Id) stdout=$stdout stderr=$stderr"
