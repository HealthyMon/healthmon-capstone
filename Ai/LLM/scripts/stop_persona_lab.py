"""Stop only the recorded worker belonging to this project's Persona Lab."""
import sys
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]
record = ROOT / 'runs/persona-lab/server.pid'
if not record.exists():
    raise SystemExit('No recorded Persona Lab worker')
try:
    process = psutil.Process(int(record.read_text().strip()))
    command = process.cmdline()
    correct_script = any(Path(part).name == 'serve_persona_lab.py' for part in command)
    correct_directory = Path(process.cwd()).resolve() == ROOT
    if not correct_script or not correct_directory:
        raise SystemExit('Recorded PID is not this project Persona Lab; left unchanged')
    process.terminate()
    process.wait(20)
    print('Persona Lab worker stopped; data retained')
except psutil.NoSuchProcess:
    print('Recorded Persona Lab worker is already stopped')
