"""Verify versioned data and frozen evaluation bytes after clone or checkout."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    checked=[]
    for version in ('improvement_v3','natural_sft_v1'):
        directory=ROOT/'data'/version
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        for name,expected in manifest['sha256'].items():
            actual=hashlib.sha256((directory/name).read_bytes()).hexdigest()
            if actual!=expected:raise ValueError('Dataset bytes changed: '+version+'/'+name)
            checked.append(version+'/'+name)
    evaluation=ROOT/'data/natural_eval_v1'
    manifest=json.loads((evaluation/'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((evaluation/'cases.json').read_bytes()).hexdigest()!=manifest['sha256']:
        raise ValueError('Frozen evaluation bytes changed')
    checked.append('natural_eval_v1/cases.json')
    print(json.dumps({'passed':True,'checked':checked},indent=2))


if __name__=='__main__':main()
