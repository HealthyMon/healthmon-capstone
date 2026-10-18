"""Stop only this project's recorded uvicorn worker, never a generic Python process."""
import psutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
pid=int((ROOT/'runs/server-worker.pid').read_text())
process=psutil.Process(pid)
if Path(process.cwd()).resolve()!=ROOT:raise RuntimeError('Worker cwd mismatch')
if not any('scripts/serve.py' in arg.replace('\\','/') for arg in process.cmdline()):raise RuntimeError('Not the Healthmon server')
children=process.children(recursive=True)
process.terminate()
for child in reversed(children):
    try:child.kill()
    except psutil.NoSuchProcess:pass
psutil.wait_procs(children,timeout=10)
process.wait(timeout=30)
print(f'Stopped verified Healthmon worker {pid}')
