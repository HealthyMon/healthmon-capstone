#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo '이 설치 스크립트는 Apple Silicon macOS용입니다.' >&2
  exit 1
fi
mkdir -p .tools .python .cache/uv models reports
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
export UV_CACHE_DIR="$PWD/.cache/uv"
uv_bin="$PWD/.tools/uv-aarch64-apple-darwin/uv"
if [ ! -x "$uv_bin" ]; then
  curl -L --fail --retry 2 https://github.com/astral-sh/uv/releases/download/0.13.7/uv-aarch64-apple-darwin.tar.gz -o .tools/uv.tar.gz
  actual_hash=$(shasum -a 256 .tools/uv.tar.gz | awk '{print $1}')
  [ "$actual_hash" = '81b811b57e4624df7ed3aac148e0359100d9962f3d9dce00aec533dc2e086731' ] || { echo 'uv 해시가 일치하지 않습니다.' >&2; exit 1; }
  tar -xzf .tools/uv.tar.gz -C .tools
fi
"$uv_bin" python install --no-bin 3.12.16
if [ ! -x .venv/bin/python ]; then
  "$uv_bin" venv --python 3.12.16 .venv
fi
"$uv_bin" pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python scripts/download_models.py
.venv/bin/python scripts/build_launcher.py
echo '설치 완료. ./run.sh 로 실행하세요.'
