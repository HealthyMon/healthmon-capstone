"""Verify locally downloaded safetensors against index, without duplicating weights."""
import hashlib,json,sys
from pathlib import Path
from safetensors import safe_open
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'models/qwen3.5-9b'
index=json.loads((folder/'model.safetensors.index.json').read_text());expected=index['weight_map'];found=set();sizes={}
for name in sorted(set(expected.values())):
    path=folder/name;sizes[name]=path.stat().st_size
    with safe_open(path,framework='pt',device='cpu') as f:
        keys=set(f.keys());assert {k for k,v in expected.items() if v==name}<=keys;found|=keys
assert set(expected)<=found
report={'passed':True,'revision':json.loads((ROOT/'config/qwen3.5-9b.json').read_text())['revision'],
        'indexed_tensors':len(expected),'shards':sizes,'total_bytes':sum(sizes.values())}
(ROOT/'runs/model-integrity.json').write_text(json.dumps(report,indent=2));print(report)
