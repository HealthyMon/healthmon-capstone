import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'runtime/unity'))
from healthmon.individual_evolution import compile_individual, design_planning_request
from healthmon.species_contract import art_direction, image_prompt
from job_store import sha
from species_experiment import resolve_case

STATS1=dict(UpperBody=60,LowerBody=60,Nutrition=65,EnergyBalance=0,Activity=55,Affinity=60,Initiative=75,Mood=50)
STATS2=dict(UpperBody=68,LowerBody=66,Nutrition=70,EnergyBalance=-.10,Activity=63,Affinity=64,Initiative=78,Mood=58)


class SecondStage(unittest.TestCase):
    def test_art_policy_preserves_identity_and_score_input(self):
        for species in ('mora','nubi'):
            contract=json.loads((ROOT/'configs/species'/f'{species}.json').read_text(encoding='utf-8'))
            saved=copy.deepcopy(contract)
            first=compile_individual(dict(species=species,previous_level=14,level=15,seed=42,stats=STATS1,history=[],history_origin='missing'),species_contract=contract)
            second=compile_individual(dict(species=species,previous_level=29,level=30,seed=42,stats=STATS2,history=[],history_origin='missing'),species_contract=contract)
            before=copy.deepcopy(second)
            request=design_planning_request(second)
            policy=art_direction(second)
            self.assertIsNone(art_direction(first))
            self.assertEqual(json.loads(request['user'])['evolution_art_policy'],policy)
            self.assertEqual(policy['source_sha256'],sha(ROOT/'configs/evolution/second-stage-v2.json'))
            self.assertIn(policy['species_direction'],image_prompt(second,dict(image_prompt='parent-grounded planned form')))
            self.assertEqual(second,before)
            self.assertEqual(contract,saved)
            self.assertEqual(second['recipe']['current'],{k:float(v) for k,v in STATS2.items() if k!='Mood'})
            self.assertNotEqual(first['condition'],second['condition'])

    def test_actual_first_parent_review_and_varied_scores_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary); folder=run/'species/nubi/stage1_balanced_seed42';folder.mkdir(parents=True)
            contract=json.loads((ROOT/'configs/species/nubi.json').read_text(encoding='utf-8'))
            (run/'species/nubi/species.json').write_text(json.dumps(contract),encoding='utf-8')
            parent=folder/'image.png';parent.write_bytes(b'explicit unit fixture, no inference')
            (folder/'image.png.json').write_text(json.dumps(dict(status='PASS',output=dict(sha256=sha(parent)))),encoding='utf-8')
            previous=dict(species='nubi',target_stage=1,stats=STATS1)
            (folder/'request.json').write_text(json.dumps(previous),encoding='utf-8')
            review=dict(nubi_stage1_seed42=dict(accepted_for_next_step=True,sha256=sha(parent)))
            review_path=run/'descendant_visual_review.json';review_path.write_text(json.dumps(review),encoding='utf-8')
            target,actual,job,source=resolve_case(run,'nubi',2,STATS2)
            self.assertEqual(actual,parent)
            self.assertEqual(job['source_stage'],1);self.assertEqual(job['target_stage'],2)
            self.assertEqual(job['stats'],STATS2);self.assertEqual(source['image_sha256'],sha(parent))
            self.assertEqual(source['species_contract'],contract)
            review['nubi_stage1_seed42']['sha256']='0'*64
            review_path.write_text(json.dumps(review),encoding='utf-8')
            with self.assertRaises(ValueError):resolve_case(run,'nubi',2,STATS2)


if __name__=='__main__':unittest.main(verbosity=2)
