"""Explicit game evolution rules; generation and visual success remain separate.

Thresholds and health rules are editable game-design interpretations, not clinical
measurements or a trained morphology controller. Personality never selects fatness.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

HEALTH_FIELDS = ('UpperBody', 'LowerBody', 'Activity', 'Nutrition', 'EnergyBalance')


def stage_for_level(level, thresholds=(25, 50, 75)):
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level) or level < 0:
        raise ValueError('Level must be a nonnegative number')
    if len(thresholds) != 3 or list(thresholds) != sorted(set(thresholds)) or thresholds[0] <= 0:
        raise ValueError('Exactly three increasing thresholds define four stages')
    return sum(level >= milestone for milestone in thresholds)


def due_transitions(previous_level, current_level, thresholds=(25, 50, 75)):
    if current_level < previous_level:
        raise ValueError('Evolution progression cannot move backwards')
    first = stage_for_level(previous_level, thresholds)
    last = stage_for_level(current_level, thresholds)
    return [{'source_stage': s, 'target_stage': s + 1, 'level': thresholds[s]}
            for s in range(first, last)]


def aggregate_history(records):
    if not records:
        raise ValueError('Accumulated history is required')
    days = sum(r.get('days', 1) for r in records)
    if days <= 0 or any(r.get('days', 1) <= 0 for r in records):
        raise ValueError('History weights must be positive')
    for record in records:
        for field in HEALTH_FIELDS:
            low, high = (-1, 1) if field == 'EnergyBalance' else (0, 100)
            if not low <= record[field] <= high:
                raise ValueError(f'Invalid {field}')
    summary = {field: sum(r[field] * r.get('days', 1) for r in records) / days
               for field in HEALTH_FIELDS}
    summary['days'] = days
    summary['joint_inactive_surplus_days'] = sum(r.get('days', 1) for r in records
        if r['Activity'] < 25 and r['EnergyBalance'] > .2)
    return summary


def choose_evolution(records, personality, *, previous_form='BALANCED'):
    health = aggregate_history(records)
    if health['joint_inactive_surplus_days'] >= 14 and health['Activity'] < 25 and health['EnergyBalance'] > .2:
        form, branch = 'HEAVY', 'hearth_heavy'
    elif previous_form == 'HEAVY' and health['Activity'] >= 55 and health['Nutrition'] >= 65:
        form, branch = 'RECOVERY', 'recovery_guardian'
    elif previous_form == 'RECOVERY' and not (
            health['days'] >= 28 and health['Activity'] >= 75 and health['Nutrition'] >= 75
            and max(health['UpperBody'], health['LowerBody']) >= 80 and abs(health['EnergyBalance']) < .3):
        form, branch = 'RECOVERY', 'recovery_guardian'
    elif health['Activity'] >= 70 and max(health['UpperBody'], health['LowerBody']) >= 75:
        form = 'FIT'
        branch = ('sprinter' if health['LowerBody'] - health['UpperBody'] >= 15 else
                  'bulwark' if health['UpperBody'] - health['LowerBody'] >= 15 else 'balanced_athlete')
    elif health['Activity'] < 25:
        form, branch = 'INACTIVE', 'restful_ranger'
    else:
        form, branch = 'BALANCED', 'balanced_ranger'
    for name in ('Affinity', 'Initiative', 'Mood'):
        if not 0 <= personality[name] <= 100:
            raise ValueError(f'Invalid {name}')
    expression = []
    expression.append('warm approachable eyes' if personality['Affinity'] >= 70 else 'reserved attentive eyes')
    expression.append('raised purposeful head and confident posture' if personality['Initiative'] >= 70 else 'relaxed modest head carriage')
    expression.append('cheerful soft brows and a small smile' if personality['Mood'] >= 70 else
                      'lowered eyelids and subdued mouth' if personality['Mood'] <= 30 else 'calm neutral mouth')
    return {'form': form, 'branch': branch, 'health_summary': health,
            'body_control': {'UpperBody': health['UpperBody'], 'LowerBody': health['LowerBody'],
                             'Activity': health['Activity'], 'EnergyBalance': health['EnergyBalance'],
                             'retained_softness': form == 'RECOVERY'},
            'expression': ', '.join(expression), 'personality': dict(personality),
            'rule_status': 'Explicit game-design rule, not learned model control'}


def commit_evolution(previous, output, metadata, review, *, target_level, decision, thresholds=(25,50,75)):
    """Commit a generated successor only after explicit visual review of that PNG."""
    output = Path(output).resolve()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    if metadata.get('status') not in ('COMPLETED', 'PASS') or metadata.get('technical_image_qc') == 'FAIL':
        raise ValueError('A completed usable inference is required')
    parent = Path(previous['current_image'])
    if not parent.is_file() or hashlib.sha256(parent.read_bytes()).hexdigest() != previous['current_image_sha256']:
        raise ValueError('Actual parent image must match its recorded hash')
    recorded_parent = metadata.get('evaluation_conditions', {}).get('full_previous_source_sha256')
    if recorded_parent and recorded_parent != previous['current_image_sha256']:
        raise ValueError('Inference parent does not match the previous state')
    if metadata.get('output', {}).get('sha256') != digest or review.get('output_sha256') != digest:
        raise ValueError('Output and visual review must bind the same actual PNG')
    if not review.get('accept_as_evolution'):
        raise ValueError('Technical completion alone cannot commit an evolution')
    if previous.get('state_status', '').startswith('CANDIDATE'):
        raise ValueError('Parent stage must be visually accepted before committing its successor')
    target_stage = stage_for_level(target_level, thresholds)
    if target_stage != previous['stage'] + 1:
        raise ValueError('Commit one actual next-stage evolution at a time')
    return {'species': previous['species'], 'stage': target_stage, 'level': target_level,
            'form': decision['form'], 'branch': decision['branch'],
            'current_image': str(output), 'current_image_sha256': digest,
            'parent_image': previous['current_image'], 'parent_image_sha256': previous['current_image_sha256'],
            'history': previous.get('history', []) + [decision],
            'lineage': previous.get('lineage', []) + [{'stage': previous['stage'],
                       'image': previous['current_image'], 'sha256': previous['current_image_sha256']}],
            'retained_visual_traits': review.get('retained_visual_traits', []),
            'review': dict(review)}
