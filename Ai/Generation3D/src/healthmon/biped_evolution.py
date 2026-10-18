"""Species-defined biped anatomy with the existing score and milestone rules."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .branch_evolution import HEALTH_FIELDS, choose_evolution, due_transitions
from .numeric_evolution import digest_json

ROOT=Path(__file__).resolve().parents[2]
SPECIES_DIR=ROOT/'configs/species'


def load_biped_species(species):
    if not isinstance(species,str) or not species.isascii() or not species.replace('_','').isalnum():
        raise ValueError('Invalid species identifier')
    path=SPECIES_DIR/f'{species}.json'
    data=json.loads(path.read_text())
    if data['id']!=species or data['locomotion']!='biped':
        raise ValueError('A registered biped species is required')
    return data,path


def compile_biped_evolution(profile, *, conditioning='previous_identity_detail'):
    required={'species','previous_level','level','previous_form','records','personality'}
    if required-profile.keys():raise ValueError('Missing numeric profile inputs')
    if {'form','target_form','branch','prompt','anatomy'}&profile.keys():
        raise ValueError('Target design must be derived from scores, not overridden')
    species,config_path=load_biped_species(profile['species'])
    if profile['previous_form'] not in {'FIT','BALANCED','INACTIVE','HEAVY','RECOVERY'}:
        raise ValueError('Invalid previous Form')
    for record in profile['records']:
        for field in (*HEALTH_FIELDS,'days'):
            value=record.get(field,1) if field=='days' else record.get(field)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f'{field} must be finite and numeric')
    for key in ('Affinity','Initiative','Mood'):
        value=profile['personality'].get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be finite and numeric')
    transitions=due_transitions(profile['previous_level'],profile['level'])
    if not transitions:return None
    if len(transitions)!=1:raise ValueError('Generate each actual predecessor before advancing multiple stages')
    if conditioning not in {'previous_identity_detail','none_founder'}:raise ValueError('Invalid conditioning')
    t=transitions[0];stage=t['target_stage']
    decision=choose_evolution(profile['records'],profile['personality'],previous_form=profile['previous_form'])
    h=decision['health_summary'];p=decision['personality']
    if stage==1:
        body=species['stage1_branch_bodies'][decision['branch']]
    else:body=species['branch_bodies'][decision['branch']]
    face=('Gentle open almond-shaped eyes and softly curved brows' if p['Affinity']>=70 else
          'Narrow almond-shaped eyelids with reserved attentive eyes')
    face+=('; clearly raised mouth corners in a warm small smile' if p['Mood']>=70 else
           '; a straight tightly closed mouth with slightly lowered corners and solemn watchful brows' if p['Mood']<=30 else
           '; a calm neutral closed mouth')
    face+=('; chin raised with confident purposeful head carriage.' if p['Initiative']>=70 else
           '; chin slightly lowered with modest composed head carriage.')
    nutrition=('Smooth satin skin and clearly legible restrained luminous current markings.' if h['Nutrition']>=70 else
               'Soft satin skin and gently visible current markings.' if h['Nutrition']>=40 else
               'Matte skin and subdued current markings; preserve the same beautiful developed anatomy and body proportions.')
    reference=('Create this new original species founding first-evolution concept from the following description. No reference image and no prior generated individual is supplied.' if conditioning=='none_founder' else
               f'The sole reference is a small identity detail from the actual preceding Stage{t["source_stage"]} creature. Inherit its midnight-teal and jade palette, pearl spots and recognizable amphibian muzzle. Freely mature the eyes, head proportions, crescent fins, shoulders, entire torso and legs into Stage{stage}. The cropped reference supplies identity only.')
    prompt=f'''Create one complete HEALTHMON {species['name_en']}, evolution Stage{stage} at level{t['level']}, a beautiful original BIPEDAL sacred-spring creature.
BODY BRANCH FROM ACTUAL SCORES: {body}
EXPRESSION FROM PERSONALITY SCORES: {face}
{reference}
SPECIES: {species['identity']}
STAGE MATURITY: {species['stages'][str(stage)]}
FOOD-QUALITY APPEARANCE: {nutrition}
ACTUAL GAME INPUTS: {h['days']:g} days; upper-body {h['UpperBody']:g}/100; lower-body {h['LowerBody']:g}/100; activity {h['Activity']:g}/100; meal quality {h['Nutrition']:g}/100; energy balance {h['EnergyBalance']:+g} on [-1,1]. Computed Form {decision['form']}, branch {decision['branch']}. Affinity {p['Affinity']:g}/100; Initiative {p['Initiative']:g}/100; Mood {p['Mood']:g}/100. These are game scores. Personality changes expression independently of body fat; inactivity alone does not select obesity.
ANATOMY: {species['anatomy_constraint']}
Polished stylized 3D fantasy game artwork, bold clean anatomy, natural smooth skin and translucent fins, refined integrated luminous markings and strong sacred-beast presence. Keep every body branch equally mature and appealing at this stage. Side-biased front-three-quarter upright standing view, hands separated from the torso, all fingers, feet, fins and tail visible with generous white margins. Fit the whole creature within the central80percent of a square canvas. Plain white studio background, only a faint shadow under the feet. No clothes, equipment, props, floating symbols, text, panels or extra creatures.'''
    return dict(transition=t,decision=decision,prompt=prompt,numeric_inputs=profile,
        numeric_input_sha256=digest_json(profile),locomotion='biped',conditioning=conditioning,
        visual_controls={'body':body,'personality':face,'nutrition':nutrition},
        controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        rule_sha256=hashlib.sha256((ROOT/'src/healthmon/branch_evolution.py').read_bytes()).hexdigest(),
        species_config=str(config_path),species_config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        control_status='Explicit score-to-text game rule; actual visual adherence requires review')
