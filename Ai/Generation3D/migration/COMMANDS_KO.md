# 실제 기존 CLI와 입출력 계약

아래는 새 PC에서 Docker 빌드 후 실행할 명령이다. 이번 Spark 작업에서는 GPU 명령을 실행하지 않았다. 프로젝트 폴더에서 `docker compose run --rm generation3d bash`로 들어가면 현재 경로 설정과 오프라인 HF 변수가 준비된다.

1. GLB/FBX → PNG (OBJ는 현재 renderer 미지원):

```bash
mkdir -p outputs/manual
blender -b --python-exit-code 1 -P src/healthmon/blender_tool.py -- \
  render --input assets/examples/lucan_s2_healthy.glb --out-dir outputs/manual/renders --size 768
```

출력: `front.png`, `three_quarter.png`, `side.png`, `back.png`, 렌더 메타데이터. 외부 texture를 참조하는 FBX/GLB 입력은 그 texture도 함께 필요하다.

2. Qwen 이미지 편집 (prompt.txt는 사용자가 작성):

```bash
"$HEALTHMON_ENVS/qwen/bin/python" src/healthmon/qwen_runner.py \
  --images outputs/manual/renders/three_quarter.png --roles edit_base_primary_identity_three_quarter \
  --prompt-file prompt.txt --output outputs/manual/qwen/edited.png \
  --cache-dir "$HEALTHMON_RUNTIME/models/huggingface" --local-files-only \
  --seed 42 --width 768 --height 768 --steps 40 --memory-mode model-cpu-offload
```

출력: RGBA `edited.png`, `edited.png.json`, effective prompt. offload는 원래 CLI 옵션이며 새 정밀도나 모델을 도입한 것이 아니다. Qwen 프로세스 종료 후 다음 명령으로 넘어간다.

3. 기존 matte → TRELLIS → RigAnything coordinator:

```bash
python3 scripts/run_image_to_rigged.py --image outputs/manual/qwen/edited.png \
  --output-dir outputs/manual/reconstruction --stage 2 --form FIT --seed 42 --size 512
```

출력: `outputs/manual/reconstruction/rigging/final_rigged.glb`. `--size`는 Blender 렌더 크기이고, 현재 TRELLIS pipeline type은 512다.

4. 분리해서 실행할 때는 기존 matte를 먼저 수행한다:

```bash
mkdir -p outputs/manual/matte
"$HEALTHMON_ENVS/matting/bin/python" scripts/background_matte.py \
  outputs/manual/qwen/edited.png outputs/manual/matte/foreground.png
python3 src/healthmon/trellis_runner.py --image outputs/manual/matte/foreground.png \
  --output outputs/manual/trellis/model.glb --seed 42 --config configs/runtime.local.json
python3 src/healthmon/rigging_runner.py --input outputs/manual/trellis/model.glb \
  --output-dir outputs/manual/rigging --seed 42 --faces 8192 --size 512 --config configs/runtime.local.json
```

입출력 계약: matte RGBA → PBR textured GLB → 8192-face rig proxy → 원본 geometry/texture에 joint/skin transfer → `final_rigged.glb`. 직접 CLI를 동시에 실행하지 않는다. 전체 순차 실행은 README의 `scripts/run_stages.sh`를 사용한다.

원래 종/단계 통합 진입점은 다음 형태로 남아 있다. 이 진입점은 Qwen memory-mode를 전달하지 않으므로 3090 첫 시험용으로 제시하지 않는다.

```bash
python3 run_pipeline.py --config configs/runtime.local.json \
  --reference-zip assets/healthmon_evolution_reference_pack_RECOVERED_PARTIAL.zip \
  --species lucan --source-stage 2 --target-stage 3 \
  --input-glb assets/examples/lucan_s2_healthy.glb --seed 42 --run-dir outputs/legacy_lucan
```

복구 reference ZIP은 일부 참조를 재구성한 파일이며 원본 학습 데이터 전체가 아니다. Mongle legacy sheet/crop 10개는 없고 과거 실험 profile이 가리키는 모든 출력 파일을 복사한 것도 아니다. 기본 GLB/FBX → 사용자 prompt → 3D/rig 경로와 이 과거 실험 복원을 구분한다.
