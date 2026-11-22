$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv venv --python 3.10 .venv-aihub
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
uv pip install --python .venv-aihub/Scripts/python.exe torch==1.13.1+cu117 torchvision==0.14.1+cu117 --extra-index-url https://download.pytorch.org/whl/cu117 --index-strategy unsafe-best-match
if ($LASTEXITCODE -ne 0) { throw 'PyTorch failed' }
uv pip install --python .venv-aihub/Scripts/python.exe numpy==1.23.5 Pillow==9.5.0 opencv-python==4.8.1.78 yapf==0.40.1 setuptools==69.5.1 wheel mmdet==2.26.0 mmcv-full==1.7.0 -f https://download.openmmlab.com/mmcv/dist/cu117/torch1.13.0/index.html
if ($LASTEXITCODE -ne 0) { throw 'MMDetection failed' }
