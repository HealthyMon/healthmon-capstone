#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '전용 환경이 없습니다. README.md의 설치 절차를 확인하세요.' >&2
  exit 1
fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec "Local Motion.app/Contents/MacOS/LocalMotion" -m exercise_counter.app "$@"
