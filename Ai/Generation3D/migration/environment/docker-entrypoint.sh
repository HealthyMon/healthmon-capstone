#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME"
cd "$HEALTHMON_RUNTIME"
python3 migration/tools/configure_runtime.py --runtime-root "$HEALTHMON_RUNTIME" \
  --env-root "$HEALTHMON_ENVS" --blender "$HEALTHMON_BLENDER" --replace-generated
exec "$@"
