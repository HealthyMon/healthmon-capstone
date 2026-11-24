import copy
import json
from pathlib import Path

import pytest

from Ai.Generation3D.runtime.evolution_2511.lineage import require_slime_parent
from Ai.Generation3D.src.healthmon.individual_evolution import compile_individual, design_planning_request
from Ai.Generation3D.src.healthmon.species_contract import art_direction, image_prompt
from Ai.Generation3D.runtime.common_gateway.appearance import BODY_CONDITIONS, body_condition, apply_to_prompt

ROOT = Path(__file__).resolve().parents[1]
SLIME = json.loads((ROOT/'configs/species/slime.json').read_text(encoding='utf-8'))
BASE = json.loads((ROOT/'tests/fixtures/lucan-species-baseline.json').read_text(encoding='utf-8'))['profile']


@pytest.mark.parametrize('parent', [{}, {'species':'lucan'}, {'species':'slime'},
    {'species':'slime', 'species_contract':{**SLIME, 'species':'lucan'}}])
def test_modern_adapter_rejects_legacy_or_incomplete_parent_before_gpu(parent):
    with pytest.raises(ValueError): require_slime_parent(parent)


@pytest.mark.parametrize('stage,level', [(1,15),(2,30),(3,50)])
def test_all_slime_stages_keep_slime_contract_and_front_view(stage,level):
    profile={**copy.deepcopy(BASE), 'species':'slime', 'previous_level':level-1, 'level':level}
    compiled=compile_individual(profile,species_contract=SLIME)
    assert compiled['transition']['target_stage']==stage
    assert art_direction(compiled) is None  # Historical turtle/axolotl biped policy never leaks in.
    request=design_planning_request(compiled)
    prompt=image_prompt(compiled, {'image_prompt':'One connected evolved slime with its original visible face.'})
    combined=json.dumps([compiled['recipe'],request,prompt]).lower()
    for old in ('lucan','thunder-wolf','charcoal fur','ivory muzzle','mandatory major second-evolution'):
        assert old not in combined
    assert 'FRONT VIEW' in prompt and SLIME['stage_directions'][str(stage)] in prompt
    assert require_slime_parent({'species':'slime','species_contract':SLIME})==SLIME


@pytest.mark.parametrize('appearance', sorted(BODY_CONDITIONS))
def test_every_shared_appearance_uses_slime_body_volumes(appearance):
    profile={'rule_version':'healthmon.v2.2','appearance':appearance}
    direction=body_condition(profile,species='slime')
    assert 'jelly' in direction or 'slime' in direction
    assert body_condition(profile).endswith(BODY_CONDITIONS[appearance])
    prompt=apply_to_prompt('SLIME\nSCORE-DERIVED BODY CONDITION: old\nFRONT VIEW',profile,species='slime')
    assert direction in prompt and 'FRONT VIEW' in prompt
    assert 'old' not in prompt


@pytest.mark.parametrize('stage,level', [(1,10),(2,20),(3,30)])
def test_live_game_milestones_preserve_slime_lineage(stage,level):
    # The live server uses 10/20/30; the historical offline adapter uses 15/30/50.
    stats={key:value for key,value in BASE['stats'].items() if key!='Mood'}
    profile={'species':'slime','level':level,'source_stage':stage-1,
             'target_stage':stage,'stats':stats,'history':[], 'seed':42,
             'authoritative_game_profile':{'rule_version':'healthmon.v2.2','appearance':'ordinary'}}
    compiled=compile_individual(profile,species_contract=SLIME,game_contract='healthmon.v2.2')
    assert compiled['transition']=={'source_stage':stage-1,'target_stage':stage,'level':level}
    prompt=image_prompt(compiled,{'image_prompt':'An evolved slime retaining the parent face and color.'})
    assert 'FRONT VIEW' in prompt and SLIME['stage_directions'][str(stage)] in prompt
    assert compiled['recipe']['species']=='slime'
    assert 'thunder-wolf' not in prompt.lower()
    # A request cannot skip a previous generated parent stage.
    if stage>1:
        with pytest.raises(ValueError,match='sequentially'):
            compile_individual({**profile,'source_stage':0},species_contract=SLIME,game_contract='healthmon.v2.2')
