"""Localized score-derived facial edits; preserve the actual evolved body."""
from .numeric_evolution import compile_numeric_evolution, digest_json


def compile_personality_refinement(profile):
    compiled=compile_numeric_evolution(profile)
    if compiled is None:raise ValueError('A base milestone request is required')
    p=compiled['decision']['personality']
    eyes=('Use gentle openly curved eyelids and softly raised outer brows, with a warmly welcoming gaze.' if p['Affinity']>=70 else
          'Replace the round open eyelids with visibly narrow almond-shaped eyelids and a restrained watchful gaze; preserve the original honey-brown or amber eye color.')
    mouth=('Raise both mouth corners into a clearly visible warm smile.' if p['Mood']>=70 else
           'Give the muzzle a straight tightly closed mouth with slightly lowered corners, a visibly solemn expression.' if p['Mood']<=30 else
           'Give the muzzle a neutral gently closed mouth.')
    carriage=('Lift the chin slightly into a confident purposeful head carriage.' if p['Initiative']>=70 else
              'Lower the chin slightly into a reserved composed head carriage.')
    prompt=f'''EDIT THE FACE EXPRESSION OF IMAGE1. {eyes} {mouth} {carriage}
This facial edit is the main requested change and must be clearly visible. Preserve the recognizable muzzle, forehead curl or crest, ear anatomy and eye color. Preserve the exact already evolved Stage{compiled['transition']['target_stage']} {profile['species']} body, all torso proportions, waist, muscle distribution, coat material, markings, four legs, paws and tail. Preserve the same camera, standing body pose and white background. Output exactly one complete creature with the changed expression. No panels or text.
Actual game personality scores: Affinity {p['Affinity']}/100; Initiative {p['Initiative']}/100; Mood {p['Mood']}/100. These change expression and head carriage only, never body fat or evolutionary stage.'''
    return {'prompt':prompt,'attribute':'personality','attribute_inputs':p,
        'numeric_inputs':profile,'numeric_input_sha256':compiled['numeric_input_sha256'],
        'attribute_input_sha256':digest_json(p),'decision':compiled['decision'],
        'rule_status':'Explicit game expression mapping, not a learned personality model'}
