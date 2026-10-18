$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    uv --cache-dir "$root\runtime\uv-cache" venv --python 3.10 .venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
uv --cache-dir "$root\runtime\uv-cache" pip install --python .venv\Scripts\python.exe 'torch==2.12.0+cu126' --index-url https://download.pytorch.org/whl/cu126
if ($LASTEXITCODE -ne 0) { throw 'torch installation failed' }
uv --cache-dir "$root\runtime\uv-cache" pip install --python .venv\Scripts\python.exe -r requirements.lock.txt --extra-index-url https://download.pytorch.org/whl/cu126 --index-strategy unsafe-best-match
if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
.venv\Scripts\python.exe -c "import torch; print(torch.__version__,torch.cuda.is_available(),torch.cuda.is_bf16_supported())"
