"""Three genuine, sequential V2 lineages sharing one generated starter.

Actual parent images condition the original V2 vision planner. Descendant
diffusion uses native text-to-image; no target-stage artwork is provided.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from healthmon.individual_evolution import compile_individual, design_planning_request, VERSION
from healthmon.qwen_runner import MODEL_ID, MODEL_REVISION

BRANCHES = {
    'balanced': dict(label_ko='균형형', stats=dict(UpperBody=60, LowerBody=60, Nutrition=65,
        EnergyBalance=0, Activity=55, Affinity=60, Initiative=75, Mood=50)),
    'athletic': dict(label_ko='운동 발달형', stats=dict(UpperBody=90, LowerBody=90, Nutrition=90,
        EnergyBalance=-.20, Activity=90, Affinity=60, Initiative=75, Mood=50)),
    'high_reserve': dict(label_ko='체지방 증가형', stats=dict(UpperBody=30, LowerBody=30, Nutrition=40,
        EnergyBalance=.75, Activity=15, Affinity=60, Initiative=75, Mood=50)),
}
LEVELS = {1:(14,15), 2:(29,30), 3:(49,50)}
STAGE_DIRECTION = {
    1: 'FIRST EVOLUTION, a juvenile quadrupedal thunder-wolf. Clearly older than the infant: longer muzzle and legs, lifted ears, an acquired swept double gold forehead ridge and a fuller gold-tipped wolf tail. Still youthful, compact and approachable. FOUR distinct supporting paws, no hands or upright human torso. Do not already make the final massive adult.',
    2: 'SECOND EVOLUTION, a broad adult QUADRUPEDAL thunder-wolf, a clearly new intermediate silhouette. A lower forward-leaning head, strong hindquarters, a broad torso, organic gold shoulder ridges and an enlarged swept lightning crest; a long substantial gold-tipped wolf tail stabilizes the body. FOUR distinct supporting paws. Mature and more substantial than the juvenile, but still visibly quadrupedal, never the final upright form.',
    3: 'THIRD EVOLUTION, a mature UPRIGHT BIPEDAL thunder-wolf with a transformed torso organization. Exactly TWO separated feet bear its weight, and TWO long arms end in clearly visible clawed hands hanging above the ground beside the hips. A distinct exposed ivory chest and abdomen, recognizable wolf face and ears, inherited gold forehead crest, integrated gold shoulder ridges, a large connected gold-tipped wolf tail. Whole body must read as an adult bipedal wolf creature, not a quadruped or a human in armor.',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verified_image(path):
    meta=read(Path(str(path)+'.json'))
    assert meta['status']=='PASS' and meta['local_inference']
    assert meta['output']['sha256']==sha(path)
    return meta


def body_instruction(compiled,stage):
    c=compiled['condition'];fat=c['adiposity'];muscle=c['exercise_development']
    if fat>=.6:
        text='Visibly soft and FAT: a very large rounded ivory belly, wide soft waist and thick rounded flanks and thighs. The projecting abdomen must be clearly visible, not hidden by fur or ornaments; emphasize soft adipose volume rather than a muscular chest.'
    elif fat<=.20 and muscle>=.8:
        text='Distinctly ATHLETIC and lean: flat ivory abdomen, narrow waist, powerful firm supporting legs and shoulders, visibly developed musculature with clear broad volumes. Muscular development must be appropriate to this evolution stage, never a swollen belly.'
    else:
        text='A BALANCED moderately built creature: a gently rounded ivory abdomen, medium waist and moderate supporting musculature. Neither highly defined bodybuilder muscles nor a very large fat belly; an approachable, sturdy middle-sized silhouette appropriate to this stage.'
    return text+f" Compiled artistic adiposity={fat:.4f}, exercise development={muscle:.4f}."


def request_for(compiled,stage):
    request=design_planning_request(compiled)
    data=json.loads(request['user'])
    data['explicit_stage_art_direction']=STAGE_DIRECTION[stage]
    data['explicit_score_condition_direction']=body_instruction(compiled,stage)
    groups=[['kinetic_flow','support_distribution','spatial_spread'],
            ['visual_density','surface_integration','overall_presence'],
            ['social_openness','self_direction','developmental_momentum','contrast_rhythm']]
    template=dict(design_thesis_ko='짧은 전체 조형 설명',
        reasoning=[dict(source_axes=g,decision_ko='짧은 조형 결정',form_why_ko='복합 지수와 조형의 관계') for g in groups],
        structural_changes=['main mass arrangement','head trunk and support relation','inherited organic gold motif'],
        lineage_anchors=['charcoal ivory gold','wolf face and tail'],image_prompt='130-170 English words')
    request['system']+=(' Obey the explicit evolution-stage art direction and score condition. '
        'The previous actual image supplies inherited color and character signatures, never a finished target-stage template. '
        'Keep a coherent stylized wolf family. Do not invent new clothing, weapons, dragons or unrelated species. '
        'Copy source_axes arrays EXACTLY from this template; keep Korean fields concise. '
        'Return complete JSON without markdown. OUTPUT TEMPLATE: '+json.dumps(template,ensure_ascii=False))
    request['user']=json.dumps(data,ensure_ascii=False,sort_keys=True)
    return request


def prepare(run,stage):
    previous_stage=stage-1
    review=read(run/f'stage_{previous_stage}_visual_review.json')
    assert review['status']=='ACCEPTED', 'Review the actual parent images before advancing'
    rows=[]
    for branch,description in BRANCHES.items():
        parent=run/'starter/image.png' if stage==1 else run/f'branches/{branch}/stage_{previous_stage}/image.png'
        meta=verified_image(parent)
        review_key='starter' if stage==1 else branch
        assert review['cases'][review_key]['sha256']==sha(parent)
        previous_level,level=LEVELS[stage]
        profile=dict(case_id=f'{branch}_stage{stage}',species='lucan',previous_level=previous_level,
            level=level,seed=42,stats=description['stats'],history=[],history_origin='missing')
        compiled=compile_individual(profile)
        assert compiled['transition']['source_stage']==previous_stage and compiled['transition']['target_stage']==stage
        folder=run/f'branches/{branch}/stage_{stage}'
        if (folder/'profile.json').exists():assert read(folder/'profile.json')==profile
        save(folder/'profile.json',profile);save(folder/'compiled.json',compiled)
        save(folder/'planning_request.json',request_for(compiled,stage))
        parent_info=dict(path=str(parent),sha256=sha(parent),stage=previous_stage,
            branch='shared_starter' if stage==1 else branch,model=meta['model_id'],
            metadata_sha256=sha(Path(str(parent)+'.json')),actual_previous_generated_image=True,
            diffusion_reference=False,vision_planner_reference=True)
        save(folder/'parent.json',parent_info)
        rows.append(dict(branch=branch,label_ko=description['label_ko'],stage=stage,
            directory=str(folder),parent=parent_info))
    save(run/f'stage_{stage}_plan.json',dict(rows=rows,synthetic_scores=True,
        conditioning_mode='planner_only',target_stage_image_inputs=0,compiler_version=VERSION,
        compiler_sha256=sha(ROOT/'src/healthmon/individual_evolution.py')))
    print(f'Prepared stage {stage}: three verified parents and score recipes',flush=True)


def plan(run,stage):
    import time
    from types import SimpleNamespace
    import torch
    from transformers import Qwen3VLForConditionalGeneration,Qwen3VLProcessor
    from healthmon.individual_evolution import infer_design_brief
    rows=read(run/f'stage_{stage}_plan.json')['rows']
    implementation=dict(model_id=MODEL_ID,revision=MODEL_REVISION,dtype='bfloat16',
        compiler_sha256=sha(ROOT/'src/healthmon/individual_evolution.py'),
        local_adapter_sha256=sha(Path(__file__)),conditioning_mode='planner_only',
        torch=torch.__version__,cuda=torch.version.cuda)
    processor_path=ROOT/'models/huggingface/models--Qwen--Qwen-Image-2.1/snapshots'/MODEL_REVISION/'processor'
    started=time.monotonic()
    processor=Qwen3VLProcessor.from_pretrained(str(processor_path),local_files_only=True)
    encoder=Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID,subfolder='text_encoder',
        revision=MODEL_REVISION,torch_dtype=torch.bfloat16,device_map='cuda',
        cache_dir=str(ROOT/'models/huggingface'),local_files_only=True).eval()
    pipe=SimpleNamespace(text_encoder=encoder,processor=processor)
    for row in rows:
        folder=Path(row['directory']);compiled=read(folder/'compiled.json')
        assert sha(Path(row['parent']['path']))==row['parent']['sha256']
        print(f"PLAN stage {stage} {row['branch']}",flush=True)
        infer_design_brief(pipe,read(folder/'planning_request.json'),folder/'design.json',implementation,
            visual_references=[row['parent']['path']])
        design=read(folder/'design.json')
        signature=design.get('perception',{})
        # The original planner's recorded concept already incorporates its actual
        # parent perception. Retain the whole inference record as evidence.
        prompt=('Create ONE original newly evolved Lucan thunder-wolf creature. '+STAGE_DIRECTION[stage]+'\n'
            'SCORE-DERIVED BODY CONDITION: '+body_instruction(compiled,stage)+'\n'
            'Inherited family identity: charcoal-black fur, ivory muzzle/chest/abdomen/paws, amber eyes, '
            'pointed wolf ears, organic gold lightning forehead and tail accents. '
            'Read the evolution stage and score condition above as the primary instructions; '
            'express the following parent-grounded V2 design with those constraints.\n'
            +design['concept']['image_prompt']+'\n'
            'Smooth stylized rendered 3D fantasy-game character, coherent connected anatomy and broad legible forms. '
            'Plain WHITE square background, calm three-quarter standing pose, full body and whole tail inside the canvas '
            'with generous margins. Exactly ONE complete creature: no comparison panels, labels, text, grids, extra heads '
            'or floating fragments. No clothes, weapons or human accessories. The GOLD structures are organic inherited motifs.\n')
        (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
    save(run/f'stage_{stage}_planner_result.json',dict(status='PASS',actual_language_generation=True,
        implementation=implementation,seconds=time.monotonic()-started,
        peak_cuda_allocated_gb=torch.cuda.max_memory_allocated()/1e9,
        prompt_artifacts=[dict(branch=r['branch'],path=str(Path(r['directory'])/'prompt.txt'),
            sha256=sha(Path(r['directory'])/'prompt.txt')) for r in rows]))
    print(f'Stage {stage} V2 parent-grounded planning PASS',flush=True)


def verify(run,stage):
    from healthmon.quality import inspect_image
    for branch in BRANCHES:
        folder=run/f'branches/{branch}/stage_{stage}'
        metadata=verified_image(folder/'image.png')
        assert metadata['generation_mode']=='native_text_to_image'
        assert metadata['ordered_references']==[]
        assert metadata['source_prompt_sha256']==sha(folder/'prompt.txt')
        qc=inspect_image(folder/'image.png')
        save(folder/'image_qc.json',qc)
        assert qc['technical_status']=='PASS',qc
    print(f'Stage {stage}: three actual Qwen images technically verified; visual review still required',flush=True)


parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['prepare','plan','verify'])
parser.add_argument('--run-dir',type=Path,required=True)
parser.add_argument('--stage',type=int,choices=[1,2,3],required=True)
args=parser.parse_args();run=args.run_dir.resolve()
assert run.is_relative_to(ROOT/'outputs')
{'prepare':prepare,'plan':plan,'verify':verify}[args.command](run,args.stage)
