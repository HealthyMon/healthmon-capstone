"""Fail-closed visual comparison before reconstruction and publication."""
import hashlib
import json
from pathlib import Path

REGIONS={'head','torso','supporting_limbs','inherited_structure','tail'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def evaluate(observation,rules):
    errors=[]
    if not isinstance(observation,dict):return dict(status='REJECTED',errors=['Missing structured visual observation'])
    for key in ('body_plan_changed','family_identity_retained','coherent_connected_anatomy','not_only_texture_pose_or_scale'):
        if observation.get(key) is not True:errors.append(key+' is not confirmed')
    changes=observation.get('major_changes',[])
    if not isinstance(changes,list):changes=[]
    regions={item.get('region') for item in changes if isinstance(item,dict) and item.get('visible') is True
        and isinstance(item.get('description'),str) and len(item['description'].strip())>=8} & REGIONS
    if len(regions)<rules['min_change_regions']:errors.append('Insufficient distinct major-change regions')
    if not {'torso','supporting_limbs'}<=regions:errors.append('Torso and supporting-limb change are mandatory')
    anchors=observation.get('inherited_anchors',[])
    if not isinstance(anchors,list) or len({a.strip().lower() for a in anchors if isinstance(a,str) and a.strip()})<rules['min_inherited_anchors']:
        errors.append('Insufficient visible inherited anchors')
    for expected,actual in [('expected_supporting_legs','candidate_supporting_legs'),('expected_free_arms','candidate_free_arms')]:
        if expected in rules:
            count=observation.get(actual)
            if type(count) is not int or count!=rules[expected]:errors.append(actual+' does not match required body plan')
    return dict(status='PASS' if not errors else 'REJECTED',errors=errors,changed_regions=sorted(regions))

def require_gate(folder,parent,policy):
    folder=Path(folder);path=folder/'evolution_check.json'
    if not path.exists():raise ValueError('Mandatory dynamic-evolution visual gate is missing')
    record=json.loads(path.read_text(encoding='utf-8'))
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    expected=dict(parent_sha256=sha(parent),candidate_sha256=sha(folder/'image.png'),policy_sha256=policy['source_sha256'],
                  validator_sha256=sha(__file__))
    if record.get('provenance')!=expected or record.get('decision')!=evaluate(record.get('observation'),policy['semantic_gate']):
        raise ValueError('Evolution gate provenance/decision does not match this candidate')
    if record['decision']['status']!='PASS':raise ValueError('Evolution lacks required dynamic structural change: '+'; '.join(record['decision']['errors']))
    return record

def assess(folder,parent,policy,model_id,revision,root):
    from PIL import Image
    import torch
    from transformers import Qwen3VLForConditionalGeneration,Qwen3VLProcessor
    import time
    folder=Path(folder);parent=Path(parent);root=Path(root)
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    provenance=dict(parent_sha256=sha(parent),candidate_sha256=sha(folder/'image.png'),policy_sha256=policy['source_sha256'],validator_sha256=sha(__file__))
    path=folder/'evolution_check.json'
    if path.exists():return require_gate(folder,parent,policy)
    rules=policy['semantic_gate']
    template=dict(body_plan_changed=False,family_identity_retained=False,coherent_connected_anatomy=False,
        not_only_texture_pose_or_scale=False,candidate_supporting_legs=0,candidate_free_arms=0,
        inherited_anchors=['visible shared feature'],major_changes=[dict(region='torso',visible=False,description='Observed comparison, not desired design')],
        summary_ko='실제 두 이미지를 비교한 짧은 평가')
    system=('You are a skeptical visual quality reviewer. Image 1 is the actual parent; image 2 is the generated candidate. '
        'Report ONLY changes you can clearly SEE, never assume the generation instructions were followed. '
        'A larger turtle, shell ornament, bigger fins, detail, pose or recoloring is not a major body-plan metamorphosis. '
        'A genuinely new upright torso with ancestral forelegs now functioning as free arms is a body-plan change. '
        'Count actual supporting legs and free arms; reject extra limbs, disconnection or ambiguous anatomy. '
        'major_changes must use distinct regions from head, torso, supporting_limbs, inherited_structure, tail, '
        'with a concrete comparative description and visible boolean. Preserve at least two actually visible family anchors. '
        'Return ONLY one complete JSON object matching this template: '+json.dumps(template,ensure_ascii=False))
    images=[]
    for item in (parent,folder/'image.png'):
        with Image.open(item) as source:
            image=source.convert('RGB');image.thumbnail((512,512));images.append(image)
    content=[dict(type='image',image=str(parent)),dict(type='image',image=str(folder/'image.png')),
             dict(type='text',text='Compare actual parent and candidate against these acceptance requirements: '+json.dumps(rules,ensure_ascii=False))]
    processor_path=root/'models/huggingface/models--Qwen--Qwen-Image-2.1/snapshots'/revision/'processor'
    started=time.monotonic()
    processor=Qwen3VLProcessor.from_pretrained(str(processor_path),local_files_only=True)
    encoder=Qwen3VLForConditionalGeneration.from_pretrained(model_id,subfolder='text_encoder',revision=revision,
        torch_dtype=torch.bfloat16,device_map='cuda',cache_dir=str(root/'models/huggingface'),local_files_only=True).eval()
    formatted=processor.apply_chat_template([dict(role='system',content=system),dict(role='user',content=content)],
        tokenize=False,add_generation_prompt=True,enable_thinking=False)
    inputs=processor(text=[formatted],images=images,return_tensors='pt').to('cuda')
    with torch.inference_mode():output=encoder.generate(**inputs,do_sample=False,max_new_tokens=1000)
    raw=processor.tokenizer.decode(output[0,inputs['input_ids'].shape[1]:],skip_special_tokens=True).strip()
    if '</think>' in raw:raw=raw.split('</think>')[-1].strip()
    cleaned=raw
    if cleaned.startswith('```'):
        cleaned=cleaned.split('\n',1)[1].rsplit('```',1)[0].strip()
    try:observation=json.loads(cleaned)
    except (ValueError,TypeError):observation={}
    record=dict(schema_version='healthmon.evolution_check.v1',provenance=provenance,
        model_id=model_id,model_revision=revision,actual_two_image_vision_inference=True,training_performed=False,
        observation=observation,decision=evaluate(observation,rules),raw_output=raw,elapsed_seconds=round(time.monotonic()-started,3),
        limitations='Vision-based acceptance is fallible; direct review remains necessary for visual/anatomical quality.')
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return require_gate(folder,parent,policy)
