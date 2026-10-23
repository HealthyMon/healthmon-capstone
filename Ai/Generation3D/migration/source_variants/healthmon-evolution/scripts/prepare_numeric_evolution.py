#!/usr/bin/env python3
"""Automatically enqueue score-derived evolution on a crossed level milestone."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import prepare_branch_evolution as helper

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from healthmon.numeric_router import compile_for_species as compile_numeric_evolution
from healthmon.numeric_source_guard import verify_numeric_parent


def prepare_profiles(profiles_path, run):
    profiles_path = Path(profiles_path).resolve()
    run = Path(run).resolve()
    helper.RUN = run
    config = json.loads(profiles_path.read_text())
    tasks = []
    skipped = []
    for index, item in enumerate(config['profiles']):
        profile = {key: item[key] for key in ('species','previous_level','level','previous_form','records','personality')}
        compiled = compile_numeric_evolution(profile)
        if compiled is None:
            skipped.append({'case_id':item['case_id'],'reason':'No25-level milestone crossed; no inference queued'})
            continue
        parent = ROOT/item['previous_image']
        meta = json.loads(Path(str(parent)+'.json').read_text())
        parent_validation=verify_numeric_parent(parent,meta,profile)
        with helper.Image.open(parent) as source_image:
            box=item['face_box']
            if len(box)!=4 or not (0<=box[0]<box[2]<=source_image.width and 0<=box[1]<box[3]<=source_image.height):
                raise ValueError('Identity crop must be entirely within its actual previous image')
        crop = helper.identity_crop(parent,item['case_id']+'_previous_central_face',tuple(item['face_box']))
        conditions = {**compiled, 'profile_id':item['case_id'],'label_ko':item['label_ko'],
            'species':profile['species'], 'source_stage':compiled['transition']['source_stage'],
            'target_stage':compiled['transition']['target_stage'],'target_level':compiled['transition']['level'],
            'form':compiled['decision']['form'],'branch':compiled['decision']['branch'],
            'full_previous_source':str(parent),'full_previous_source_sha256':helper.sha(parent),
            'conditioning_mode':'One actual previous central-face identity crop; no target-stage or target-form reference',
            'target_design_reference_count':0,'full_body_target_reference_count':0,
            'body_history_inheritance':'Textual; actual preceding full-body geometry is not an image condition',
            'parent_stage_and_form_validation':parent_validation,
            'automatic_visual_pass':False,'trellis_or_rigging':False}
        conditions.pop('prompt')
        helper.save(run/'compiled'/f"{item['case_id']}.json",compiled)
        task = helper.enqueue(item['case_id'],compiled['prompt'],[crop],
            [f"actual_previous_{profile['species']}_central_face_identity_only"],conditions,order=index)
        tasks.append(task)
    helper.save(run/'input_profiles.json',config)
    helper.save(run/'plan.json',{'purpose':'Actual numeric-input-controlled sacred evolution comparison',
        'profile_source':str(profiles_path),'profile_source_sha256':helper.sha(profiles_path),
        'prepared_inferences':len(tasks),'cases':[t['case_id'] for t in tasks], 'skipped':skipped,
        'same_seed':42,'target_stages':sorted({t['conditions']['target_stage'] for t in tasks}),'training':False,'trellis_or_rigging':False,
        'inference_path':'numeric_evolution.compile_numeric_evolution -> this score-driven enqueue -> qwen_branch_worker -> actual diffusers QwenImage21Pipeline',
        'preparer_sha256':helper.sha(Path(__file__))})
    return {'run_dir':str(run),'prepared':len(tasks),'skipped':len(skipped)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare_profiles(args.profiles,args.run_dir),ensure_ascii=False))

if __name__=='__main__':
    main()
