$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
uv venv --python 3.11 .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
uv pip install --python .venv/Scripts/python.exe torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed' }
uv pip install --python .venv/Scripts/python.exe -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
Write-Host 'Ready. Run .venv\Scripts\python.exe download.py'
