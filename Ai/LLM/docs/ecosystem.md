# Unity, Vision and Qwen

The current repository on `ai/3d` contains Unity, LLM, Vision and Generation3D. See [shared setup](../../../Docs/LOCAL_DEVELOPMENT.md).
Unity uses one authenticated session, pet ID and state version for dialogue and food.
Qwen keeps the existing CUDA environment, base weights, selected LoRA and PostgreSQL data.
Opening the dialogue tab loads Qwen once. Its separate CUDA process stays alive for
successive messages while that tab remains open. Leaving the tab, pausing the app, or
starting Vision ends that conversation lease and releases the process and GPU allocations.
Unity renews the lease every 20 seconds; a missing heartbeat expires after 90 seconds.
A close cancels an unfinished preload. A generation already running finishes before
its process exits; neither path can resurrect the closed tab. Only one model job runs at a time. BGE and Vision
remain one-shot workers. Food reactions outside the dialogue tab also unload Qwen after
their single response. The API and PostgreSQL stay running. No weights are copied.

## Start

Prepare Vision once, if its environment is absent:

```powershell
Set-Location E:\qwen-llm\healthmon-unity-desktop
& E:\qwen-llm\.venv\Scripts\python.exe Ai\LLM\scripts\setup_vision.py
```

Start the API and open the existing team scene with one command:

```powershell
& E:\qwen-llm\.venv\Scripts\python.exe Ai\LLM\scripts\launch_ecosystem.py
```

Use `--pet PET_ID` to continue a specific pet. Otherwise the launcher selects an owned pet with a registered 3D starter model. A new starter must be validated and registered before opening Unity.
Press Play. Credentials pass to Unity in process memory; scenes contain no tokens.
`/health` uses `model_lifecycle=conversation_session`. `loaded=true` is expected between
messages inside the dialogue tab; it becomes false after closing the tab or switching to
Vision. `/ecosystem/health` distinguishes a current job (`active_model`) from the retained
conversation model (`conversation_active`, `resident_model`). The old `--warmup` flag
does not preload Qwen before opening dialogue.

## Food and conversation

1. Open the food tab. Capture a photo on the mobile AR device, or use **PC 사진 선택** in the Editor.
2. Analyze the photo. The three candidate buttons display actual model names and confidence.
3. Select the correct candidate. Nutrients show the entered quantity, or clearly marked 100g reference values.
4. The optional grams field starts with the model's estimate when available. Correct it to the amount actually eaten; leave it empty when unknown.
5. Confirm consumption. The server saves one user-reported meal and updates the shared state version.
6. The same pet reacts through the actual Qwen API; open the dialogue tab to see the response or ask about the recorded food.

Analysis alone never records consumption. Confirm retries cannot add the same meal twice.
Unknown nutrient values remain unavailable, not zero-calorie claims. Without grams, total
consumed nutrients remain unknown. User confirmations retain `source=user`; existing
sensor/backend evidence and reward rules remain authoritative. Food diary progress in the
Unity prototype is updated only after a successful save.
If a model job is already running, another request returns 503 instead of loading a second
model. Qwen startup and each generation have 150-second deadlines; embedding has 60 seconds. A timed-out
worker and its owned children are stopped. Unity retains the request ID and exposes
**다시 시도**; explicit state conflicts refresh state before reusing that same ID.
Idle model unloading does not guarantee that any size of 3D scene and a 9B model can fit
simultaneously during inference; that peak still needs testing with the final 3D assets.
Before loading Qwen, its worker checks that free VRAM covers the weight files plus a
1.5 GiB workspace reserve. When it cannot fit, the request fails without evicting Unity assets.

## API

All routes use the same Bearer authentication as `/pets/{pet}/chat`.

| Route | Contract |
| --- | --- |
| `GET /ecosystem/health` | Vision configuration/worker status and contract versions |
| `POST /pets/{pet}/chat-session` | JSON `session_id` (32 lowercase hex characters), `active`; preload/keep or close the authenticated conversation lease |
| `POST /pets/{pet}/chat-session/heartbeat` | JSON `session_id`; renew the same active lease, without reopening a closed tab |
| `POST /pets/{pet}/food/analyze` | Raw JPEG or PNG body, up to 12 MiB and 16 megapixels; returns `healthmon.food.v1`, analysis ID and up to three candidates |
| `POST /pets/{pet}/food/confirm` | JSON `analysis_id`, `candidate_id`, optional positive `grams` up to 10000; returns saved record and current state version |
| `GET /pets/{pet}/food/records` | Latest 50 valid confirmed meal records for that pet |

The server derives names and nutrients from its saved analysis; clients cannot submit
invented nutrients. Ownership is checked before model work and again before persistence.
Photos are temporary and removed after inference. Analysis/confirmation metadata persists
in the additive `003_food_analyses.sql` table; meal evidence uses existing activity sources.
Deleting a meal invalidates it for conversation/history; replaying its old confirmation
returns 410 instead of restoring it.

The API binds to localhost by default. Desktop Editor integration is the local target;
running the AR camera on a physical phone additionally needs a reachable deployment URL
and device validation. No camera/firewall permissions are changed by these scripts.

## Diagnostics

API launcher logs: `E:\qwen-llm\runs\ecosystem`.
Vision worker log: `Ai/LLM/runs/vision-worker.log`.
Verification evidence: `E:\qwen-llm\diagnostics\ecosystem-20261013`.
The pre-migration database backup is in `E:\qwen-llm\backups\ecosystem-20261013`.
The Python API tests use an isolated test database and controlled failures; actual Vision,
Qwen and Unity Play verification are recorded separately.

Chat loads BGE only when saving an explicit durable preference/goal or searching existing
valid memory vectors. Ordinary conversation and meal facts use their existing context.
Deletion commands do not load either model. A conversation keeps only Qwen resident;
each message still reconstructs its current authenticated pet context without shared history caches.
Response `metrics.timings` separates embedding, runtime imports, tokenizer, base weights,
adapter, generation and the full worker round trip. `server_seconds` covers request handling
through the final write, excluding its last commit/network delivery. `latency_seconds` is
generation/validation time alone and must not be shown as the entire user wait.
`generation_attempt_seconds` and privacy-safe `failure_codes` identify a second generation
caused by repetition or output validation. Timing logs contain no user dialogue.
Retained conversation replies report `conversation_reused=true` and `model_load_seconds=0`.

`EcosystemVerification.Run` is an Editor verification entry point. It uploads the supplied
real image through the scene's client, selects the first candidate, confirms it, waits for
the Qwen reaction, and writes a result report. It does not save scene changes or credentials.
