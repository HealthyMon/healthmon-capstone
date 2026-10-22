"""Strict CPU-only request validation; no AI model import or invented measurements."""
import math
import base64
import hashlib
import re
from Server.healthmon.rules import evolution_profile

CONTRACT = 'healthmon.ai.v1'
RULE = 'healthmon.v2.2'
AXES = {'upper_body':'UpperBody','lower_body':'LowerBody','nutrition':'Nutrition',
        'energy_balance':'EnergyBalance','activity':'Activity','affinity':'Affinity','initiative':'Initiative'}
APPEARANCES = {'adipose','lean_athletic','lean','bulky_athletic','rounded_general','upper_developed',
               'lower_developed','balanced_athletic','developed_general','ordinary','undertrained'}


def identifier(value):
    if not isinstance(value,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value) is None:
        raise ValueError('Invalid stable identifier')
    return value


def validate_request(job_id, body):
    identifier(job_id)
    if set(body) != {'contract_version','request_id','pet_id','input'}:
        raise ValueError('Unexpected envelope fields')
    if body['contract_version'] != CONTRACT or body['request_id'] != job_id:
        raise ValueError('Contract/request identity mismatch')
    identifier(body['pet_id'])
    data=body['input']
    if not isinstance(data,dict) or data.get('adapter_version') != 'healthmon.evolution.v2.2':
        raise ValueError('Only the explicit v2.2 adapter contract is accepted')
    fields={'stage','state','profile','rule_version','adapter_version','source_contract','legacy_compatibility'}
    if set(data) not in (fields,fields|{'parent_asset'}) or data['source_contract']!='new_common_gateway_contract':
        raise ValueError('Unexpected v2.2 job fields')
    state,profile=data.get('state'),data.get('profile')
    if not isinstance(state,dict) or not isinstance(profile,dict):
        raise ValueError('A frozen state and profile are required')
    if state.get('pet_id') != body['pet_id'] or state.get('rule_version') != RULE or data.get('rule_version') != RULE or profile.get('rule_version') != RULE:
        raise ValueError('State/profile ownership or rule version mismatch')
    stage=data.get('stage')
    if isinstance(stage,bool) or not isinstance(stage,int) or not 1 <= stage <= 3:
        raise ValueError('Invalid evolution stage')
    level=state.get('level')
    if isinstance(level,bool) or not isinstance(level,int) or not 1 <= level <= 100:
        raise ValueError('Current generator supports authoritative levels 1..100')
    if sum(level >= x for x in (10,20,30)) != stage or profile.get('stage') != stage or state.get('evolution_target_stage') != stage:
        raise ValueError('Stage must correspond to actual level 10/20/30')
    published=state.get('published_model_stage')
    if isinstance(published,bool) or not isinstance(published,int) or not 0 <= published < stage:
        raise ValueError('A new stage must be pending')
    if profile.get('appearance') not in APPEARANCES:
        raise ValueError('Unknown v2.2 appearance')
    if profile != evolution_profile(state,state.get('previous_evolution')):
        raise ValueError('Frozen profile does not match the authoritative v2.2 state')
    stats={}
    for key,out in AXES.items():
        value=state.get(key)
        low=-100 if key=='energy_balance' else 0
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low <= value <= 100:
            raise ValueError('All seven finite, measured game axes are required')
        stats[out]=value/100 if key=='energy_balance' else value
    if any(key.lower()=='mood' for key in state):
        raise ValueError('Mood is not an authoritative v2.2 axis')
    compatibility=data.get('legacy_compatibility',{})
    if compatibility.get('mood') is not None or compatibility.get('energy_balance_normalized',stats['EnergyBalance']) != stats['EnergyBalance'] or compatibility.get('original_energy_balance',state['energy_balance']) != state['energy_balance']:
        raise ValueError('Compatibility values must not invent Mood or alter EnergyBalance')
    if 'parent_asset' in data:
        if stage!=1 or published!=0:raise ValueError('Automatic starter binding is only for the first transition')
        validate_parent_asset(data['parent_asset'])
    return stats


def validate_parent_asset(value):
    fields={'stage','revision','species','species_contract','image_base64','image_sha256','model_sha256','source_kind'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['stage']) is not int or value['stage']!=0 or value['source_kind']!='common_server_verified_starter':
        raise ValueError('Invalid authenticated starter parent contract')
    identifier(value['revision']);identifier(value['species'])
    for key in ('image_sha256','model_sha256'):
        if not isinstance(value[key],str) or re.fullmatch(r'[a-f0-9]{64}',value[key]) is None:raise ValueError('Invalid starter hash')
    encoded=value['image_base64']
    if not isinstance(encoded,str) or len(encoded)>1398104:raise ValueError('Starter image exceeds1MiB')
    try:image=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError) as exc:raise ValueError('Invalid starter image encoding') from exc
    if not 8<=len(image)<=1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(image).hexdigest()!=value['image_sha256']:
        raise ValueError('Starter image does not match its identity')
    contract=value['species_contract']
    if contract is not None:
        from Ai.Generation3D.src.healthmon.species_contract import validate_contract
        validate_contract(contract,value['species'])
    elif value['species']!='lucan':raise ValueError('An explicit species contract is required')
    return image
