"""Explicit per-lineage identity; growth math is shared, species appearance is not."""
import copy
import hashlib
import json
import re
from pathlib import Path


def validate_contract(value, species=None):
    if not isinstance(value, dict) or value.get('schema_version') != 'healthmon.species.v1':
        raise ValueError('A healthmon.species.v1 contract is required for a new species')
    result = copy.deepcopy(value)
    name = result.get('species')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name):
        raise ValueError('Invalid species identifier')
    if species is not None and name != species:
        raise ValueError('Species and its contract do not match')
    for key in ('label_ko', 'identity', 'starter_prompt'):
        if not isinstance(result.get(key), str) or not 1 <= len(result[key]) <= 6000:
            raise ValueError('Missing or excessive species description: ' + key)
    anchors = result.get('lineage_anchors')
    if not isinstance(anchors, list) or not 2 <= len(anchors) <= 8 or any(not isinstance(item, str) or not 1 <= len(item) <= 1000 for item in anchors):
        raise ValueError('Provide two to eight explicit lineage anchors')
    stages = result.get('stage_directions')
    if not isinstance(stages, dict) or set(stages) != {'1', '2', '3'} or any(not isinstance(item, str) or not 1 <= len(item) <= 3000 for item in stages.values()):
        raise ValueError('Provide the three ordered evolution directions')
    return result


