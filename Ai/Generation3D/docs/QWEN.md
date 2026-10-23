# Local Qwen Image 2.1 inference

The HEALTHMON adapter calls the official `diffusers.QwenImage21Pipeline`, with the exact original `Qwen/Qwen-Image-2.1` checkpoint. It does not use Turbo, Edit-2511, paid APIs, quantized replacements, or prompt rewriting models.

## Pinned sources and license

- Official Qwen repository: https://github.com/QwenLM/Qwen-Image-2.1, commit `1993c3a4821f977df0b6dd2661ff5b40239aa55a`.
- Official Diffusers repository: https://github.com/huggingface/diffusers, commit `1d5d056ecff3a8c1d887a7dd1aa66ca4a0323458`, installed editable as `0.41.0.dev0`.
- Checkpoint: https://huggingface.co/Qwen/Qwen-Image-2.1, revision `d26bb61231c349cf6b7896fa83353113880e1ba3`; downloaded files total 33,134,949,561 bytes.
- Qwen repository and checkpoint use the **Qwen RESEARCH LICENSE AGREEMENT**, dated September 20, 2026, allowing **noncommercial research/evaluation only**. Commercial use requires a separate license. Redistribution of covered materials requires the agreement and attribution notices. See the archived exact [checkpoint license](QWEN_MODEL_LICENSE.txt). These restrictions need review before product distribution.
- Diffusers uses Apache-2.0; Transformers uses Apache-2.0; PyTorch uses BSD-style terms. Package license texts remain in the installed distributions and source repositories.

## Setup and verified compatibility

```bash
cd /workspace/healthmon-evolution
bash scripts/setup_qwen.sh
```

The isolated `.venvs/qwen` uses `--system-site-packages` to reuse the existing ARM64 Python 3.12/PyTorch `2.10.0+cu130`; the existing host environment is not modified. Qwen requirements are Transformers `5.19.0`, Accelerate `1.15.0`, Hugging Face Hub `1.33.0`, Safetensors `0.8.0`, and Tokenizers `0.23.3`. Current Diffusers needs a newer optional torchao API than the inherited host `0.14.0+git`, so this venv installs `torchao==0.16.0` without changing torch. No torchao quantization is used for the BF16 checkpoint. No FlashAttention, Triton extension, or xFormers build is required by this adapter; attention uses PyTorch's built-in SDPA.

The host reports NVIDIA GB10 compute capability 12.1 while the existing PyTorch wheel warns its listed maximum is 12.0. This warning alone is not proof of incompatibility or success; the actual model execution and any error are recorded in each generation's JSON metadata. Model downloads and pipeline imports are separately logged and do not count as inference success.

## One real image-conditioned edit

```bash
.venvs/qwen/bin/python src/healthmon/qwen_runner.py \
  --images outputs/example/references/source_poster_region.png outputs/example/references/source_crop.png \
  --roles source_stage_2_fit_primary_poster_identity source_stage_2_fit_rough_location_hint \
  --prompt-file outputs/example/bootstrap/clean_prompt.txt \
  --output outputs/example/bootstrap/start_character.png \
  --seed 42 --width 768 --height 768 --steps 40
```

The bootstrap example deliberately labels the raw candidate as a rough location hint and supplies the isolated primary poster region as the identity reference. Raw candidates may contain clipped anatomy, labels, or neighbors and are not clean ground truth. For evolution, pass the actual current GLB render first and the Qwen-cleaned target illustration last, with matching roles:

```bash
.venvs/qwen/bin/python src/healthmon/qwen_runner.py \
  --images outputs/example/renders/three_quarter.png outputs/example/references/target_clean.png \
  --roles edit_base_primary_identity_three_quarter design_only_same_individual_future_stage \
  --prompt-file outputs/example/qwen/evolution_prompt.txt \
  --output outputs/example/qwen/evolved.png \
  --seed 42 --width 768 --height 768 --steps 40 --local-files-only
```

`image=[PIL.Image, ...]` is the official multi-image interface, with up to ten references. The adapter converts references to RGBA, explicitly prepends their ordered role declarations to the actual model prompt, uses `torch.bfloat16`, one image, a CUDA generator seeded to 42, and the original checkpoint's 40-step sampling. No unsupported `strength`, `guidance_scale`, transparency flag, or adapter weights are passed. `output_resolution`, verified in the pinned upstream signature, sets the reference image area target (768 by default) as well as the width/height fallback; the explicit output dimensions remain 768 square. Native RGBA output is requested through the documented prompt wording, not through an invented argument: `This is an RGBA image with transparency. ... The image has alpha channel and the background is transparent.`

