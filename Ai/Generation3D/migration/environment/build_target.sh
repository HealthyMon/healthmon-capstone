#!/usr/bin/env bash
# Environment reconstruction only, inside a NEW target image. Never loads model weights.
set -euo pipefail
if [[ "${1:-}" != --target-container || "$(uname -m)" != x86_64 || ! -f /.dockerenv ]]; then
  echo 'Run only through the target x86_64 Dockerfile.' >&2; exit 2
fi
cd "$HEALTHMON_RUNTIME"
python3 migration/tools/verify_sources.py
# Keep the original matting Python/NumPy combination in its own environment.
printf '%s  %s\n' 'f276987f06270ae6c1fb4da620bd105edf78c31368c2f7e85e6c1d51c560b04b' 'vendor/Python-3.10.21.tgz' | sha256sum -c -
mkdir -p /tmp/healthmon-python-build
tar -xzf vendor/Python-3.10.21.tgz -C /tmp/healthmon-python-build --strip-components=1
(cd /tmp/healthmon-python-build && ./configure --prefix=/opt/healthmon-python310 --with-ensurepip=install && make -j"${MAX_JOBS:-4}" && make altinstall)
python3 -m pip install --break-system-packages 'torch==2.10.0+cu130' 'torchvision==0.25.0+cu130' --index-url https://download.pytorch.org/whl/cu130
python3 -m pip install --break-system-packages -r requirements.txt
for stage in qwen trellis riganything; do
  python3 -m venv --system-site-packages "$HEALTHMON_ENVS/$stage"
  "$HEALTHMON_ENVS/$stage/bin/python" -m pip install \
    -c "migration/environment/constraints-$stage.txt" \
    -r "migration/environment/requirements-$stage.txt"
done
"$HEALTHMON_ENVS/qwen/bin/python" -m pip install \
  -c migration/environment/constraints-qwen.txt -e vendor/diffusers
/opt/healthmon-python310/bin/python3.10 -m venv "$HEALTHMON_ENVS/matting"
"$HEALTHMON_ENVS/matting/bin/python" -m pip install \
  -c migration/environment/constraints-matting.txt -r migration/environment/requirements-matting.txt
TRELLIS_PY="$HEALTHMON_ENVS/trellis/bin/python"
"$TRELLIS_PY" -m pip install -c migration/environment/constraints-trellis.txt setuptools wheel packaging psutil
for source in utils3d CuMesh FlexGEMM TRELLIS.2/o-voxel nvdiffrast flash-attention; do
  "$TRELLIS_PY" -m pip install --no-deps --no-build-isolation "$HEALTHMON_RUNTIME/vendor/$source"
done
for stage in qwen trellis riganything matting; do
  "$HEALTHMON_ENVS/$stage/bin/python" -m pip check
  mkdir -p /opt/healthmon-build
  "$HEALTHMON_ENVS/$stage/bin/python" -m pip freeze > "/opt/healthmon-build/$stage.freeze.txt"
done
# Existing RigAnything entry runs inside Blender; its Python ABI must match the venv.
blender -b --factory-startup --python-exit-code 1 --python-expr \
  'import bpy,sys; print("Blender",bpy.app.version_string,"Python",sys.version); assert bpy.app.version[:3] == (4,0,2), "Blender version mismatch"; assert sys.version_info[:2] == (3,12), "Blender/Python ABI mismatch"'
python3 --version
nvcc --version
# Build completion does not imply RTX 3090 inference success.
