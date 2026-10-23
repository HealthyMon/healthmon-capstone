# Desktop Qwen + team Unity

The integrated food-analysis and dialogue workflow is documented in [Unity, Vision and Qwen](ecosystem.md).
Use `scripts/launch_ecosystem.py` to start the shared API and open Unity with one command.

Work in the current repository on `ai/3d`. Unity, Vision, LLM and Generation3D use the same checkout. See [shared local setup](../../../Docs/LOCAL_DEVELOPMENT.md).

## Run

In PowerShell:

```powershell
Set-Location E:\qwen-llm\healthmon-unity-desktop
& E:\qwen-llm\.venv\Scripts\python.exe .\Ai\LLM\scripts\start_desktop.py
```

Leave the API terminal open. In another terminal:

```powershell
Set-Location E:\qwen-llm\healthmon-unity-desktop
& E:\qwen-llm\.venv\Scripts\python.exe .\Ai\LLM\scripts\open_unity_desktop.py
```

The launcher opens `Assets/HealthMon/Scenes/MainARScene.unity` with Unity 6000.4.6f1 and passes the existing local user token to the Editor process in memory. Press Play, then select the existing **대화** tab. When a runtime token is present, Play calls the same real API `Connect()` automatically. The `DialogueManger` Inspector also has a manual **Connect** button. Use the existing input and **보내기** button. Tokens are not serialized into the scene or committed.

The API uses the existing runtime resources outside the clone:

- Python: `E:\qwen-llm\.venv\Scripts\python.exe`
- Credentials: `E:\qwen-llm\.env`
- Model: `E:\qwen-llm\models\qwen3.5-9b`
- Selected LoRA: `E:\qwen-llm\runs\expanded-20260929\checkpoint-epoch-1`
- BGE-M3: `E:\qwen-llm\models\bge-m3`
- Existing PostgreSQL data: `E:\qwen-llm\runtime\pgdata`, localhost port 55432

`start_desktop.py` selects the adapter from `config/serving.json`, warms up the actual model, and binds the API to `127.0.0.1:8000`. It reuses an already running matching server. It never initializes a new database. No demo server is involved. Python launchers also work when PowerShell script-file execution is restricted.

Chat goes through authenticated `POST /pets/{pet_id}/chat`; the existing character response text displays `response.speech` from the server. Connection/loading/error text is UI status. `ChatDisplayed` in the Unity Console records the request ID and server metrics. `fallback=False` with `attempts=1` identifies a successful model generation; a fallback response is marked as a generation failure.

## Git routing

- `origin`: `https://github.com/KORemc2/healthmon-capstone.git`
- `team`: `https://github.com/HealthyMon/healthmon-capstone.git`
- Local `remote.pushDefault=origin`, `branch.ai/llm.pushRemote=origin`, `push.default=current` make plain `git push` push `ai/llm` to the fork.
- Local `git pr` opens the team's PR comparison with head `KORemc2:ai/llm` and base `feature/unity` (the branch containing the team UI). It does not submit or merge a PR.

After committing the intended source files:

```powershell
git push
git pr
```

Use `git pr --base develop` if the team requests a different destination branch. `git pr --print-url` prints the destination without opening a browser. The local alias uses the existing desktop Python runtime. GitHub CLI, if installed, also recognizes the local team remote as the default PR repository; an explicit equivalent is:

```powershell
gh pr create --repo HealthyMon/healthmon-capstone --base feature/unity --head KORemc2:ai/llm
```

No push or PR creation was performed during setup. A `git push --dry-run` attempt was blocked by missing GitHub HTTPS authentication on this PC. Authenticate Git before using `git push`; the fork routing is already configured. Models, adapters, `.env`, tokens, database files and local verification output remain outside Git.

## Verified and remaining

On this desktop, model warmup, CUDA inference, authenticated API generation, BGE-M3 encoding, PostgreSQL/pgvector, Unity Play-mode Connect and the existing input/send/response UI were verified. A Unity request (`2cdb42ce2f7446c9bdec3250388c0e0d`) returned `fallback=False`, `attempts=1`, latency 7.89 seconds and displayed the generated reply in the existing scene. Local evidence is in `E:\qwen-llm\diagnostics\desktop-unity-20261012`.

PC AR provider/camera warnings are separate from chat; real mobile AR photo capture was not verified. The existing `test_serving_config.py` default test assumes model artifacts inside the clone and fails without them; desktop serving uses verified external absolute paths instead. The precedence test passes. Unity imported the integration and entered Play successfully.