The exact effective prompt is saved as `<output_stem>.effective_prompt.txt`. `<output>.json` records reference order/roles/paths/SHA-256, source prompt and exact effective prompt, seed, sampling options, pinned model revision, package versions, GPU, loading/inference duration, peak memory, output dimensions/mode/alpha statistics, and any failure traceback. `PASS` indicates technical image generation, while visual quality remains `REQUIRES_REVIEW` for the orchestrator's checks and human visual inspection.

The process exits after one image so Qwen allocations do not overlap with TRELLIS or rigging. `--memory-mode model-cpu-offload` is an available generic Diffusers fallback if the full BF16 pipeline does not fit; it retains the same checkpoint. VAE tiling is disabled by default at these conservative dimensions because the initial tiled run showed faint alpha seams. `--vae-tiling` opts into the official VAE API if needed for memory. The setting is recorded in metadata. All failed metadata and logs are retained.

## Single-subject evolution control

All four Blender views are preserved. `qwen_identity_views` selects which actual 3D renders enter editing; it participates in prompt and artifact fingerprints. The current default uses `three_quarter` as the sole edit base plus the cleaned target concept as design guidance for the same individual. This preserves actual 3D conditioning while reducing layout ambiguity.

The first real evolution call used front, quarter, side, and target references. It produced a four-creature contact sheet despite the single-creature request and was visually rejected in `rejected/evolution/attempt_1_contact_sheet/`. No panel was cropped and passed off as a successful single-creature inference. The retry explicitly requests one uninterrupted image, one body/head, one viewpoint, and forbids grids, panels and duplicated inputs. For Heavy Lucan it also requests exposed soft abdominal fat rather than concealed armor bulk. Automatic QC now rejects multiple substantial disconnected silhouettes before TRELLIS. Exact per-attempt prompts, roles, images, revisions, and rejection reasons remain auditable.

## Observed local execution

The resumed real 3D-conditioned evolution used the verified source GLB's quarter render and the preserved target cleanup as two ordered references. Attempt 2 produced one creature but insufficient body-fat change and was preserved as a visual rejection. Attempt 3 used the same checkpoint, references, seed 42, BF16, 768 square and 40 steps with a shorter explicit torso transformation prompt. Its output SHA256 is `3760d83229af95707f328c570b6dd438e218610859a32a256b0c2521ae13412c`; loading took 217.932 seconds and generation 37.812 seconds. Visual inspection confirmed a low protruding potbelly, rounded flanks, a larger pale mane, one complete creature and recognizable lineage. Facial maturation is moderate. It was accepted for real evolved-3D reconstruction with this limitation recorded in `validation/visual_review.json`. The original starting and target-cleanup PNGs remain unchanged.

The real Lucan Stage 2 edit ran on NVIDIA GB10 with the pinned BF16 checkpoint and completed all 40 steps at 768 square, seed 42. Its generation metadata is `outputs/lucan_stage2_to_stage3_seed42/bootstrap/start_character.png.json`: model loading 171.479 seconds, generation 38.929 seconds, peak CUDA allocation 36.175 GB, RGBA output with alpha extrema 0–255. This demonstrates actual Qwen execution on the existing ARM64/PyTorch CUDA 13 runtime despite the compute-capability warning. It does not establish success for TRELLIS, evolution from 3D, or rigging.

The generated character is centered and complete on a white alpha-composited preview, but has low-alpha background noise and faint regular tile seams. The original alpha>32 edge test flagged eight semitransparent pixels near the right boundary; edge alpha never exceeded 47, while the alpha>64 subject bounds were `[93, 66, 692, 669]`. Preserve the original output and review these artifacts rather than claiming perfect segmentation. Technical model inference and subsequent image quality checks are recorded separately in the run report. Diagnostic previews are in `bootstrap/diagnostics/`; they are alpha-composited inspection copies, not replacement model outputs.

The real Stage 3 target-design cleanup also completed with the same pinned model, 40 steps, seed 42, and VAE tiling disabled: `references/target_clean.png`, 180.549 seconds loading, 37.205 seconds generation, 39.058 GB peak allocation, RGBA alpha 0–255. Its automatic image checks passed. White-composited inspection shows one complete charcoal/gold guardian without visible labels or neighboring characters; narrow side margins (opaque bbox `[7, 89, 761, 660]`) still warrant review. The untiled output has no visible tile grid, and its right-edge alpha maximum is 3. This is cleanup of a target-design reference, **not** evidence of evolution conditioned on an actual generated 3D model.
