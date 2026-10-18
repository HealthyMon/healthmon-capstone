# Official RigAnything integration

The primary backend is the official [RigAnything repository](https://github.com/Isabella98Liu/RigAnything), pinned to source commit `d03cdb21dd134fa81df6b0947522469db3f78bd2`. The public [Isabellaliu/RigAnything checkpoint](https://huggingface.co/Isabellaliu/RigAnything) is pinned to revision `30df7c0c390db1d5453c5af12da8d227c5025db6`.

The checkpoint is 2,344,595,770 bytes. Its SHA256 is `84c00971ed5c07f2906495bb4a23891058e7e1ee2afe687ada2011cd082a187a`. A checkpoint hash mismatch stops the runner.

## Tested environment

The real HEALTHMON Lucan run has now executed official GPU inference and exported a final textured rig at `outputs/lucan_stage2_to_stage3_seed42/rigging/final_rigged.glb`. The model predicted 27 joints with a connected hierarchy and skinning weights. The final reimport has 777,544 vertices, one skin, one skinned primitive, 27 active joints, zero invalid-weight vertices, and two embedded 2048×2048 textures. The 61,660,424-byte GLB SHA256 is `5bbffa8ebcf2e332c17255e599bc99e06957cb095e37897187f41d55542bac87`. Real local deformation passes; anatomical suitability is reviewed separately. Exact evidence is in the run's `rigging/validation.json` and `validation/glb_report.json`.

The proxy correspondence has a 1.93% extent p95 surface distance and 6.17% maximum distance, within the declared thresholds. The independent upstream inverse-axis check has maximum world error 5.55e-17. Original textured geometry remains separately preserved in `trellis/evolved.glb`. The official source and checkpoint, rather than a procedural armature or default automatic weights, generated this rig.

The inspected machine is ARM64/aarch64, with Python 3.12.3, PyTorch 2.10.0+cu130, CUDA 13 and NVIDIA GB10. RigAnything recommends Python 3.11; this installation has actually passed its CPU import and strict checkpoint architecture preflight under Python 3.12 inside Blender 4.0.2. It loaded all 123 state tensors into the 195,369,478 parameter model with no missing or unexpected keys. The result is in `logs/rigging_preflight/riganything_preflight.json`. This preflight does not execute GPU inference or establish final HEALTHMON rig quality.

Blender is an existing isolated Ubuntu ARM64 4.0.2 bundle at `/workspace/3d_pipeline_lab/runtime/blender_arm/root/usr/bin/blender`. The executable `scripts/blender` launcher configures its library and script directories per subprocess; the system installation is not modified. A fresh host can supply a compatible `--blender` path, or extract ARM64 Blender and its dependency `.deb` files into the project with `--blender-debs DIRECTORY`.

The project environment `.venvs/riganything` inherits the existing compatible torch installation and adds `easydict==1.13`, `trimesh==4.12.2` and `transformers==4.57.6`. Official RigAnything inference does not require FlashAttention, xFormers, spconv or CUDA extension compilation. The upstream convenience dependency list includes a PyPI `bpy` wheel, Open3D and PyMeshLab. This adapter runs the official entry points inside actual Blender instead, and prepares a proxy using Blender's decimation and triangulation; it does not install incompatible ARM `bpy` wheels or the unused geometry packages.

## Setup and execution

```bash
cd /workspace/healthmon-evolution
bash scripts/setup_rigging.sh
# On a fresh ARM64 host with downloaded Ubuntu packages:
# bash scripts/setup_rigging.sh --blender-debs /path/to/arm64/debs

PYTHONPATH=src python -m healthmon.rigging_runner \
  --config configs/runtime.json \
  --input outputs/EXPERIMENT/trellis/evolved.glb \
  --output-dir outputs/EXPERIMENT/rigging \
  --faces 8192 --seed 42
```

Setup writes `configs/rigging_runtime.json` as a mergeable fragment without overwriting the main runtime config. Both the fragment and main config may be passed directly with `--config`. Setup is CPU-only. The inference command uses the GPU and should be scheduled alongside the other models to avoid simultaneous model memory use.

The runner invokes the following inspected official interfaces in real Blender processes:

1. `inference.py --config config.yaml --load CHECKPOINT -s inference true -s inference_out_dir OUTPUT --mesh_path proxy.glb` predicts a skeleton, parent hierarchy and per-vertex skin weights, saved as `proxy.npz`.
2. `inference_utils/vis_skel.py --data_path proxy.npz --save_path OUTPUT --mesh_path proxy.glb` creates `proxy_rig.glb` using the official export implementation.
3. The project transfers these predicted weights to the original textured GLB and exports `final_rigged.glb`.

The official repository is unchanged on disk. A documented seed-only AST override changes its fixed `torch.manual_seed(777)` call to the requested experiment seed; NumPy and the documented trimesh surface-sampling interface are also seeded. The adapter forces strict checkpoint loading and refuses sequence generation unless the official model weights were loaded. This guard prevents the upstream exception-catching checkpoint loader from silently allowing an uninitialized model after a load failure. Exact commands, logs, model identity and adapter notes are retained per experiment. Retrying archives preceding process logs and command records rather than overwriting failed-attempt evidence.

## Geometry, textures and spatial correspondence

The high-quality TRELLIS original is kept intact. `proxy.glb` is a separate triangulated decimation copy for the neural rigging input. It retains material information, but the final mesh, UVs and materials come from the original GLB.

Skinning transfer uses the closest triangle surface in the common Blender world coordinate system. The three triangle vertices' predicted neural weights are interpolated using barycentric coordinates, restricted to the four strongest influences and normalized. No unrelated vertex-index matching is used. The exact triangle indices, coefficients, target positions and distances are saved in `spatial_transfer.mapping.npz`.

Before export, `coordinate_validation.json` numerically compares the official denormalized NPZ pointcloud after inverse-axis rotation against independently imported proxy world vertices. Original and proxy file hashes are retained. There is no guessed alignment. Original and predicted proxy must share coordinates. Transfer fails when its 95th-percentile distance exceeds 5% of the original mesh's largest extent, or the maximum distance exceeds 15%. These tolerances are visible in `spatial_transfer.json` and can be tightened with the direct Blender transfer command. Numerical proximity cannot eliminate leakage between physically adjacent limbs, so anatomical review remains necessary.

## Outputs and validation

The rigging output directory contains:

- `final_rigged.glb`: original textured mesh bound to the model-predicted armature and weights.
- `proxy.glb`, `proxy.npz`, `proxy_rig.glb`: preserved neural inference inputs and outputs.
- `original_validation.json`, `spatial_transfer.json`, `validation.json`: actual import and correspondence checks.
- `neutral.png`, `skeleton_preview.png`: copies of the neutral pose and unobstructed skeleton preview.
- `validation/neutral.png`, `validation/pose_test.png`, `validation/skeleton_preview.png`, `validation/pose_test.blend`: neutral, actual deformed pose and skeleton-only evidence.
- `renders/front.png`, `three_quarter.png`, `side.png`, `back.png`: consistently framed textured views.
- Exact command JSON, process logs and checkpoint/seed settings.

Validation reimports the exported GLB into Blender and checks finite nonempty geometry, bounds, materials, UVs and image textures. It also inspects the GLB JSON for actual skins, joints, `JOINTS_0` and `WEIGHTS_0` attributes. Rig checks require multiple bones, a valid hierarchy, Armature modifiers, nonempty normalized skin weights and influences on multiple joints.

The automated pose test rotates nonroot bones by 15 degrees on three axes and measures evaluated mesh vertices through Blender's dependency graph. It requires a measurable local deformation and compares the moving region with vertices weighted to the rotated joint and its descendants. It records the selected bone and displacement counts and renders that actual pose. This verifies technical binding; it does not prove anatomical suitability or production animation quality. Skeleton previews render real predicted bone positions without the mesh obscuring them.

The default front camera is on Blender -Y after glTF's +Y-up import conversion. A character may face another direction; `--front-azimuth` records a visual-review adjustment. Renders use neutral lighting, orthographic framing and CPU Cycles.

## Independent Lucan limb audit

The final 27-joint Lucan GLB passes numerical binding checks, but it still requires anatomical rig correction before animation use. A separate CPU Blender audit rotates all 26 nonroot bones on three local axes, giving 78 actual deformation tests. Four paw surfaces, torso flanks and the head are defined by spatial regions independently of the predicted weights. Positive-X front and hind paw tests leave the other three paws stationary. The negative-X front test also moves 48.7% of torso-region vertices and 38.5% of the same-side hind paw; the negative-X hind test also moves 55.6% of the opposite hind paw. The positive-X front test also moves 13.7% of the head region. These observations do not establish independent four-leg control or gait quality.

One isolated candidate used the same official checkpoint and seed 42 with a 32,768-face proxy. It passed technical validation with 24 joints, and transfer distance P95 improved from 1.928% to 0.365% of mesh extent. Its 69 independent joint/axis tests showed worse opposite-hind-paw coupling, reaching 100% moving vertices, so it was not promoted. This is a comparison of anatomical behavior, not evidence that every region is better in the selected rig.

The selected final GLB remains unchanged. Hash-bound evidence is in `outputs/lucan_stage2_to_stage3_seed42/validation/rig_quality_review.json`; complete measurements, real diagnostic renders, preserved helpers and exact commands are under `logs/anatomy_audit/` within that run. The unselected candidate remains under `rigging_candidates/faces32768_seed42/`.

## Licenses

Both the official source `LICENSE.md` and the downloaded checkpoint repository `LICENSE.md` state the Adobe Research License. It permits use of those materials for noncommercial research and teaching; commercial product development and other commercial gain are outside its grant. Keep the copyright/license notices when redistributing the materials. A university noncommercial capstone fits the stated research/teaching purpose; future commercial use requires separate authorization. The model card does not provide a broader generated-output license, so this project does not assert that model-produced assets have unrestricted commercial rights. See the [official license text](https://github.com/Isabella98Liu/RigAnything/blob/main/LICENSE.md).

Installed dependency license metadata is preserved in `logs/rigging_preflight/dependency_licenses.json`. Core dependencies include PyTorch (BSD-3-Clause), Transformers and Hugging Face Hub (Apache), trimesh/einops/PyYAML/rich (MIT), NumPy and SciPy (BSD plus bundled-library notices), and easydict (LGPL-3.0). Blender is GPL software; keep its and its packaged dependencies' notices when redistributing the runtime. These dependency terms do not override RigAnything's noncommercial model/material restrictions.

[UniRig](https://github.com/VAST-AI-Research/UniRig) remains an allowed alternative, but is not silently substituted here. Its repository is MIT licensed and has separate skeleton and skin checkpoints; its CUDA sparse-convolution and attention dependencies require additional ARM64/GB10 verification. RigAnything passed the CPU preflight, so no UniRig fallback was required.

## Tool verification evidence

`logs/blender_tool_smoke/smoke_test.json` labels the existing unrelated neural-rig sample used solely for CPU tooling tests. The tests passed actual textured import, an 18-bone deformation test, barycentric weight-transfer roundtrip, and all four camera renders. The deformation moved 28,300 of 119,974 evaluated vertices, with zero moving vertices outside the selected joint/descendant weighted region. Two textures and the material remained present after transfer. An unrigged input was correctly rejected with `status: FAIL` and a nonzero process exit.

`logs/blender_tool_smoke/official_export_fixture/` tests the unchanged official exporter using a format conversion of that existing genuine neural rig. It does not represent new RigAnything model inference. The numerical inverse-coordinate check passed, the official exporter completed in real Blender, and its exported GLB passed the rig/deformation validation. These tooling checks establish adapter behavior only; they are not substituted for the requested HEALTHMON experiment.
