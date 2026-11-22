# Qwen3.5-4B migration candidate

The official model is `Qwen/Qwen3.5-4B`, revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. The user's Ollama copy is GGUF;
training uses a separate official safetensors download. Ollama files are unchanged.

## Preserved contract and scope

`src/prompts.py::messages(context, text)` is used by both training and inference.
It preserves personality expression guidance, recent dialogue, retrieved memories,
activity facts and server quest candidates. `src/agent.py` still validates the same
speech/emotion/animation/action/memory_ids/personality_update JSON. Only assistant
target tokens receive training loss. Context is never silently truncated.

The Unity common-server route also uses `Server/local_probe/gpu_gateway.py`, with
three personality axes and a `classification` output. A second training stage uses
that module's unchanged `projected_messages(full_personality_facts=True)` plus
legacy replay examples. Its loader now accepts the explicitly selected
`qwen4b-v1` bundle and NF4; default 9B versions and precision remain unchanged.
The existing 9B LoRA checkpoint and private deployed server configuration have not
been provided. `config/serving.json` remains unchanged. A completed candidate is
not proof of 9B parity or live Unity APK connectivity.

## Data

`data/qwen4b_candidate_v1`: 216 existing Healthmon training records plus 29
individually agent-reviewed reactive AI Hub 71302 turns. Original conversation IDs,
archive paths and SHA256 hashes are recorded. Human biographies are not converted
into pet facts. AI Hub turns have neutral display labels supplied by the agent;
they do not have human-reviewed emotion labels. They are a small supplementary
sample, not full-dataset training. The existing 43-example development validation
is byte-identical and never used for gradient updates. Historical final cases are
not used by the training script. Human semantic review is still needed.

`data/qwen4b_common_v2` adds 43 agent-authored common-server examples, with 48
original training records replayed to retain the earlier JSON contract. There are
six new common-server development validation cases plus the original 43. This is
not teacher distillation from the missing 9B checkpoint. The rejected draft
`qwen4b_common_v1` contains duplicate all-neutral prompts and was never trained.

## Commands (from the outer workspace directory)

```powershell
$py = '.runtime/qwen4b-venv/Scripts/python.exe'
$llm = 'healthmon-capstone-feature-dd/Ai/LLM'
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'

# Use a new output/run directory for every experiment.
& $py "$llm/scripts/prepare_qwen4b_data.py" --aihub-root 'C:/Users/user/Desktop/capstone/044.페르소나 대화' --output "$llm/data/qwen4b_candidate_v1"
& $py "$llm/scripts/train_qwen4b.py" --data "$llm/data/qwen4b_candidate_v1" --run "$llm/runs/qwen4b-candidate-v1" --epochs 1
& $py "$llm/scripts/evaluate_qwen4b.py" --output "$llm/runs/qwen4b-evaluation/base-validation.json"
$selected = (Get-Content "$llm/runs/qwen4b-candidate-v1/selection.json" -Raw | ConvertFrom-Json).selected.path
& $py "$llm/scripts/evaluate_qwen4b.py" --adapter $selected --output "$llm/runs/qwen4b-evaluation/lora-validation.json"
```

The actual first stage stopped after its first complete epoch using `stop.request`
so training could continue on the APK common-server contract. For that stage:

```powershell
& $py "$llm/scripts/train_qwen4b.py" --data "$llm/data/qwen4b_common_v2" --run "$llm/runs/qwen4b-common-v1" --init-adapter "$llm/runs/qwen4b-candidate-v1/checkpoint-epoch-1" --epochs 2 --final-only-validation
& $py "$llm/scripts/final_validate_qwen4b.py" --run "$llm/runs/qwen4b-common-v1" --output "$llm/runs/qwen4b-final-validation-v1"
```

Per user request, stage two has no intermediate evaluation: the final epoch is
selected, then validation runs once as a final batch. The batch includes unit
checks, real legacy/common generations and, if the common contract passes, the
real authenticated FastAPI inference endpoint. It does not retrain or retry the
whole evaluation to hide failures. Individual requests retain the server's
existing bounded repair behavior. The batch is not a live Unity APK test.

For a common-server private configuration, select the final adapter with
`expected_model_version: "qwen4b-v1"`, `expected_model_mode: "lora"`,
`quantization: "nf4"`, and `full_personality_facts: true`. Preserve the existing
server token, BGE path, database, router, and Unity API URL. The base path is
`Ai/LLM/models/qwen3.5-4b`. Use the adapter path from the second stage's
`selection.json`. Only a completed successful common evaluation can create its
`healthmon-model.json` bundle manifest.

Do not rerun the preparation command against the existing data directory. The
training command creates fresh LoRA weights on 4B, not an initialization from the
9B adapter. NF4 double quantization with BF16 compute fits the 12GB GPU; frozen
vision weights are not trained. Rank 8, alpha 32, LR 5e-5, batch 1 with accumulation
8, maximum two epochs and validation-loss early stopping are the initial settings.
The selected adapter is reloaded and its validation loss checked before completion.

To explicitly launch the original LLM API after supplying its real DB/auth config
and existing BGE-M3 embedding model:

```powershell
& "$llm/scripts/serve_qwen4b.ps1" -Python (Resolve-Path $py) -EnvFile 'PATH/TO/.env' -EmbeddingPath 'PATH/TO/bge-m3' -Run 'runs/qwen4b-common-v1'
```

This command requires the existing database; it is not an Ollama import command.
The embedding model/retrieval and server state rules remain separate from Qwen.
To return to 9B, use its original model and adapter paths with `--quantization none`.
Never attach a 9B LoRA to the 4B base. The loader checks base identity before GPU use.

## Evidence

Run `metrics.jsonl`, `config.json`, `selection.json` and evaluation JSON files are
the source of truth for actual completion and observed quality. Smoke training is
only a two-record execution check. Raw contract validity is not semantic accuracy.
No live Unity/API integration or 9B comparison can be inferred from offline scores.
