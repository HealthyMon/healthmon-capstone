import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from healthmon.evolution_gate import evaluate,require_gate
from healthmon import evolution_gate
from job_store import sha

RULES=dict(min_change_regions=3,min_inherited_anchors=2,expected_supporting_legs=2,expected_free_arms=2)
VALID=dict(body_plan_changed=True,family_identity_retained=True,coherent_connected_anatomy=True,
    not_only_texture_pose_or_scale=True,candidate_supporting_legs=2,candidate_free_arms=2,
    inherited_anchors=['green peach colors','organic shell'],major_changes=[
    dict(region=r,visible=True,description='Unit fixture: clear comparative structure') for r in ('torso','supporting_limbs','inherited_structure')])

class Gate(unittest.TestCase):
    def test_accepts_actual_required_fields(self):
        self.assertEqual(evaluate(VALID,RULES)['status'],'PASS')
    def test_texture_only_unchanged_torso_or_extra_limbs_are_rejected(self):
        for key,value in [('body_plan_changed',False),('not_only_texture_pose_or_scale',False),('candidate_supporting_legs',4),('candidate_free_arms',True),('major_changes',None)]:
            case=copy.deepcopy(VALID);case[key]=value
            self.assertEqual(evaluate(case,RULES)['status'],'REJECTED')
        case=copy.deepcopy(VALID);case['major_changes'][0]['region']='head'
        self.assertEqual(evaluate(case,RULES)['status'],'REJECTED')
    def test_gate_missing_or_stale_images_fail_closed(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);parent=folder/'parent.png';parent.write_bytes(b'UNIT PARENT')
            image=folder/'image.png';image.write_bytes(b'UNIT CANDIDATE')
            policy=dict(source_sha256='unit-policy',semantic_gate=RULES)
            with self.assertRaises(ValueError):require_gate(folder,parent,policy)
            record=dict(provenance=dict(parent_sha256=sha(parent),candidate_sha256=sha(image),policy_sha256='unit-policy',validator_sha256=sha(evolution_gate.__file__)),observation=VALID,decision=evaluate(VALID,RULES))
            path=folder/'evolution_check.json';path.write_text(json.dumps(record))
            self.assertEqual(require_gate(folder,parent,policy),record)
            image.write_bytes(b'ALTERED')
            with self.assertRaises(ValueError):require_gate(folder,parent,policy)
    def test_target_prompt_does_not_reintroduce_quadruped_contract_direction(self):
        from healthmon.individual_evolution import compile_individual,design_planning_request
        from healthmon.species_contract import image_prompt
        contract=json.loads((ROOT/'configs/species/nubi.json').read_text(encoding='utf-8'))
        stats=dict(UpperBody=68,LowerBody=66,Nutrition=70,EnergyBalance=-.1,Activity=63,Affinity=64,Initiative=78,Mood=58)
        compiled=compile_individual(dict(species='nubi',previous_level=29,level=30,seed=42,stats=stats,history=[],history_origin='missing'),species_contract=contract)
        prompt=image_prompt(compiled,dict(image_prompt='unit planned new biped'))
        self.assertNotIn(contract['stage_directions']['2'],prompt)
        self.assertNotIn(contract['identity'],prompt)
        self.assertIn('TWO separated supporting legs',prompt)
        request=json.loads(design_planning_request(compiled)['user'])
        self.assertNotIn('stage_directions',request['species_contract'])
        self.assertIn('ancestral_identity',request['species_contract'])

if __name__=='__main__':unittest.main(verbosity=2)
