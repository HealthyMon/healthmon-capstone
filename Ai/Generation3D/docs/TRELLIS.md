# TRELLIS.2 runtime and evidence

The adapter uses [Microsoft's official TRELLIS.2 source](https://github.com/microsoft/TRELLIS.2), pinned to `75fbf0183001ed9876c8dbb35de6b68552ee08bd`, and the official `microsoft/TRELLIS.2-4B` pretrained weights. The source was copied into a new checkout at `vendor/TRELLIS.2`; `git ls-remote` confirmed that revision was the current official HEAD during setup. No earlier source checkout or environment was modified.

The inference worker calls `Trellis2ImageTo3DPipeline.run(..., pipeline_type="512", seed=...)` and exports the resulting geometry and learned base-color, metallic, roughness, and alpha voxel attributes through `o_voxel.postprocess.to_glb`. CuMesh performs the official remeshing and UV unwrapping. GLB textures use PNG for standard viewer compatibility; the official example's optional WebP extension is disabled. Output geometry is never replaced with an existing model or a procedural substitute.

## Current verified status

The new `.venvs/trellis` environment imports `cumesh`, `o_voxel`, `flex_gemm`, `nvdiffrast.torch`, `flash_attn`, `transformers`, `utils3d`, and the official `Trellis2ImageTo3DPipeline` successfully. Host PyTorch remains `2.10.0+cu130`, CUDA toolkit `13.0`, Python `3.12`, architecture `aarch64`. Setup details and package versions are in `logs/trellis/setup.json` and `logs/trellis/setup.log`.

Authenticated access to the mandatory `facebook/dinov3-vitl16-pretrain-lvd1689m` checkpoint is now verified in `logs/dinov3_authenticated_access.json`. Real 512 inference and PBR GLB export have executed on GB10. The earlier unauthenticated HTTP 401 preflight remains historical evidence in `logs/trellis/official_sample.trellis.json`; it is no longer the current blocker. Per-run `.trellis.json` files record the actual inference/export flags, hashes, and timings.

The first source GLB passed geometry/UV/material import checks but was rejected after visual inspection revealed severe horizontal planes. Its original PNG had faint decoded alpha grid/shadow residue outside the creature. That attempt is preserved in `outputs/lucan_stage2_to_stage3_seed42/rejected/bootstrap_3d/attempt_1_planar_stripes/`. The adapter now creates a separate alpha-sanitized image: it keeps substantial confident foreground components, dilates their support by four pixels to preserve antialiasing, and removes distant residue and alpha below 16. RGB and the original Qwen file remain unchanged. The derived image then passes through the official preprocessor and real inference again. This is input matte repair, not model training or a substitute mesh. Latest renders and `validation/visual_review.json` determine whether the artifact is resolved.

The original official pipeline also references `briaai/RMBG-2.0`, which currently returns HTTP 401 without authorization. Its preprocessing function directly accepts RGBA foreground masks. For an input with usable alpha, the adapter uses the official constructor with `rembg_model=None`, then follows that existing alpha branch. This avoids loading a background model that the pipeline will not call. For RGB or fully opaque RGBA inputs, the adapter checks and loads the official RMBG checkpoint. DINOv3 remains mandatory for every input.

## Isolated setup

The setup performed here reused compatible native builds by copying their package files into the new environment. These earlier builds contain native `sm_121` CUDA code for CuMesh and O-Voxel, and `sm_120` code for FlashAttention. The existing environment is used only as a read source. Immutable cached official Microsoft checkpoint files are hardlinked into a new task-local Hugging Face cache, with independent cache directories and metadata. Missing public sparse-structure decoder weights were downloaded from `microsoft/TRELLIS-image-large`.

```bash
python scripts/setup_trellis.py \
  --native-from /workspace/3d_model_comparison/20261005/envs/trellis2 \
  --reuse-cache /workspace/3d_model_comparison/20261005/cache/huggingface/hub \
  --download-public
```

For a fresh native build, `python scripts/setup_trellis.py --build-native --arch 12.1 --download-public` clones the official extension sources and builds them with the host CUDA toolkit. That source-build mode is provided but was not executed in this run. The default path does not claim a new native compilation. The setup script constrains inherited PyTorch/torchvision/Triton versions to preserve their CUDA ABI.

Compatibility corrections made during setup:

- O-Voxel's previous environment could not import because `plyfile` was missing; the new environment installs it.
- Installing all `utils3d` optional dependencies failed on aarch64 because `glcontext` needed unavailable `X11/Xlib.h`. Headless inference does not use that optional OpenGL backend, so the official pinned `utils3d` package is installed without those extras.
- An unconstrained initial dependency resolver selected newer PyTorch/CUDA packages inside the new environment. Those replacements were removed from the new environment, and setup now constrains the host's `torch==2.10.0+cu130`, `torchvision==0.25.0+cu130`, and `triton==3.6.0`. The original environments remained unchanged.
- The NVIDIA PyTorch image emits a warning that its advertised supported capability range ends at 12.0 while GB10 is 12.1. Real TRELLIS sampling, decoding, CuMesh UV unwrapping, and textured GLB export have now executed on this GPU.

## Run or resume

Merge `configs/trellis_runtime.json` into the runtime configuration if those paths differ from the defaults. `trellis_python`, `trellis_repo`, `trellis_model`, and `trellis_cache` select the interpreter, source, weights, and isolated cache. The default export uses a 2048 texture atlas and the official one-million decimation target, with remeshing enabled.

```bash
python src/healthmon/trellis_runner.py \
  --image path/to/foreground.png --output outputs/model.glb --seed 42 \
  --config configs/runtime.json --preflight

python src/healthmon/trellis_runner.py \
  --image path/to/foreground.png --output outputs/model.glb --seed 42 \
  --config configs/runtime.json
```

`--preflight` checks required checkpoint access without GPU inference. Without it, the worker proceeds through the real pipeline and official PBR export only when the required checkpoints are accessible. Standard `HF_TOKEN`, `HF_TOKEN_PATH`, and `hf auth login` credentials are honored; isolating `HF_HOME` preserves the original token file location. Credentials are never printed or copied into reports. Alternatively, `trellis_dino_model` can point at an authorized local directory containing the exact official DINOv3 checkpoint and configuration. No alternative conditioning architecture is supplied.

The Python API is `run_trellis(image, output, seed=42, config=...)`. It returns the evidence dictionary on success and raises `TrellisError` with an accessible `.report` on failure. Every attempt saves `<output stem>.trellis.json`, `.trellis.log`, and `.trellis.config.json`; successful preprocessing also saves `.preprocessed.png`. Reports distinguish setup, checkpoint-access, inference, and export failures, and include seed, commit, timings, and hashes. The official constructor loads only the six models required by the 512 path, preserving the official 512 architecture and sampler defaults while avoiding unneeded 1024-model allocations.

## Sources and licenses

TRELLIS.2 source, O-Voxel, and the Microsoft TRELLIS.2-4B checkpoint are MIT licensed. CuMesh (`12289e1062f0603f2f0d0771b02e1395d247f26f`) and FlexGEMM (`6dd94a859c26ee8246888502eada3dd8ad85532e`) use MIT licenses. The pinned utils3d source revision is `9a4eb15e4021b67b12c460c7057d642626897ec8`. nvdiffrast `v0.4.0` and FlashAttention have separate upstream license terms. DINOv3 and Bria checkpoint access and license terms are separate from Microsoft's MIT release; this implementation does not bypass their access controls.

Primary references: [official README and example](https://github.com/microsoft/TRELLIS.2), [official pretrained pipeline manifest](https://huggingface.co/microsoft/TRELLIS.2-4B/blob/main/pipeline.json), [CuMesh](https://github.com/JeffreyXiang/CuMesh), [FlexGEMM](https://github.com/JeffreyXiang/FlexGEMM), and the vendored `LICENSE` and `setup.sh` files.
