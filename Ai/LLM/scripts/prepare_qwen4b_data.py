"""Build a traceable candidate set; preserve historical validation/final files.

AI Hub additions are individually agent-reviewed short reactive turns, not raw
human persona profiles. They do not teach the pet a human biography. No human
review or comprehensive AI Hub benchmark is claimed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.contracts import ModelOutput

# Reviewed from the user's local AI Hub 71302 Training labeling archives.
REVIEWED = set('''BP22013021.2 BP22013859.19 BP22005350.10 BP22021931.10
BP22038087.16 BP22019143.18 BP22026510.9 BP22027711.8 BP22006102.14
BP22014019.3 BP22034076.16 BP22023297.10 BP22006786.15 BP22033894.8
BP22013917.2 BP22003358.15 BP22007270.13 BP22035320.11 BP22034499.12
BP22000700.5 BP22001510.3 BP22004289.2 BP22018390.4 BP22013165.13
BP22019697.10 BP22006519.10 BP22014285.9 BP22026864.12
BP22006955.17'''.split())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(aihub_root, destination):
    if destination.exists():
        raise ValueError('Choose a new dataset directory')
    old = ROOT / 'data/improvement_v3'
    train = [json.loads(x) for x in (old/'train.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    base_context = deepcopy(train[0]['context'])
    base_context['settings'].update(speech_level='formal', profanity='none')
    base_context['recent'] = []
    base_context['memories'] = []
    found, provenance, additions = set(), [], []
    for archive in sorted(aihub_root.rglob('TL_*.zip')):
        used = False
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                if not member.endswith('.json'):
                    continue
                doc = json.loads(z.read(member))
                for index, turn in enumerate(doc['utterances']):
                    ident = turn['utterance_id']
                    if ident not in REVIEWED:
                        continue
                    if index < 1 or ident in found or doc['info']['evaluation']['avg_rating'] < 4.5:
                        raise ValueError('Reviewed source changed: '+ident)
                    previous = doc['utterances'][index-1]
                    if previous['persona_id'] == turn['persona_id']:
                        raise ValueError('Expected alternating speakers')
                    answer = ModelOutput(speech=turn['text'], emotion='neutral', animation='idle',
                        action={'type':'none','target_id':None}, memory_ids=[], personality_update=None).model_dump()
                    additions.append({'sample_id':'aihub71302:'+ident, 'scenario_group':'aihub71302:'+doc['info']['id'],
                        'source':'AI Hub 71302 local licensed copy', 'source_archive':archive.name,
                        'source_member':member, 'source_id':ident, 'context':deepcopy(base_context),
                        'user_text':previous['text'], 'answer':answer,
                        'review':{'semantic':'agent_reviewed', 'human':'not_reviewed',
                                  'note':'Reactive pair only; no speaker persona or fabricated memory labels. Neutral display labels added by agent.'}})
                    found.add(ident)
                    used = True
        if used:
            provenance.append({'file':str(archive), 'sha256':sha(archive)})
    if found != REVIEWED:
        raise ValueError('Missing reviewed AI Hub records: '+str(REVIEWED-found))
    destination.mkdir(parents=True)
    combined = train + sorted(additions, key=lambda r:r['sample_id'])
    (destination/'train.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in combined),encoding='utf-8')
    (destination/'validation.jsonl').write_bytes((old/'validation.jsonl').read_bytes())
    manifest = {'counts':{'train':len(combined),'healthmon_train':len(train),'aihub_train':len(additions),
                          'validation':len((old/'validation.jsonl').read_text(encoding='utf-8').splitlines())},
                'sha256':{name:sha(destination/name) for name in ('train.jsonl','validation.jsonl')},
                'aihub_archives':provenance, 'human_review':False, 'historical_final_used_for_training':False,
                'prompt_contract':'Ai/LLM/src/prompts.py messages(context,user_text)',
                'scope':'Candidate for original LLM API; common-server classification training is a separate contract.'}
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest['counts']))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--aihub-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    build(a.aihub_root,a.output)
