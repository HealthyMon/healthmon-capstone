#!/usr/bin/env bash
# Migration command wrapper around unchanged existing inference entry points.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: bash scripts/run_stages.sh INPUT.glb_or_fbx PROMPT.txt NEW_OUTPUT_DIR' >&2
  exit 2
fi
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="$(realpath -e "$1")"
PROMPT="$(realpath -e "$2")"
OUTPUT="$(realpath -m "$3")"
export HEALTHMON_RUNTIME="${HEALTHMON_RUNTIME:-$PROJECT}"
export HEALTHMON_ENVS="${HEALTHMON_ENVS:-$PROJECT/.venvs}"
export HEALTHMON_BLENDER="${HEALTHMON_BLENDER:-/usr/bin/blender}"
export HEALTHMON_MATTING_PYTHON="$HEALTHMON_ENVS/matting/bin/python"
export HEALTHMON_MATTING_CHECKPOINT="$PROJECT/models/matting/bria-rmbg.onnx"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
MEMORY_MODE="${HEALTHMON_QWEN_MEMORY_MODE:-cuda}"
if [[ "$MEMORY_MODE" != cuda && "$MEMORY_MODE" != model-cpu-offload ]]; then
  echo 'HEALTHMON_QWEN_MEMORY_MODE must be cuda or model-cpu-offload' >&2;exit 2
fi
if [[ -e "$OUTPUT" ]]; then echo 'Use a new output directory; existing results are preserved.' >&2;exit 2;fi
cd "$PROJECT"
python3 migration/tools/configure_runtime.py --runtime-root "$PROJECT" --env-root "$HEALTHMON_ENVS" --blender "$HEALTHMON_BLENDER" --replace-generated
mkdir -p outputs "$OUTPUT"
# Share the original run_image_to_rigged.py lock for the Qwen allocation phase.
exec 9>outputs/gpu.lock
flock 9
"$HEALTHMON_BLENDER" -b --python-exit-code 1 -P src/healthmon/blender_tool.py -- \
  render --input "$INPUT" --out-dir "$OUTPUT/renders" --size 768
"$HEALTHMON_ENVS/qwen/bin/python" src/healthmon/qwen_runner.py \
  --images "$OUTPUT/renders/three_quarter.png" --roles edit_base_primary_identity_three_quarter \
  --prompt-file "$PROMPT" --output "$OUTPUT/qwen/edited.png" \
  --cache-dir "$PROJECT/models/huggingface" --local-files-only \
  --seed 42 --width 768 --height 768 --steps 40 --memory-mode "$MEMORY_MODE"
# Qwen process has exited. The original next entry acquires gpu.lock itself.
flock -u 9
exec 9>&-
python3 scripts/run_image_to_rigged.py --image "$OUTPUT/qwen/edited.png" \
  --output-dir "$OUTPUT/reconstruction" --stage 2 --form FIT --seed 42 --size 512
printf 'Result: %s\n' "$OUTPUT/reconstruction/rigging/final_rigged.glb"
