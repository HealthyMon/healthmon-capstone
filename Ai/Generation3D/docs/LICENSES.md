# Sources, checkpoints and dependency licenses

Reviewed for this university research proof of concept on 2026-10-10 (Asia/Seoul). This is a record of retrieved terms, not a clearance for commercial distribution. Keep the applicable license files with any covered material you redistribute.

| Component | Source / terms inspected | Consequence for this experiment |
| --- | --- | --- |
| Qwen-Image-2.1 code and weights | [Official repository](https://github.com/QwenLM/Qwen-Image-2.1), [checkpoint](https://huggingface.co/Qwen/Qwen-Image-2.1), archived `QWEN_MODEL_LICENSE.txt` | Qwen Research License, noncommercial research/evaluation; commercial use requires separate permission. The license also contains attribution/redistribution conditions. |
| TRELLIS.2 code and model | [Official repository/license](https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE), [official model](https://huggingface.co/microsoft/TRELLIS.2-4B) | MIT for TRELLIS materials; retain notice. This does not override restrictions on conditioning/removal models and dependencies. |
| DINOv3 conditioning backbone | [Official checkpoint](https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m) | Custom DINOv3 license and access gate; user must obtain access under its conditions. No approval is inferred from public metadata. |
| RMBG-2.0 | [Official checkpoint and model card](https://huggingface.co/briaai/RMBG-2.0) | Official model card currently specifies CC BY-NC 4.0 (noncommercial with attribution) and access gating. The official TRELLIS alpha preprocessing path does not invoke it for usable RGBA input; opaque inputs would require it. |
| RigAnything code and weights | [Official repository](https://github.com/Isabella98Liu/RigAnything), local `vendor/RigAnything/LICENSE.md` and official weight repository license | Adobe Research License: noncommercial academic research/teaching; retain notices and inspect redistribution conditions. A future product release needs separate review/permission. |
| Blender | Blender ARM Debian/Ubuntu bundle, package copyright/license files | GPL software. Its license is distinct from the licensing of imported artwork/model weights. |
| Diffusers / Transformers | Pinned upstream source and installed package metadata | Apache-2.0; retain required license/NOTICE where applicable. |
| PyTorch / NumPy / SciPy / Pillow | Installed package license metadata and included license texts | BSD-family / Pillow permissive terms; preserve applicable notices. |
| CuMesh / O-Voxel / FlexGEMM / nvdiffrast / FlashAttention / utils3d | Exact source/binary provenance in `docs/TRELLIS.md`, `logs/trellis/setup.json`, installed distribution metadata and vendor licenses | CuMesh/O-Voxel/FlexGEMM use MIT. nvdiffrast and FlashAttention carry separate upstream terms. Retain each license; package import does not establish that its GPU kernels ran on this asset. |
| easydict | Installed license metadata in `logs/rigging_preflight/dependency_licenses.json` | LGPL-3.0; include applicable notices and inspect redistribution requirements for any packaged runtime. |
| HEALTHMON ZIP images | User-supplied reference pack README and manifest | Previous concept drafts, explicitly not confirmed canonical starter artwork. No third-party commercial creature artwork is introduced as replacement. |

UniRig was considered as the requested alternative but is not selected when the primary RigAnything checkpoint loads. Its cached presence is not evidence that it was used for the HEALTHMON run.

Exact model revisions and environment package versions are recorded separately in the per-model setup and generation reports. No model weights or access tokens belong in source control. A research license or publicly readable model card must not be described as an unrestricted commercial license.

## Upload review — 2026-10-18

The GitHub export excludes server-wide Docker inventory data, models, vendor implementations, personal assets and runtime output. Official model licenses were reviewed separately before the private backup. Qwen and RigAnything retain noncommercial research restrictions; license copies and attribution accompany the backup. The private model repository is https://huggingface.co/emc2square/healthmon-3d-models and is not an inference service. DINOv3 materials require the DINOv3 license and Built with DINOv3 attribution. Public readability or a private backup does not remove model license conditions.
