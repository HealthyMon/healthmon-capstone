#!/usr/bin/env python3
"""Prepare a small creative branching evolution trial from existing Lucan assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'outputs/branch_evolution'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text() != text:
        raise ValueError(f'Existing evidence differs; use a new case ID: {path}')
    path.write_text(text)


def enqueue(case, prompt, images, roles, conditions, *, order, cfg=1.0, size=1024):
    for folder in ('images', 'prompts', 'queue', 'references', 'logs'):
        (RUN / folder).mkdir(parents=True, exist_ok=True)
    prompt_path = RUN / 'prompts' / f'{case}.txt'
    value = prompt.strip() + '\n'
    if prompt_path.exists() and prompt_path.read_text() != value:
        raise ValueError(f'Existing prompt differs: {case}')
    prompt_path.write_text(value)
    task = {'case_id': case, 'group': 'creative_branch_evolution', 'images': list(map(str, images)),
            'roles': roles, 'prompt_path': str(prompt_path), 'output': str(RUN/'images'/f'{case}.png'),
            'seed': 42, 'parameters': {'width': size, 'height': size, 'output_resolution': size,
                                     'num_inference_steps': 40, 'true_cfg_scale': cfg},
            'negative_prompt': ('cropped body, head portrait only, multiple characters, comic panels, text, arrows, duplicated legs, body covered in thick armor' if cfg > 1 else None),
            'conditions': conditions}
    save(RUN/'queue'/f'{order:03d}_{case}.json', task)
    return task


def identity_crop(source, case, box):
    target = RUN/'references'/f'{case}_identity_head.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        crop = im.convert('RGBA').crop(box)
        if not target.exists():
            crop.save(target)
    save(target.with_suffix('.json'), {'purpose': 'Input reference only; never a generated evolution output',
        'source': str(source.resolve()), 'source_sha256': sha(source), 'crop_box_xyxy': list(box),
        'output': str(target), 'output_sha256': sha(target),
        'body_conditioning_note': 'Crop deliberately excludes most of the old torso, legs and pose; body-history inheritance is textual in this experimental mode.'})
    return target


def prepare():
    cfg = json.loads((ROOT/'configs/branch_evolution.json').read_text())
    source = ROOT/'outputs/diversity_evaluation/images/base_stage1_clean.png'
    crop = identity_crop(source, 'common_stage1', (235, 65, 712, 494))
    tasks = []
    for i, (name, profile) in enumerate(cfg['profiles'].items()):
        prompt = f'''Create one original HEALTHMON Lucan at its SECOND evolutionary stage, the level50 milestone after its juvenile level25 form. Design an entirely new complete evolved body around the inherited species identity in the reference head.
Inherited lineage: charcoal canine fur, amber eyes, pale muzzle and chest, pointed ears, gold forehead crest and a gold tail accent. Let the muzzle and face mature to adolescent proportions; the face need not remain identical to the juvenile. The reference supplies identity colors and facial motifs; its cropped framing is not the output framing.
EVOLVED BODY DESIGN: {profile['anatomy']}
EXPRESSION AND CHARACTER: {profile['expression']}
Life history informing this evolution: {profile['history']}
Draw the complete new creature in an unobstructed side-biased three-quarter standing view, exactly one head, one quadrupedal body, four distinct paws and a complete tail. Render a polished appealing fantasy-creature concept with readable anatomy and a clear overall silhouette. Keep ample margin around every appendage. Plain transparent or white studio background, no labels, props, diagrams or panels.'''
        conditions = {'species': 'lucan', 'source_stage': 1, 'target_stage': 2, 'source_level': 25, 'target_level': 50,
                      'branch': name, 'health': profile['health'], 'personality': profile['personality'],
                      'history': profile['history'], 'full_previous_source': str(source), 'full_previous_source_sha256': sha(source),
                      'conditioning_mode': 'previous-head-identity-only', 'target_design_reference_count': 0,
                      'evaluation_type': 'creative design demonstration, not an isolated causal test',
                      'same_seed_across_branches': True, 'manual_design_rule_not_trained_controller': True}
        tasks.append(enqueue(f'stage2_{name}_head_identity', prompt, [crop],
                             ['cropped_head_of_actual_previous_Lucan_Stage1_species_identity'], conditions, order=i))
    save(RUN/'plan.json', {'purpose': 'Different evolved body plans from accumulated exercise, nutrition and personality',
        'reuses': str(source), 'previous_source_sha256': sha(source), 'configuration_sha256': sha(ROOT/'configs/branch_evolution.json'),
        'level_thresholds': cfg['level_thresholds'], 'initial_inferences': len(tasks),
        'further_steps': 'Review the actual stage2 branches before queueing any stage3 successor; no full matrix or3D',
        'identity_constraint': 'Head crop preserves lineage; complete prior body is not a VAE condition in this experiment',
        'confounds': ['Creative body-plan and personality briefs both vary; independent numeric control is not proved',
                      '1024 resolution instead of prior768; not a one-variable attribution experiment'],
        'tasks': [t['case_id'] for t in tasks], 'trellis_or_rigging': False})
    print(json.dumps({'run_dir': str(RUN), 'prepared': len(tasks)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    prepare()
