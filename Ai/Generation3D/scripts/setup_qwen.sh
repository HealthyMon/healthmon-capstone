#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QWEN_VENV="$PROJECT_DIR/.venvs/qwen"
mkdir -p "$PROJECT_DIR/vendor" "$PROJECT_DIR/logs" "$PROJECT_DIR/models/huggingface"
python -m venv --system-site-packages "$QWEN_VENV"
# Reuse host ARM64 CUDA PyTorch; do not install a replacement torch wheel.
"$QWEN_VENV/bin/python" -c 'import torch; print(torch.__version__, torch.version.cuda)'
if [ ! -d "$PROJECT_DIR/vendor/diffusers/.git" ]; then
    git clone https://github.com/huggingface/diffusers "$PROJECT_DIR/vendor/diffusers"
    git -C "$PROJECT_DIR/vendor/diffusers" checkout 1d5d056ecff3a8c1d887a7dd1aa66ca4a0323458
fi
if [ "$(git -C "$PROJECT_DIR/vendor/diffusers" rev-parse HEAD)" != "1d5d056ecff3a8c1d887a7dd1aa66ca4a0323458" ]; then
    echo "Unexpected Diffusers revision; inspect it before changing the existing checkout." >&2
    exit 1
fi
if [ ! -d "$PROJECT_DIR/vendor/Qwen-Image-2.1/.git" ]; then
    git clone https://github.com/QwenLM/Qwen-Image-2.1 "$PROJECT_DIR/vendor/Qwen-Image-2.1"
    git -C "$PROJECT_DIR/vendor/Qwen-Image-2.1" checkout 1993c3a4821f977df0b6dd2661ff5b40239aa55a
fi
"$QWEN_VENV/bin/python" -m pip install -e "$PROJECT_DIR/vendor/diffusers" \
    'transformers==5.19.0' 'accelerate==1.15.0' 'huggingface-hub==1.33.0' \
    'safetensors==0.8.0' 'tokenizers==0.23.3' 'sentencepiece==0.2.2' pillow
# BF16 inference does not use torchao quantization, but current Diffusers imports
# optional torchao when the host has it. A venv-local release fixes the old API.
"$QWEN_VENV/bin/python" -m pip install --no-deps 'torchao==0.16.0'
"$QWEN_VENV/bin/python" -c 'from diffusers import QwenImage21Pipeline; print(QwenImage21Pipeline)'
"$QWEN_VENV/bin/python" "$PROJECT_DIR/scripts/setup_qwen_download.py" --project "$PROJECT_DIR"