def contract_hash(value):
    return hashlib.sha256(json.dumps(validate_contract(value), ensure_ascii=False, sort_keys=True,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def art_direction(compiled):
    """Stage rendering policy never rewrites the published species identity or scores."""
    if compiled['transition']['target_stage'] != 2:
        return None
    path = Path(__file__).resolve().parents[2] / 'configs/evolution/second-stage-v2.json'
    raw = path.read_bytes()
    policy = json.loads(raw)
    if policy.get('schema_version') != 'healthmon.evolution_art.v1' or policy.get('target_stage') != 2:
        raise ValueError('Invalid second-stage art policy')
    if not isinstance(policy.get('shared_direction'), str) or not policy['shared_direction'].strip():
        raise ValueError('An explicit stage transformation direction is required')
    species = compiled['recipe']['species']
    specific = policy.get('species_directions', {}).get(species, '')
    if not isinstance(specific, str):
        raise ValueError('Invalid species art direction')
    gate = dict(policy['semantic_gate'])
    requirements = gate.pop('species_requirements', {}).get(species, {})
    gate.update(requirements)
    return dict(policy_id=policy['policy_id'], target_stage=2, source_sha256=hashlib.sha256(raw).hexdigest(),
                source_filename=path.name, shared_direction=policy['shared_direction'],
                species_direction=specific, semantic_gate=gate)


def planning_request(compiled, axis_sources):
    recipe = compiled['recipe']
    contract = validate_contract(recipe['species_contract'], recipe['species'])
    state = {key: value for key, value in recipe.items()
             if key not in ('prompt', 'history_records', 'dimensions', 'current', 'history', 'tendencies')}
    state['whole_form_axes'] = {key: value for key, value in recipe['dimensions'].items() if key != 'adiposity'}
    state['physical_condition'] = recipe['condition']
    policy = art_direction(compiled)
    if policy is not None:
        state['evolution_art_policy'] = policy
        # The immutable contract is ancestry, not a target-anatomy constraint.
        state['species_contract'] = dict(species=contract['species'], label_ko=contract['label_ko'],
            ancestral_identity=contract['identity'], inherited_symbols=contract['lineage_anchors'])
        state['stage_context'] = dict(target_stage=2, mandatory_body_plan=policy['species_direction'])
    system = (
        'You are the art director of an original creature-raising fantasy game. Design ONE evolved individual '
        'belonging to the explicit species_contract and actual parent image. Preserve its stated family identity '
        'and two or more actually visible heritable anchors; invent a new coherent stage-appropriate whole silhouette. '
        'Interpret all supplied whole_form_axes together. Physical condition gives secondary artistic shape cues, '
        'never biological measurements or inferred health history. Do not replace this species with another animal. '
        'A shell, external gills, fins, skin or other existing defining materials must stay coherent with this family. '
        'Use connected anatomy, broad readable sculpted forms, smooth stylized 3D game rendering, a calm expression, '
        'a complete three-quarter figure with generous white margins. Do not invent clothing, weapons, floating parts or text. '
        'Return ONLY complete JSON with design_thesis_ko (one short Korean sentence), reasoning (three entries), '
        'structural_changes (three English phrases), lineage_anchors (two or more English phrases), '
        'image_prompt (130-170 English words). Each reasoning entry contains source_axes (two or more exact names '
        'from whole_form_axes), decision_ko and form_why_ko (short Korean sentences describing the artistic decision). '
        'Across the three entries cover all supplied persistent physical and behavioral fields through their declared axes. '
        'Explain proposed shapes only; do not claim observed exercise, food or unprovided history.')
    if policy is not None:
        system += (' The explicit evolution_art_policy is the stage-2 transformation requirement. '
            'Name three major new structures in structural_changes and express them clearly in image_prompt. '
            'Ancestral identity and visible parent descriptions are historical evidence, NOT target anatomy. '
            'Keep the friendly rounded game-art style; added realistic detail is not evolution.')
    return dict(version='species-generative-director-v2' if policy else 'species-generative-director-v1', seed=recipe['seed'],
        grounding=dict(current=recipe['current'], history=recipe['history'], axis_sources=axis_sources),
        system=system, user=json.dumps(state, ensure_ascii=False, sort_keys=True),
        perception_system=(
            'Observe this actual previous creature. Write 45 to 70 English words describing only visibly inherited '
            'color relationships, surface materials, head and body organization, and two or three distinctive '
            'structural signatures such as a shell, gill fans or a fin. Report only visible evidence. '
            'Do not propose an evolution, clothing, props, a different species, mood or unobserved history.'),
        fallback_signature='; '.join(contract['lineage_anchors']),
        inference=dict(do_sample=True, temperature=.7, top_p=.9, repetition_penalty=1.05, max_new_tokens=1100))


def body_instruction(compiled):
    fat = compiled['condition']['adiposity']
    muscle = compiled['condition']['exercise_development']
    if fat >= .6:
        text = 'A visibly fuller softer body, wider waist and rounded projecting underside; retain this species structural identity and supporting anatomy.'
    elif fat <= .2 and muscle >= .8:
        text = 'An athletic lean body with a narrower underside and stronger developed supporting musculature, interpreted coherently for this species.'
    else:
        text = 'A balanced moderately built individual with medium body volumes and moderate supporting musculature, appropriate to its species and stage.'
    return text + f' Artistic reserve index={fat:.4f}; exercise development={muscle:.4f}.'


def image_prompt(compiled, concept):
    contract = validate_contract(compiled['recipe']['species_contract'], compiled['recipe']['species'])
    stage = compiled['transition']['target_stage']
    policy = art_direction(compiled)
    stage_text = '' if policy is None else ('\nMANDATORY MAJOR SECOND-EVOLUTION TRANSFORMATION: '
        + policy['shared_direction'] + '\nSPECIES STAGE TRANSFORMATION: ' + policy['species_direction'])
    ancestry = ('Create ONE original radically evolved descendant of the ' + contract['species'] + ' lineage. '
        'Ancestral symbols may be reorganized into the mandatory new body plan; do not retain ancestral limb function.\n') if policy else (
        'Create ONE original newly evolved ' + contract['identity'] + '\n' + contract['stage_directions'][str(stage)])
    return (ancestry + stage_text + '\nSCORE-DERIVED BODY CONDITION: '
        + body_instruction(compiled) + '\nINHERITED FAMILY SYMBOLS, not target body-plan constraints: '
        + '; '.join(contract['lineage_anchors']) + '\nACTUAL PARENT-GROUNDED DESIGN: '
        + concept['image_prompt'] + '\nSmooth high-quality stylized 3D fantasy-game character render. '
        'Coherent connected anatomy, broad legible forms, soft studio lighting, calm three-quarter standing pose. '
        'Full body and complete tail inside generous margins on a plain WHITE square background. '
        'Exactly ONE creature, no labels, text, grids, comparison panels, extra heads, floating fragments, clothing or weapons.\n')
