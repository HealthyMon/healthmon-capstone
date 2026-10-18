"""Explicit region-by-region visual review, preserving the original strict validator."""
import hashlib
import json
from pathlib import Path
import time

def assess(folder,parent,policy,model_id,revision,root,retry=False):
    from PIL import Image
    import torch
    from transformers import Qwen3VLForConditionalGeneration,Qwen3VLProcessor
    from healthmon.evolution_gate import evaluate,require_gate
    from healthmon import evolution_gate
    folder=Path(folder);parent=Path(parent);root=Path(root)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    path=folder/'evolution_check.json';previous=None
    if path.exists():
        if not retry:return require_gate(folder,parent,policy)
        old=json.loads(path.read_text(encoding='utf-8'))
        if old['decision']['status']=='PASS':return require_gate(folder,parent,policy)
        number=1
        while (folder/f'evolution_check.attempt{number}.json').exists():number+=1
        archived=folder/f'evolution_check.attempt{number}.json'
        path.rename(archived);previous=dict(path=str(archived),sha256=sha(archived),decision=old['decision'])
    rules=policy['semantic_gate']
    system=('Compare ONLY the two ACTUAL creature images. Image1 is parent; Image2 is candidate. '
        'Write concrete visual observations in five labeled paragraphs: head, torso, supporting_limbs, inherited_structure, tail. '
        'For EACH paragraph describe image1 and image2, then whether a major structural change is visible. '
        'For torso compare trunk orientation, shoulder/waist/hip organization. For supporting_limbs count ground-support legs '
        'and free arms/hands separately in EACH image; distinguish limb function from a temporary pose. '
        'For inherited_structure compare shell/gill/fin architecture. Describe only what is visible; if uncertain say uncertain. '
        'Finally list visible shared family anchors, connected anatomy or extra-limb problems. '
        'Do not assume changes occurred; texture, color, pose and scale alone do not count as body-plan evolution.')
    user='Observe and compare the actual parent and candidate images, including all five regions. No JSON or desired design description.'
    images=[]
    for item in (parent,folder/'image.png'):
        with Image.open(item) as source:
            image=source.convert('RGB');image.thumbnail((512,512));images.append(image)
    processor_path=root/'models/huggingface/models--Qwen--Qwen-Image-2.1/snapshots'/revision/'processor'
    started=time.monotonic()
    processor=Qwen3VLProcessor.from_pretrained(str(processor_path),local_files_only=True)
    encoder=Qwen3VLForConditionalGeneration.from_pretrained(model_id,subfolder='text_encoder',revision=revision,
        torch_dtype=torch.bfloat16,device_map='cuda',cache_dir=str(root/'models/huggingface'),local_files_only=True).eval()
    content=[dict(type='image',image=str(parent)),dict(type='image',image=str(folder/'image.png')),dict(type='text',text=user)]
    formatted=processor.apply_chat_template([dict(role='system',content=system),dict(role='user',content=content)],
        tokenize=False,add_generation_prompt=True,enable_thinking=False)
    inputs=processor(text=[formatted],images=images,return_tensors='pt').to('cuda')
    with torch.inference_mode():output=encoder.generate(**inputs,do_sample=False,max_new_tokens=650)
    visual_analysis=processor.tokenizer.decode(output[0,inputs['input_ids'].shape[1]:],skip_special_tokens=True).split('</think>')[-1].strip()
    extraction_system=('Convert the supplied ACTUAL visual comparison into one complete JSON object. '
        'Never invent observations or copy example defaults. No default observations are provided. '
        'Fields: body_plan_changed, family_identity_retained, coherent_connected_anatomy, not_only_texture_pose_or_scale '
        '(all booleans grounded in the comparison), candidate_supporting_legs and candidate_free_arms (integer counts), '
        'inherited_anchors (visible shared features only, not taxonomy or hidden biological traits), '
        'major_changes (exactly FIVE objects with region, visible boolean, description), summary_ko (short sentence). '
        'Use exact regions head, torso, supporting_limbs, inherited_structure, tail. Every description must give the actual '
        'parent versus candidate comparison, even if unchanged; never leave descriptions empty. '
        'visible=true means the supplied comparison supports a major STRUCTURAL change in that region. '
        'Torso verticalization and a new shoulder/waist/hip organization are torso changes. '
        'Ground supporting forelegs becoming free arms/hands belongs in supporting_limbs. '
        'Do not infer a change from acceptance requirements. Return JSON only.')
    extraction_user='ACTUAL TWO-IMAGE OBSERVATIONS:\n'+visual_analysis+'\nAcceptance criteria (unchanged): '+json.dumps(rules,ensure_ascii=False)
    formatted=processor.apply_chat_template([dict(role='system',content=extraction_system),dict(role='user',content=extraction_user)],
        tokenize=False,add_generation_prompt=True,enable_thinking=False)
    structured=processor(text=[formatted],return_tensors='pt').to('cuda')
    with torch.inference_mode():output=encoder.generate(**structured,do_sample=False,max_new_tokens=1280)
    raw=processor.tokenizer.decode(output[0,structured['input_ids'].shape[1]:],skip_special_tokens=True).strip()
    cleaned=raw.split('</think>')[-1].strip()
    if cleaned.startswith('```'):cleaned=cleaned.split('\n',1)[1].rsplit('```',1)[0].strip()
    try:observation=json.loads(cleaned)
    except (ValueError,TypeError):observation={}
    record=dict(schema_version='healthmon.evolution_check.v1',
        provenance=dict(parent_sha256=sha(parent),candidate_sha256=sha(folder/'image.png'),policy_sha256=policy['source_sha256'],validator_sha256=sha(evolution_gate.__file__)),
        review_implementation=dict(version='vision-observation-then-structured-review-v3',sha256=sha(__file__),system=system,user=user,
            visual_analysis=visual_analysis,extraction_system=extraction_system,extraction_user=extraction_user,previous_attempt=previous),
        model_id=model_id,model_revision=revision,actual_two_image_vision_inference=True,training_performed=False,
        observation=observation,decision=evaluate(observation,rules),raw_output=raw,
        elapsed_seconds=round(time.monotonic()-started,3),
        limitations='Visual inference is fallible; direct review also required. Acceptance rules were not relaxed for this re-review.')
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return require_gate(folder,parent,policy)

if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--retry',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'src'))
    from healthmon.qwen_runner import MODEL_ID,MODEL_REVISION
    folder=args.folder.resolve()
    if not folder.is_relative_to(root/'outputs'):raise ValueError('Review must stay inside runtime outputs')
    policy=json.loads((folder/'art_policy.json').read_text(encoding='utf-8'))
    parent=Path(json.loads((folder/'parent.json').read_text(encoding='utf-8'))['path'])
    result=assess(folder,parent,policy,MODEL_ID,MODEL_REVISION,root,retry=args.retry)
    print('Actual two-image review',result['decision']['status'],flush=True)
