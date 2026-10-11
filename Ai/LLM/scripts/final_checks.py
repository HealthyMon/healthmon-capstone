"""Sequential GPU checks; preserves every earlier evaluation artifact."""
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
commands=[['scripts/compare_adapters.py'],['scripts/regression_real.py']]
for args in commands:
    print('START',args,flush=True)
    subprocess.run([sys.executable,'-u',*args],cwd=ROOT,check=True)
print('FINAL_CHECKS_COMPLETE',flush=True)
