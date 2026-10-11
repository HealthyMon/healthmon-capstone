"""Verify the recorded original-artifact hashes without rewriting originals."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'runs/improvement-20260929'
manifest=json.loads((D/'preservation-sha256.json').read_text(encoding='utf-8'))
failures=[]
for name,expected in manifest.items():
    path=ROOT/name
    if not path.is_file():
        failures.append({'path':name,'reason':'missing'});continue
    with path.open('rb') as f:
        digest=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        actual=digest.hexdigest()
    if actual!=expected:failures.append({'path':name,'reason':'hash mismatch'})
result={'checked_files':len(manifest),'unchanged':not failures,'failures':failures,
        'scope':'Recorded original snapshots, pilot data, pilot checkpoints and historical evaluations; not a hash of the live DB.'}
(D/'preservation-verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(bool(failures))
