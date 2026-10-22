"""Docker-side general score/parent-image adapter, using the verified local runtimes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parents[1]))
sys.path.insert(0, str(ROOT / 'src'))
from job_store import LEVELS, atomic_json, read, sha

STAGES = {
    1: 'FIRST EVOLUTION: a juvenile QUADRUPEDAL thunder-wolf, older than the infant, longer muzzle and legs, lifted ears, swept double gold forehead ridge and fuller gold-tipped tail. FOUR complete supporting paws, youthful compact body, no hands or upright human torso.',
    2: 'SECOND EVOLUTION: a mature broad QUADRUPEDAL thunder-wolf with lower forward-leaning head, strong hindquarters, substantial torso, organic gold shoulder ridges and enlarged lightning crest. FOUR complete supporting paws and a long substantial tail. Never the final upright form.',
    3: 'THIRD EVOLUTION: a mature UPRIGHT BIPEDAL thunder-wolf. Exactly TWO separated supporting feet and TWO long arms with complete clawed hands beside the hips above the ground. Exposed ivory chest and abdomen, wolf face, gold forehead crest, organic shoulder ridges and connected gold-tipped tail.',
}


def body_instruction(compiled):
    fat = compiled['condition']['adiposity']
    muscle = compiled['condition']['exercise_development']
    if fat >= .6:
        text = 'Visibly soft fat body with a large projecting round ivory belly, wide soft waist, rounded flanks and thighs. Emphasize soft adipose volume rather than a muscular chest.'
    elif fat <= .20 and muscle >= .8:
        text = 'Athletic lean body with a flat ivory abdomen, narrow waist and visibly developed firm supporting musculature. No swollen belly.'
    else:
        text = 'Balanced moderately built body with a gently rounded ivory abdomen and moderate supporting musculature. Neither bodybuilder nor very large fat belly.'
    return text + f' Artistic adiposity={fat:.4f}; exercise development={muscle:.4f}.'


def plan(folder, job):
    parent = ROOT / 'outputs/unity_service/pets' / job['pet_id'] / 'versions' / job['source_revision'] / 'image.png'
    source = read(parent.parent / 'manifest.json')
    return plan_from_parent(folder, job, parent, source)


def plan_from_parent(folder, job, parent, source):
    from healthmon.individual_evolution import compile_individual, design_planning_request, infer_design_brief
    from healthmon.qwen_runner import MODEL_ID, MODEL_REVISION
    from healthmon.species_contract import body_instruction as species_body, image_prompt as species_prompt, art_direction
    from types import SimpleNamespace
    import torch
    from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor
    stage = job['target_stage']
    contract = source.get('species_contract')
    if sha(parent) != source['image_sha256'] or source['stage'] != job['source_stage']:
        raise ValueError('Parent provenance mismatch')
    v22 = job.get('game_contract') == 'healthmon.v2.2'
    if v22:
        profile = dict(species=source.get('species','lucan'), level=job['authoritative_state']['level'],
                       source_stage=job['source_stage'], target_stage=stage, seed=job.get('seed',42),
                       stats=job['stats'], history=[], history_origin='missing',
                       authoritative_game_profile=job['authoritative_profile'])
    else:
        profile = dict(species=source.get('species', 'lucan'), previous_level=LEVELS[stage] - 1, level=LEVELS[stage], seed=job.get('seed', 42),
                       stats=job['stats'], history=[], history_origin='missing')
    compiled = compile_individual(profile, species_contract=contract,
                                  game_contract='healthmon.v2.2' if v22 else 'legacy')
    request = design_planning_request(compiled)
    data = json.loads(request['user'])
    resolved_policy = art_direction(compiled) if contract else None
    data['explicit_stage_art_direction'] = (resolved_policy['shared_direction'] + ' ' + resolved_policy['species_direction']) if resolved_policy else (contract['stage_directions'][str(stage)] if contract else STAGES[stage])
    data['explicit_score_condition_direction'] = species_body(compiled) if contract else body_instruction(compiled)
    if v22:
        from Ai.Generation3D.runtime.common_gateway.appearance import body_condition
        direction=body_condition(job['authoritative_profile'])
        data['explicit_score_condition_direction']=direction
        data['authoritative_body_condition']=direction
        data['condition_role']='The shared v2.2 appearance is a required visible whole-body condition, not an optional secondary nuance.'
        if 'physical_condition' in data:
            data['physical_condition']['role']=data['condition_role']
        if 'visual_principles' in data:
            data['visual_principles']=[value for value in data['visual_principles'] if 'not a swollen belly' not in value]
        request['system']+=' The AUTHORITATIVE V2.2 APPEARANCE controls the visible body condition. Describe the requested abdomen, waist, flanks and supporting masses explicitly; do not contradict it with a default moderate, lean or muscular body. Preserve the supplied species and stage anatomy.'
    groups = [['kinetic_flow', 'support_distribution', 'spatial_spread'],
              ['visual_density', 'surface_integration', 'overall_presence'],
              ['social_openness', 'self_direction', 'developmental_momentum', 'contrast_rhythm']]
    template = dict(design_thesis_ko='짧은 전체 조형 설명',
        reasoning=[dict(source_axes=g, decision_ko='짧은 조형 결정', form_why_ko='복합 지수와 조형의 관계') for g in groups],
        structural_changes=['mass arrangement', 'head trunk support relation', 'inherited gold motif'],
        lineage_anchors=['charcoal ivory gold', 'wolf face and tail'], image_prompt='130-170 English words')
    if contract:
        template['structural_changes'] = ['mass arrangement', 'head trunk support relation', 'transformed inherited species motif']
        template['lineage_anchors'] = contract['lineage_anchors'][:2]
        request['system'] += (' Obey the species contract, stage and score condition. Copy source_axes arrays EXACTLY. '
            'Return complete concise JSON. OUTPUT TEMPLATE: ' + json.dumps(template, ensure_ascii=False))
    else:
        # Legacy Lucan behavior remains explicit for previously published lineages.
        request['system'] += (' Obey the explicit stage and score condition. Keep a coherent stylized wolf family. '
            'No clothes, weapons, dragons or unrelated species. Copy source_axes arrays EXACTLY. '
            'Keep Korean fields concise and return complete JSON without markdown. OUTPUT TEMPLATE: ' + json.dumps(template, ensure_ascii=False))
    request['user'] = json.dumps(data, ensure_ascii=False, sort_keys=True)
    implementation = dict(model_id=MODEL_ID, revision=MODEL_REVISION, dtype='bfloat16',
        compiler_version=compiled['version'], compiler_sha256=sha(ROOT / 'src/healthmon/individual_evolution.py'),
        adapter_sha256=sha(__file__), conditioning_mode='planner_only')
    if contract:
        policy = art_direction(compiled)
        implementation.update(species_module_sha256=sha(ROOT / 'src/healthmon/species_contract.py'),
            evolution_art_policy=None if policy is None else dict(policy_id=policy['policy_id'], source_sha256=policy['source_sha256']))
        if policy is not None: atomic_json(folder / 'art_policy.json', policy)
    atomic_json(folder / 'profile.json', profile)
    atomic_json(folder / 'compiled.json', compiled)
    atomic_json(folder / 'parent.json', dict(path=str(parent), sha256=sha(parent), revision=job['source_revision']))
    atomic_json(folder / 'planning_request.json', request)
    if (folder / 'design.json').exists():
        record = read(folder / 'design.json')
        if record['implementation'] != implementation or record['visual_references'][0]['sha256'] != sha(parent):
            raise ValueError('Planner implementation or parent changed; create a new request')
        design = record
    else:
        processor_path = ROOT / 'models/huggingface/models--Qwen--Qwen-Image-2.1/snapshots' / MODEL_REVISION / 'processor'
        processor = Qwen3VLProcessor.from_pretrained(str(processor_path), local_files_only=True)
        encoder = Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID, subfolder='text_encoder',
            revision=MODEL_REVISION, torch_dtype=torch.bfloat16, device_map='cuda',
            cache_dir=str(ROOT / 'models/huggingface'), local_files_only=True).eval()
        infer_design_brief(SimpleNamespace(text_encoder=encoder, processor=processor), request,
                           folder / 'design.json', implementation, visual_references=[str(parent)])
        design = read(folder / 'design.json')
    if contract:
        prompt = species_prompt(compiled, design['concept'])
    else:
        prompt = ('Create ONE original newly evolved Lucan thunder-wolf. ' + STAGES[stage] + '\n'
            'SCORE-DERIVED BODY CONDITION: ' + body_instruction(compiled) + '\n'
            'Inherited family identity: charcoal fur, ivory muzzle/chest/abdomen/paws, amber eyes, pointed wolf ears, '
            'organic gold forehead and tail lightning motifs. Prioritize the explicit stage and score instructions.\n'
            + design['concept']['image_prompt'] + '\n'
            'Smooth stylized rendered 3D fantasy-game character, connected anatomy, broad legible forms. '
            'Plain WHITE square background. Calm three-quarter standing pose, full body and whole tail inside generous margins. '
            'Exactly ONE creature, no text, comparison panels, extra heads, floating fragments, clothes or weapons.\n')
    if v22:
        from Ai.Generation3D.runtime.common_gateway.appearance import apply_to_prompt
        prompt=apply_to_prompt(prompt,job['authoritative_profile'])
    (folder / 'prompt.txt').write_text(prompt, encoding='utf-8')


def image(folder, job):
    output = folder / 'image.png'
    if output.exists() and output.with_suffix('.png.json').exists():
        metadata = read(output.with_suffix('.png.json'))
        if metadata['status'] == 'PASS' and metadata['output']['sha256'] == sha(output) and metadata['source_prompt_sha256'] == sha(folder / 'prompt.txt'):
            pass
        else:
            raise ValueError('Image cache failed provenance check')
    else:
        subprocess.run([sys.executable, str(ROOT / 'runtime/lineage/qwen_runner.py'),
            '--prompt-file', str(folder / 'prompt.txt'), '--output', str(output), '--seed', str(job.get('seed', 42)),
            '--steps', '40', '--width', '768', '--height', '768', '--memory-mode', 'phased-cpu-offload',
            '--cache-dir', str(ROOT / 'models/huggingface'), '--local-files-only'], check=True, cwd=ROOT)
    from healthmon.quality import inspect_image
    qc = inspect_image(output)
    atomic_json(folder / 'image_qc.json', qc)
    if qc['technical_status'] != 'PASS':
        raise ValueError('Image technical QC failed; previous model retained')


def evolution_check(folder, job):
    from review_evolution_images import assess
    from healthmon.qwen_runner import MODEL_ID, MODEL_REVISION
    policy = read(folder / 'art_policy.json') if (folder / 'art_policy.json').exists() else None
    if policy and policy.get('semantic_gate'):
        assess(folder, Path(read(folder / 'parent.json')['path']), policy, MODEL_ID, MODEL_REVISION, ROOT)


def reconstruct(folder, job):
    policy = read(folder / 'art_policy.json') if (folder / 'art_policy.json').exists() else None
    if policy and policy.get('semantic_gate'):
        from healthmon.evolution_gate import require_gate
        require_gate(folder, Path(read(folder / 'parent.json')['path']), policy)
    subprocess.run([sys.executable, str(ROOT / 'runtime/phased/configure_gpu_runtime.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'runtime/lineage/run_image_to_rigged.py'),
        '--image', str(folder / 'image.png'), '--output-dir', str(folder / 'reconstruction'),
        '--stage', str(job['target_stage']), '--form', 'BALANCED', '--seed', str(job.get('seed', 42)), '--size', '512'], check=True, cwd=ROOT)


def mobile(folder):
    output = folder / 'mobile'
    output.mkdir(exist_ok=True)
    subprocess.run(['/usr/bin/blender', '-b', '-P', str(ROOT / 'runtime/unity/mobile_export.py'), '--',
        '--input', str(folder / 'reconstruction/rigging/final_rigged.glb'),
        '--output', str(output / 'model.glb'), '--triangles', '60000'], check=True)
    subprocess.run(['/usr/bin/blender', '-b', '-P', str(ROOT / 'src/healthmon/blender_tool.py'), '--',
        'validate', '--input', str(output / 'model.glb'), '--require-rig',
        '--report', str(output / 'validation.json'), '--preview-dir', str(output / 'preview')], check=True)
    report = read(output / 'validation.json')
    if report['status'] != 'PASS' or not report['pose_test']['valid']:
        raise ValueError('Optimized rig validation failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['plan', 'image', 'evolution_check', 'reconstruction', 'mobile_export'])
    parser.add_argument('--job-dir', type=Path, required=True)
    args = parser.parse_args()
    folder = args.job_dir.resolve()
    if not folder.is_relative_to(ROOT / 'outputs/unity_service/work'):
        raise ValueError('Job must be inside service work directory')
    job = read(folder / 'request.json')
    {'plan': lambda: plan(folder, job), 'image': lambda: image(folder, job), 'evolution_check': lambda: evolution_check(folder, job),
     'reconstruction': lambda: reconstruct(folder, job), 'mobile_export': lambda: mobile(folder)}[args.phase]()
