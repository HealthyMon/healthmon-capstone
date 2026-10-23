"""Container-side phases. Invoked only by the operator-gated GPU worker."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'runtime/unity'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['plan','image','evolution_check','reconstruction'])
    parser.add_argument('--job-id',required=True)
    args=parser.parse_args()
    folder=ROOT/'outputs/common_gateway/work'/args.job_id
    if not folder.resolve().is_relative_to((ROOT/'outputs/common_gateway/work').resolve()): raise ValueError('Invalid job path')
    value=json.loads((folder/'request.json').read_text(encoding='utf-8'))
    parent=value['parent']
    image=ROOT/'outputs/common_gateway'/parent['image_relative']
    job={'target_stage':value['input']['input']['stage'],'source_stage':parent['stage'],
         'source_revision':parent['revision'],'seed':42,'stats':value['stats'],
         'game_contract':'healthmon.v2.2',
         'authoritative_state':value['input']['input']['state'],
         'authoritative_profile':value['input']['input']['profile']}
    import evolution_worker as existing
    if args.phase=='plan': existing.plan_from_parent(folder,job,image,parent)
    elif args.phase=='image': existing.image(folder,job)
    elif args.phase=='evolution_check': existing.evolution_check(folder,job)
    else: existing.reconstruct(folder,job)


if __name__=='__main__': main()
