"""Prevent numeric milestone requests from using an incorrectly mapped predecessor."""
import hashlib
import json
from pathlib import Path
from .branch_evolution import stage_for_level
from .prompts import ART_DIRECTION_CONFIG


def verify_numeric_parent(parent, metadata, profile):
    parent=Path(parent).resolve();digest=hashlib.sha256(parent.read_bytes()).hexdigest()
    if metadata.get('status')!='COMPLETED' or metadata.get('output',{}).get('sha256')!=digest:
        raise ValueError('Previous actual inference does not match its recorded output')
    conditions=metadata.get('evaluation_conditions',{})
    stage=conditions.get('target_stage');form=conditions.get('form')
    stage_source='Actual previous inference metadata'
    # Preserve archived requested stages while respecting the user's visual assignment.
    policy=json.loads(ART_DIRECTION_CONFIG.read_text())
    for reference in policy.get('references',{}).values():
        if Path(reference['image_path']).resolve()==parent and reference['sha256']==digest:
            stage=reference['design_stage'];form={'athletic':'FIT','heavy':'HEAVY'}[reference['form']]
            stage_source='User-confirmed visual stage assignment; archived requested stage unchanged'
            break
    expected=stage_for_level(profile['previous_level'])
    if stage!=expected:
        raise ValueError(f'Previous image visual stage {stage} does not match previous level stage {expected}')
    if form!=profile['previous_form']:
        raise ValueError(f'Previous image Form {form} does not match recorded prior Form {profile["previous_form"]}')
    if conditions.get('species') and conditions['species']!=profile['species']:
        raise ValueError('Previous image species does not match numeric profile')
    return {'parent_sha256':digest,'verified_visual_stage':stage,'verified_form':form,
            'stage_assignment_source':stage_source}
