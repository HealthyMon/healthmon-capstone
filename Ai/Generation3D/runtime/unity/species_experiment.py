"""Explicit image-only lineage experiment with verified actual-parent provenance."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from job_store import read, sha, atomic_json, checked_stats
from evolution_worker import plan_from_parent, image, evolution_check
from healthmon.species_contract import validate_contract

BASE_STATS = dict(UpperBody=60, LowerBody=60, Nutrition=65, EnergyBalance=0,
                  Activity=55, Affinity=60, Initiative=75, Mood=50)


def resolve_case(run, species, target_stage, stats=None):
    contract = validate_contract(read(run / 'species' / species / 'species.json'), species)
    if target_stage == 1:
        parent_folder = run / 'species' / species / 'starter_seed_42'
        review = read(run / 'starter_visual_review.json')[species + '_seed42']
        source_revision = 'experiment_starter_seed42'
        inherited_stats = BASE_STATS
        folder = run / 'species' / species / 'stage1_balanced_seed42'
    elif target_stage == 2:
        parent_folder = run / 'species' / species / 'stage1_balanced_seed42'
        previous = read(parent_folder / 'request.json')
        if previous['species'] != species or previous['target_stage'] != 1:
            raise ValueError('Second evolution requires the actual first-evolution parent')
        inherited_stats = previous['stats']
        review = read(run / 'descendant_visual_review.json')[species + '_stage1_seed42']
        source_revision = 'experiment_stage1_balanced_seed42'
        folder = run / 'species' / species / 'stage2_dynamic_seed42'
    else:
        raise ValueError('This image experiment supports sequential stages 1 and 2')
    parent = parent_folder / 'image.png'
    meta = read(parent.with_suffix('.png.json'))
    if meta['status'] != 'PASS' or meta['output']['sha256'] != sha(parent):
        raise ValueError('Actual parent inference provenance mismatch')
    if not review.get('accepted_for_next_step', review.get('accepted_for_reconstruction')) or review['sha256'] != sha(parent):
        raise ValueError('Review and accept the actual parent before its descendant')
    job = dict(kind='image_only_species_generalization', seed=42, species=species,
        source_stage=target_stage-1, target_stage=target_stage, source_revision=source_revision,
        score_source='synthetic_demo_species_diversity' if target_stage == 1 else 'synthetic_demo_second_stage_varied_scores',
        stats=checked_stats(inherited_stats if stats is None else stats))
    source = dict(species=species, species_contract=contract, stage=target_stage-1, image_sha256=sha(parent))
    return folder, parent, job, source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['plan', 'image', 'evolution_check'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--species', required=True)
    parser.add_argument('--target-stage', type=int, choices=[1,2], default=1)
    parser.add_argument('--stats-file', type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not run.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Experiment must stay inside runtime outputs')
    stats = None
    if args.stats_file:
        stats_path = args.stats_file.resolve()
        if not stats_path.is_relative_to(ROOT / 'outputs'):
            raise ValueError('Explicit demo score file must stay inside outputs')
        stats = read(stats_path)
    folder, parent, job, source = resolve_case(run, args.species, args.target_stage, stats)
    folder.mkdir(parents=True, exist_ok=True)
    request_path = folder / 'request.json'
    if request_path.exists() and read(request_path) != job:
        raise ValueError('Experiment input changed; use a new experiment folder')
    atomic_json(request_path, job)
    if args.phase == 'plan': plan_from_parent(folder, job, parent, source)
    elif args.phase == 'image': image(folder, job)
    else: evolution_check(folder, job)
    print(args.species, args.phase, 'PASS (image-only case, no 3D publication)', flush=True)


if __name__ == '__main__': main()
