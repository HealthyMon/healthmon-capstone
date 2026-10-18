"""Adjust generated local runtime only; keep the original config unchanged."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / 'configs/runtime.local.json'
config = json.loads(path.read_text())
if not config.get('_healthmon_generated_runtime'):
    raise SystemExit('Refusing to edit a non-generated configuration.')
config['trellis_low_vram'] = False
path.write_text(json.dumps(config, indent=2) + '\n')
print('TRELLIS: keep models on GPU to avoid CPU offload allocation peak.', flush=True)
