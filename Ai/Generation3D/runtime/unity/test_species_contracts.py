import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'runtime/unity'))
from healthmon.individual_evolution import compile_individual, design_planning_request
from healthmon.species_contract import validate_contract, image_prompt, contract_hash
from job_store import Store
from test_jobs import tiny_glb

BASELINE = json.loads((ROOT / 'tests/fixtures/lucan-species-baseline.json').read_text(encoding='utf-8'))
MORA = json.loads((ROOT / 'configs/species/mora.json').read_text(encoding='utf-8'))
NUBI = json.loads((ROOT / 'configs/species/nubi.json').read_text(encoding='utf-8'))


class SpeciesContracts(unittest.TestCase):
    def test_legacy_lucan_recipe_and_request_are_unchanged(self):
        compiled = compile_individual(BASELINE['profile'])
        self.assertEqual(compiled, BASELINE['compiled'])
        self.assertEqual(design_planning_request(compiled), BASELINE['request'])

    def test_generic_recipe_and_prompt_have_no_lucan_leak(self):
        for contract in (MORA, NUBI):
            profile = {**BASELINE['profile'], 'species': contract['species']}
            compiled = compile_individual(profile, species_contract=contract)
            request = design_planning_request(compiled)
            prompt = image_prompt(compiled, dict(image_prompt='A coherent evolved creature from the actual parent.'))
            combined = json.dumps([compiled['recipe'], request, prompt]).lower()
            for forbidden in ('lucan', 'thunder-wolf', 'charcoal', 'ivory', 'amber eyes'):
                self.assertNotIn(forbidden, combined)
            self.assertEqual(compiled['recipe']['species'], contract['species'])
            self.assertIn(contract['identity'], prompt)
            self.assertEqual(compiled['condition'], BASELINE['compiled']['condition'])

    def test_identity_and_seed_change_recipe_mood_does_not(self):
        profile = {**BASELINE['profile'], 'species': 'mora'}
        first = compile_individual(profile, species_contract=MORA)
        mood = copy.deepcopy(profile)
        mood['stats']['Mood'] = 99
        self.assertEqual(first['body_key'], compile_individual(mood, species_contract=MORA)['body_key'])
        changed_seed = compile_individual({**profile, 'seed': 777}, species_contract=MORA)
        self.assertNotEqual(first['body_key'], changed_seed['body_key'])
        other = compile_individual({**profile, 'species': 'nubi'}, species_contract=NUBI)
        self.assertNotEqual(first['body_key'], other['body_key'])

    def test_unknown_or_mismatched_species_fails_explicitly(self):
        with self.assertRaises(ValueError):
            compile_individual({**BASELINE['profile'], 'species': 'mora'})
        with self.assertRaises(ValueError):
            compile_individual({**BASELINE['profile'], 'species': 'nubi'}, species_contract=MORA)
        bad = copy.deepcopy(MORA)
        bad['stage_directions'].pop('2')
        with self.assertRaises(ValueError): validate_contract(bad)

    def test_species_is_inherited_and_cannot_change_on_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image, model = root / 'image.png', root / 'model.glb'
            image.write_bytes(b'test fixture')
            tiny_glb(model)
            store = Store(root / 'state')
            starter = store.publish('pet', 'starter', 0, image, model, species='mora', species_contract=MORA)
            self.assertEqual(starter['species_contract_sha256'], contract_hash(MORA))
            job = store.submit('pet', dict(request_id='event', level=15, stats=BASELINE['profile']['stats'], score_source='synthetic_test'))
            self.assertEqual(job['species'], 'mora')
            evolved = store.publish('pet', 'evolved', 1, image, model, source_revision='starter')
            self.assertEqual(evolved['species'], 'mora')
            self.assertEqual(evolved['species_contract'], MORA)
            with self.assertRaises(ValueError):
                store.publish('pet', 'wrong', 2, image, model, source_revision='evolved', species='nubi', species_contract=NUBI)
            self.assertEqual(store.current('pet')['revision'], 'evolved')

    def test_generation_seed_is_replayable_and_part_of_nondefault_request_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image, model = root / 'image.png', root / 'model.glb'
            image.write_bytes(b'test fixture')
            tiny_glb(model)
            store = Store(root / 'state')
            store.publish('pet', 'starter', 0, image, model)
            request = dict(request_id='event', level=15, stats=BASELINE['profile']['stats'], score_source='synthetic_test')
            first = store.submit('pet', request)
            self.assertEqual(first['seed'], 42)
            self.assertEqual(first, store.submit('pet', {**request, 'seed': 42}))
            with self.assertRaises(ValueError): store.submit('pet', {**request, 'seed': 777})


if __name__ == '__main__': unittest.main(verbosity=2)
