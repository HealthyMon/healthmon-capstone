"""Compile recorded game scores into the actual Qwen inference prompt.

The score rules are explicit game design, not a trained or medical body model.
There is deliberately no caller-supplied target Form or free-form body override.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .branch_evolution import HEALTH_FIELDS, choose_evolution, due_transitions
from .prompts import ART_DIRECTION_CONFIG, evolution_art_direction

ROOT = Path(__file__).resolve().parents[2]
IDENTITIES = {
    'mongle': 'Mongle: cream and warm apricot fleece, honey-brown eyes, pale muzzle, pointed apricot ears and inherited spiral forehead curl. It is an original cloud-lineage quadruped.',
    'tori': 'Tori: ivory coat, olive-brown eyes, pale muzzle, green leaf ears, a curled forehead tuft and living woodland foliage. It is an original sacred-grove quadruped.',
    'lucan': 'Lucan: charcoal canine fur, amber eyes, ivory muzzle and chest, gold forehead crest and golden tail accent. It is an original sovereign canine quadruped.',
}
SIGNATURES = {
    'mongle': 'Two sweeping spiral fleece plumes frame an inherited central curl, a sculpted cloud-scroll shoulder mantle curls backward, and a flowing two-lobed cloud tail balances the body. Fine pearlescent whorl markings are innate in the fleece. Keep the short mantle above the ribs and expose the entire waist, abdomen and legs. Develop a dignified adult brow and muzzle, smaller eyes relative to the head, and four broad distinct paws.',
    'tori': 'The two inherited leaf ears develop into elegant tall branching leaf fronds; a layered shoulder canopy, branching amber heartwood ridges, a few ivory blossoms and a flowing three-leaf tail establish sacred-grove anatomy. Fine emerald vein markings are innate in the coat. End the canopy above the ribs and expose the entire waist, abdomen and legs. Develop a dignified adult brow and muzzle, smaller eyes relative to the head, and four broad distinct paws.',
    'lucan': 'An elegant golden forehead crest, long ivory flowing cheek and shoulder mane, refined gold limb markings and a sweeping split golden tail establish sovereign anatomy. Fine amber markings are innate in the coat. Keep the mane above the ribs and expose the entire waist, abdomen and legs. Develop a dignified adult brow and muzzle, smaller eyes relative to the head, and four broad distinct paws.',
}
BODY_BRIEFS = {
    'sprinter': 'AGILE WIND SENTINEL. A long streamlined torso with a clearly tucked, narrow waist, deep lean chest, powerful distinctly developed hindquarters and long spring-loaded hind legs. The forequarters remain lighter than the hips. Use a poised forward-ready stance and swept-back flowing species motifs. Actual exposed torso anatomy must read as athletic. Keep the developed sacred-stage face and signature structures.',
    'bulwark': 'POWERFUL MOUNTAIN SENTINEL. A broad deep muscular chest, much larger shoulders and upper forelimbs, huge grounded forepaws, compact strong hindquarters and a firm visible waist. The front half is substantially more developed than the rear half. Arrange the same stage-specific natural shoulder motifs in a wide monumental span. Muscle has firm planar transitions, not a soft hanging belly. Keep the developed sacred-stage face and signature structures.',
    'balanced_athlete': 'ALL-ROUND ATHLETIC SENTINEL. Evenly developed shoulders and hips, firm defined waist, strong proportional forelegs and hind legs, a symmetrical poised stance. Use the full mature species signature structures with exposed athletic anatomy.',
    'balanced_ranger': 'HARMONIOUS GROVEKEEPER. A moderately built proportionate torso, gently defined waist, even shoulders and hips, medium-length legs and an elegant upright standing stance. Its anatomy is neither a sprinter specialization nor a bulwark specialization. Use balanced flowing sacred-stage signature structures and an adult face.',
    'restful_ranger': 'STILL-WATCH GUARDIAN. A long gently curved torso, modest muscle definition, relaxed lower shoulders, softly resting weight on four medium-length legs and a calm slightly lowered neck. Keep a visible waist and ordinary abdomen: balanced energy intake does not justify an obese abdomen. The body is relaxed rather than an athletic runner. Develop the same adult sacred-stage face and complete signature structures; use an elegant downward flow in the shoulder motifs.',
    'hearth_heavy': 'MONUMENTAL HEARTH GUARDIAN. A very wide softly rounded torso with a huge clearly exposed ivory or cream abdomen, broad soft hips, thick thighs and short-looking sturdy weight-bearing legs. Show a smooth convex belly extending below the ribcage and well behind the forelegs, and large soft flanks. Keep the head moderate in size so it reads as a majestic adult, not a starter cub. Natural shoulder motifs fan widely but end above the huge visible abdomen. Develop the same sacred-stage face and signature structures as every other branch.',
    'recovery_guardian': 'RESILIENT RETURNING GUARDIAN. Retain the preceding heavy branch\'s broad hips, moderately rounded visible abdomen and substantial paws, while developing firmer supporting limbs, a more lifted chest and an upright active stance. The body still carries clearly readable softness from its recorded heavy history. Use the same mature sacred-stage signature structures; do not replace the accumulated body history with an instantly slender runner.',
}


def digest_json(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _validate(profile):
    required = {'species', 'previous_level', 'level', 'previous_form', 'records', 'personality'}
    missing = required - profile.keys()
    if missing:
        raise ValueError(f'Missing numeric inputs: {sorted(missing)}')
    forbidden = {'form', 'target_form', 'branch', 'prompt', 'anatomy'} & profile.keys()
    if forbidden:
        raise ValueError(f'Target design must be derived from scores, not overridden: {sorted(forbidden)}')
    if profile['species'] not in IDENTITIES:
        raise ValueError('Unsupported species')
    if profile['previous_form'] not in {'FIT', 'BALANCED', 'INACTIVE', 'HEAVY', 'RECOVERY'}:
        raise ValueError('Invalid previous Form')
    for record in profile['records']:
        for field in (*HEALTH_FIELDS, 'days'):
            value = record.get(field, 1) if field == 'days' else record.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{field} must be finite and numeric')
    for field in ('Affinity', 'Initiative', 'Mood'):
        value = profile['personality'].get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{field} must be finite and numeric')


def compile_numeric_evolution(profile):
    """Return a real inference request at one crossed 25-level milestone, or None."""
    _validate(profile)
    transitions = due_transitions(profile['previous_level'], profile['level'])
    if not transitions:
        return None
    if len(transitions) != 1:
        raise ValueError('Generate and review each actual predecessor before advancing multiple stages')
    transition = transitions[0]
    decision = choose_evolution(profile['records'], profile['personality'], previous_form=profile['previous_form'])
    h = decision['health_summary']
    p = decision['personality']
    nutrition = (
        'High meal-quality score: a smooth lustrous coat, crisp healthy leaf or fleece edges, and bright restrained innate vein or whorl highlights.' if h['Nutrition'] >= 70 else
        'Moderate meal-quality score: a softly satin coat, moderately crisp leaf or fleece edges, and gentle innate vein or whorl highlights.' if h['Nutrition'] >= 40 else
        'Low meal-quality score: a matte coat, softer less crisp leaf or fleece edges, and very subdued innate vein or whorl highlights. Preserve the same beautiful mature sacred anatomy and body proportions; nutrition quality alone does not create obesity or undo evolution.'
    )
    activity = ('Sustained high activity: show firm engaged supporting limbs and springy readiness.' if h['Activity'] >= 70 else
                'Moderate activity: show naturally supported, evenly toned limbs.' if h['Activity'] >= 25 else
                'Sustained low activity: show relaxed limbs and modest muscle definition.')
    muscle = (f"Upper-body training {h['UpperBody']:g}/100: " +
              ('strongly developed shoulders and forelimbs' if h['UpperBody'] >= 75 else 'moderate shoulders and forelimbs' if h['UpperBody'] >= 40 else 'light upper-body muscle definition') +
              f". Lower-body training {h['LowerBody']:g}/100: " +
              ('strongly developed hips, thighs and hind limbs' if h['LowerBody'] >= 75 else 'moderate hips and hind limbs' if h['LowerBody'] >= 40 else 'light lower-body muscle definition') + '.')
    # Heavy/recovery retains fat irrespective of exercise-specific muscle phrases.
    body = BODY_BRIEFS[decision['branch']]
    body_description = f'{body}\n{activity}\n{muscle}'
    personality_description = f"{decision['expression']}. " + (
        'Hold the head high with a deliberate confident gaze.' if p['Initiative'] >= 70 else 'Hold the head slightly lower with a modest composed gaze.')
    if p['Mood'] <= 30:
        personality_description += ' Close the smiling mouth, narrow the eyelids and use a solemn watchful expression; keep its sacred dignity.'
    stage = transition['target_stage']
    signature = (SIGNATURES[profile['species']] if stage >= 2 else
                 'Use a restrained juvenile forehead motif, small shoulder growths and a compact species-specific tail; leave room for the second evolution.')
    if stage == 3:
        signature += ' Develop these inherited structures into a more monumental flowing final guardian silhouette with a longer adult muzzle, more layered natural head crest and assured imposing stance.'
    prompt = f'''Create exactly one original HEALTHMON {profile['species']} at evolution Stage{stage}, level{transition['level']}, as a beautiful numinous sacred beast with a clearly mature and compelling evolution silhouette.
The sole reference contains the central face of the actual preceding creature. Inherit the species palette, eye color and recognizable muzzle. Rebuild the entire head outline, brow, ears, neck, body and tail into the requested evolved anatomy. The cropped reference is an identity detail, never a framing template. Target-stage and target-body images are absent.
PRIORITY BODY DESIGN, DERIVED FROM RECORDED SCORES: {body_description}
SPECIES IDENTITY: {IDENTITIES[profile['species']]}
STAGE SIGNATURES: {signature}
{evolution_art_direction(profile['species'], transition['source_stage'], stage, decision['form'])}
FOOD-QUALITY APPEARANCE: {nutrition}
PERSONALITY EXPRESSION AND HEAD CARRIAGE: {personality_description}
ACTUAL GAME INPUTS: {h['days']:g} recorded days; upper-body {h['UpperBody']:g}/100; lower-body {h['LowerBody']:g}/100; activity {h['Activity']:g}/100; meal quality {h['Nutrition']:g}/100; energy balance {h['EnergyBalance']:+g} on [-1,1]; prior Form {profile['previous_form']}; computed Form {decision['form']}; computed branch {decision['branch']}. Affinity {p['Affinity']:g}/100, Initiative {p['Initiative']:g}/100, Mood {p['Mood']:g}/100. These are game scores. Personality changes expression and carriage independently of body fat. Energy surplus and meal quality are separate inputs.
Render polished stylized 3D fantasy creature artwork with bold sculpted coherent anatomy, smooth material groups, dignified restrained luminous anatomical accents and a readable exposed torso. Exactly one head, one complete quadrupedal body, four clearly separated paws and one complete tail. Side-biased three-quarter standing view, whole creature and every appendage within the central80percent of a square white canvas, only a faint shadow directly underneath. No text, diagrams, props, floating symbols, panels or additional characters.'''
    return {'transition': transition, 'decision': decision, 'prompt': prompt,
            'visual_controls': {'body': body_description, 'nutrition': nutrition, 'personality': personality_description},
            'numeric_inputs': profile, 'numeric_input_sha256': digest_json(profile),
            'controller_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'rule_sha256': hashlib.sha256((ROOT/'src/healthmon/branch_evolution.py').read_bytes()).hexdigest(),
            'art_direction_sha256': hashlib.sha256(ART_DIRECTION_CONFIG.read_bytes()).hexdigest(),
            'control_status': 'Deterministic score-to-text compiler; image adherence requires visual review'}
