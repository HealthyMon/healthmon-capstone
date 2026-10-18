#!/usr/bin/env python3
"""Automatically enqueue score-derived evolution on a crossed level milestone."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import prepare_branch_evolution as helper

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from healthmon.numeric_router import compile_for_species as compile_numeric_evolution
from healthmon.numeric_source_guard import verify_numeric_parent


def prepare_profiles(profiles_path, run):
    profiles_path = Path(profiles_path).resolve()
    run = Path(run).resolve()
    helper.RUN = run
    config = json.loads(profiles_path.read_text())
    tasks = []
    skipped = []
    for index, item in enumerate(config['profiles']):
        profile = {key: item[key] for key in ('species','previous_level','level','previous_form','records','personality')}
        compiled = compile_numeric_evolution(profile)
        if compiled is None:
            skipped.append({'case_id':item['case_id'],'reason':'No25-level milestone crossed; no inference queued'})
            continue
        parent = ROOT/item['previous_image']
        meta = json.loads(Path(str(parent)+'.json').read_text())
        parent_validation=verify_numeric_parent(parent,meta,profile)
        with helper.Image.open(parent) as source_image:
            box=item['face_box']
            if len(box)!=4 or not (0<=box[0]<box[2]<=source_image.width and 0<=box[1]<box[3]<=source_image.height):
                raise ValueError('Identity crop must be entirely within its actual previous image')
        crop = helper.identity_crop(parent,item['case_id']+'_previous_central_face',tuple(item['face_box']))
        conditions = {**compiled, 'profile_id':item['case_id'],'label_ko':item['label_ko'],
            'species':profile['species'], 'source_stage':compiled['transition']['source_stage'],
            'target_stage':compiled['transition']['target_stage'],'target_level':compiled['transition']['level'],
            'form':compiled['decision']['form'],'branch':compiled['decision']['branch'],
            'full_previous_source':str(parent),'full_previous_source_sha256':helper.sha(parent),
            'conditioning_mode':'One actual previous central-face identity crop; no target-stage or target-form reference',
            'target_design_reference_count':0,'full_body_target_reference_count':0,
            'body_history_inheritance':'Textual; actual preceding full-body geometry is not an image condition',
            'parent_stage_and_form_validation':parent_validation,
            'automatic_visual_pass':False,'trellis_or_rigging':False}
        conditions.pop('prompt')
        helper.save(run/'compiled'/f"{item['case_id']}.json",compiled)
        task = helper.enqueue(item['case_id'],compiled['prompt'],[crop],
            [f"actual_previous_{profile['species']}_central_face_identity_only"],conditions,order=index)
        tasks.append(task)
    helper.save(run/'input_profiles.json',config)
    helper.save(run/'plan.json',{'purpose':'Actual numeric-input-controlled sacred evolution comparison',
        'profile_source':str(profiles_path),'profile_source_sha256':helper.sha(profiles_path),
        'prepared_inferences':len(tasks),'cases':[t['case_id'] for t in tasks], 'skipped':skipped,
        'same_seed':42,'target_stages':sorted({t['conditions']['target_stage'] for t in tasks}),'training':False,'trellis_or_rigging':False,
        'inference_path':'numeric_evolution.compile_numeric_evolution -> this score-driven enqueue -> qwen_branch_worker -> actual diffusers QwenImage21Pipeline',
        'preparer_sha256':helper.sha(Path(__file__))})
    return {'run_dir':str(run),'prepared':len(tasks),'skipped':len(skipped)}


def prepare_individual_profiles(profiles_path, run):
    """V2 shares the real Qwen worker; each distinct persistent body has one queue item."""
    import hashlib
    from healthmon.individual_evolution import compile_individual, digest, design_planning_request
    from healthmon.qwen_runner import MODEL_ID, MODEL_REVISION
    from run_selected_3d import load_runtime
    runtime=load_runtime(ROOT/'configs/runtime.json')
    config=json.loads(Path(profiles_path).read_text())
    run=Path(run).resolve(); run.mkdir(parents=True,exist_ok=True)
    catalogue=json.loads((ROOT/'records/models_catalog.json').read_text())
    jobs=[]; seen=set(); compiled_rows=[]; skipped=[]
    for index,item in enumerate(config['profiles']):
        case_id=item['case_id']
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',case_id): raise ValueError('Invalid case_id')
        c=compile_individual(item)
        if c is None:
            skipped.append(dict(case_id=case_id,reason='No Lv15/30/50 milestone crossed')); continue
        stage=c['transition']['source_stage']
        parent=item.get('previous_asset')
        if parent:
            if parent['stage']!=stage or parent['species']!='lucan': raise ValueError('Previous asset stage/species mismatch')
            image=(ROOT/parent['image']).resolve()
            if helper.sha(image)!=parent['sha256']: raise ValueError('Previous image hash mismatch')
            if parent.get('model'):
                model=(ROOT/parent['model']).resolve()
                render_meta=json.loads((ROOT/parent['render_metadata']).read_text())
                if helper.sha(model)!=render_meta['source_sha256']: raise ValueError('Previous GLB/render mismatch')
                if render_meta.get('target_stage',stage)!=stage: raise ValueError('Previous GLB stage mismatch')
                if render_meta.get('image_sha256') and helper.sha(image)!=render_meta['image_sha256']: raise ValueError('Previous GLB render image mismatch')
                provenance=dict(kind='actual_glb_render',model=str(model),model_sha256=helper.sha(model),render_metadata=render_meta)
            else:
                meta=json.loads(Path(str(image)+'.json').read_text())
                if meta.get('status')!='COMPLETED' or meta.get('output',{}).get('sha256')!=helper.sha(image): raise ValueError('Previous PNG is not verified actual inference')
                if meta.get('evaluation_conditions',{}).get('target_stage')!=stage: raise ValueError('Previous Qwen stage mismatch')
                provenance=dict(kind='previous_actual_qwen_png',metadata=str(image)+'.json')
        else:
            # Canonical V1 is a comparison parent only; no target-stage reference is conditioned.
            row=next(r for r in catalogue if r['species']=='lucan' and r['stage']==stage and r['form']==('starter' if stage==0 else 'healthy'))
            stem=f's{stage}_'+('starter' if stage==0 else 'healthy')
            model=ROOT/row['model']; image=ROOT/f'images/3d/{stem}/three_quarter.png'
            render_meta=json.loads((ROOT/f'records/3d/{stem}/render_metadata.json').read_text())
            if helper.sha(model)!=row['model_sha256'] or render_meta['source_sha256']!=row['model_sha256']: raise ValueError('V1 GLB/render provenance mismatch')
            preserved=json.loads((ROOT/'records/v2/v1_preservation.json').read_text())['files']
            recorded=next(r['sha256'] for r in preserved if r['path']==str(image.relative_to(ROOT)))
            if helper.sha(image)!=recorded: raise ValueError('V1 reference render changed')
            provenance=dict(kind='actual_glb_render',model=str(model),model_sha256=row['model_sha256'],render_metadata=render_meta)
        full_previous=image
        mode=config.get('conditioning_mode','identity_crop')
        if mode not in ('planner_only','identity_crop','identity_and_process'):
            raise ValueError('Unknown V2 conditioning_mode')
        # Full actual appearance goes to the vision planner in every mode. Native
        # diffusion conditioning can be isolated for a controlled capability test.
        if mode!='planner_only' and not parent:
            boxes={0:(300,350,640,725),1:(375,540,620,775),2:(300,345,650,725)}
            box=boxes[stage]
            cropdir=ROOT/'outputs/v2/identity_references';cropdir.mkdir(parents=True,exist_ok=True)
            cropped=cropdir/f"{helper.sha(image)[:16]}_s{stage}_{digest(list(box))[:8]}.png"
            with helper.Image.open(image) as im:
                if not (0<=box[0]<box[2]<=im.width and 0<=box[1]<box[3]<=im.height):
                    raise ValueError('Identity crop exceeds actual previous render')
                if not cropped.exists():im.crop(box).save(cropped)
            helper.save(cropped.with_suffix('.json'),dict(source=str(image),source_sha256=helper.sha(image),box=list(box),
                        purpose='Actual previous GLB face/color identity only; no target anatomy',output_sha256=helper.sha(cropped)))
            provenance['full_render']=str(image);provenance['identity_crop']=dict(box=list(box),sha256=helper.sha(cropped))
            # A frame-filling head crop makes the edit model produce a huge head
            # and cut off the descendant's tail. Preserve identity at body-sheet
            # scale, with room to invent the trunk and terrestrial stance.
            from PIL import Image
            framed=cropped.with_name(cropped.stem+'_identity_canvas_v1.png')
            if not framed.exists():
                patch=Image.open(cropped).convert('RGBA');patch.thumbnail((160,160))
                canvas=Image.new('RGBA',(768,768),'white')
                canvas.alpha_composite(patch,(160,200));canvas.convert('RGB').save(framed)
            helper.save(framed.with_suffix('.json'),dict(source=str(cropped),source_sha256=helper.sha(cropped),
                purpose='Small inherited face on empty body-design canvas; preserves identity without oversized head',
                canvas=[768,768],maximum_patch_size=[160,160],position=[160,200],output_sha256=helper.sha(framed)))
            provenance['identity_canvas']=dict(path=str(framed),sha256=helper.sha(framed))
            image=framed
        refs=[] if mode=='planner_only' else [image]
        roles=[] if not refs else ['Actual previous Lucan appearance: lineage palette and motifs ONLY; freely replace anatomy']
        if mode=='identity_and_process':
            manifest=json.loads((ROOT/'outputs/v2/reference_data/manifest.json').read_text())
            art=next(r for r in manifest['licensed_art'] if r['id']=='shibu')
            licensed=ROOT/art['path']
            if art['license']!='CC0-1.0' or helper.sha(licensed)!=art['sha256']:
                raise ValueError('Unverified license or changed process reference')
            refs.append(licensed);roles.append('CC0 branching process examples ONLY; never copy colors, species, faces, limbs or final designs; output one new Lucan')
        ref_rows=[dict(path=str(p),sha256=helper.sha(p),role=role) for p,role in zip(refs,roles)]
        planning_refs=[dict(path=str(full_previous),sha256=helper.sha(full_previous),role='Full actual previous appearance for lineage-aware concept planning, not a target anatomical template')]
        params=dict(width=768,height=768,output_resolution=768,num_inference_steps=40,true_cfg_scale=1.0)
        allowed_parameters={'width','height','output_resolution','num_inference_steps','true_cfg_scale'}
        if set(config.get('generation_parameters',{}))-allowed_parameters:raise ValueError('Unknown generation parameter')
        params.update(config.get('generation_parameters',{}))
        request=design_planning_request(c)
        # Give continuous coordinates a stable meaning. Bare floats with artistic
        # names leave the language model free to invert their intended direction.
        directed=json.loads(request['user'])
        directed['axis_semantics_0_to_1']={
            'kinetic_flow':'contained economical movement -> expansive rhythmic propulsion; interpret the entire locomotor silhouette',
            'support_distribution':'rear-centered visual gravity -> front-centered visual gravity; redistribute the trunk and support together, not isolated limb sizes',
            'spatial_spread':'gathered main volumes and narrow gaps -> open arrangement and broad deliberate negative spaces',
            'visual_density':'light sparse main masses -> dense substantial main masses; not fatness and not detail count',
            'social_openness':'guarded inward structural curves -> receptive outward structural curves; independent of imposing size',
            'self_direction':'receptive converging form rhythm -> strongly directional self-led form rhythm; not a warrior template',
            'surface_integration':'separate graphic motif groups -> unified flowing graphic motif system; both must remain attractive',
            'developmental_momentum':'consolidating established movement organization -> emerging expansive movement organization, from actual chronological records',
            'structural_persistence':'lightly established organization -> strongly consolidated acquired structures',
            'contrast_rhythm':'even transitions among main volumes -> deliberate alternating large/small or curved/angular main volumes',
            'coiled_to_expansive':'gathered or coiled organizing axis -> unfolded expansive organizing axis',
            'overall_presence':'compact intimate presence -> monumental whole-body volume and scale cues; never simply enlarge a belly',
        }
        directed['interpretation_contract']='Use these coupled continuous directions consistently. Nearby coordinates should retain related organization. No axis selects a finished form or an anatomical measurement. Current, history and individual seed all remain inputs.'
        directed['stat_definitions']={
            'UpperBody':'Exercise development of the upper body, interpreted jointly as whole-body support and design balance, not an arm-size command',
            'LowerBody':'Exercise development of the lower body, interpreted jointly as whole-body propulsion and support, not a leg-size command',
            'Nutrition':'Diet quality/support score; not calorie quantity, and not evidence of an unrecorded specific food or protein intake',
            'EnergyBalance':'Dietary calorie surplus/deficit from -1 to +1; zero is balance. NOT magical energy, electricity or attack power',
            'Activity':'Habitual activity tendency, not body fat and not a requirement for an action pose',
            'Affinity':'Long-term affiliative temperament; can coexist with intimidating size, strength or awkward appearance',
            'Initiative':'Long-term proactive tendency; not compulsory warrior, muscle, bipedal or giant morphology',
        }
        if request['version'].startswith('lucan-generative-director-v7-grounded'):
            directed.pop('stat_definitions',None)
            groups=[['kinetic_flow','support_distribution','spatial_spread'],
                    ['visual_density','surface_integration','overall_presence'],
                    ['social_openness','self_direction','developmental_momentum','contrast_rhythm']]
            template=dict(design_thesis_ko='새 전체 형태와 인상을 한국어로 제안',
                reasoning=[dict(source_axes=axes,decision_ko='구체적인 전체 조형 결정',form_why_ko='이 조형이 주어진 복합 지수를 표현하는 방식') for axes in groups],
                structural_changes=['whole-body main mass organization','head trunk and support reorganization','inherited motif becomes a silhouette structure'],
                lineage_anchors=['first actual inherited signature','second actual inherited signature'],image_prompt='130-170 English words describing this ONE newly designed whole creature')
            request['system']+=' Copy source_axes arrays EXACTLY from this output template, filling all other text with your own proposed design. Keep each Korean sentence under 40 characters. Do not narrate numerical or dietary claims. A single memorable main form, not many accessories on a generic wolf or dragon. OUTPUT TEMPLATE: '+json.dumps(template,ensure_ascii=False)
        if request['version'].startswith('lucan-generative-director-v6-causal'):
            groups=[['UpperBody','LowerBody','Activity','Initiative'],
                    ['Nutrition','EnergyBalance','Activity','UpperBody','LowerBody'],
                    ['Affinity','Initiative']+(['history'] if c['history']['available'] else [])]
            template=dict(design_thesis_ko='Fill one Korean whole-form design hypothesis',
                reasoning=[dict(source_fields=fields,decision_ko='Fill a concrete whole-form decision',why_ko='Explain this combined supplied evidence in Korean') for fields in groups],
                structural_changes=['main mass organization','head/trunk/support relation','inherited motif structural role'],
                lineage_anchors=['choose actual inherited signature','choose second actual inherited signature'],image_prompt='Fill 130-170 English words based on the same thesis and decisions')
            request['system']+=' IMPORTANT: Copy the source_fields arrays EXACTLY from this output template. They name RAW supplied statistics. Never substitute computed axis names such as SupportDistribution, KineticFlow or MotifMigration. Fill all other text with your original grounded design. OUTPUT TEMPLATE: '+json.dumps(template,ensure_ascii=False)
            request['system']+=' Keep design_thesis_ko under 40 Korean characters, each decision_ko under 25 and each why_ko under 40. DO NOT write numerals in these Korean fields: exact values are attached by code. Treat around 50 as moderate, 0 and 100 as extremes. Calorie balance is NOT supernatural power. Do not invent diet contents, physiological facts or unobserved experiences. Complete the entire JSON, including image_prompt.'
            request['inference']['max_new_tokens']=1100
        request['user']=json.dumps(directed,ensure_ascii=False,sort_keys=True)
        request['version']+='-defined-axes'
        key=digest(dict(body_key=c['body_key'],references=ref_rows,planning_references=planning_refs,design_request=request,conditioning_mode=mode,model=MODEL_ID,revision=MODEL_REVISION,parameters=params,
                        planner=helper.sha(ROOT/'src/healthmon/individual_evolution.py'),worker=helper.sha(ROOT/'scripts/qwen_branch_worker.py'),pipeline=helper.sha(Path(runtime['qwen_pipeline_file']))))
        cache=ROOT/'outputs/v2/body_cache'/key
        cache.mkdir(parents=True,exist_ok=True)
        output=cache/'body.png'
        prompt_path=cache/'prompt.txt'
        prompt_path.write_text(c['prompt']+'\n')
        row=dict(case_id=case_id,label_ko=item.get('label_ko',case_id),input=item,compiled=c,
                 generation_key=key,output=str(output),references=ref_rows,planning_references=planning_refs,conditioning_mode=mode,previous_provenance=provenance,
                 visual_quality='REQUIRES_REVIEW',body_reuse_within_batch=key in seen)
        compiled_rows.append(row)
        helper.save(run/'compiled'/f'{case_id}.json',row)
        if key in seen: continue
        seen.add(key)
        task=dict(case_id=key[:20],design_planning=request,planning_images=[str(full_previous)],images=[str(p) for p in refs],roles=[r['role'] for r in ref_rows],
                  prompt_path=str(prompt_path),output=str(output),seed=c['seed'],parameters=params,
                  conditions=dict(version=c['version'],body_key=c['body_key'],generation_key=key,
                    recipe=c['recipe'],target_stage=c['transition']['target_stage'],source_stage=stage,
                    conditioning_mode=mode,planning_references=planning_refs,previous_provenance=provenance,visual_quality='REQUIRES_REVIEW',training_performed=False))
        helper.save(run/'queue'/f'{index:03d}_{key[:20]}.json',task);jobs.append(task)
    helper.save(run/'input_profiles.json',config)
    helper.save(run/'plan.json',dict(version='v2',profiles=compiled_rows,skipped=skipped,prepared_inferences=len(jobs),
                 training_performed=False,visual_quality='REQUIRES_REVIEW',levels=[15,30,50],
                 history_notice='Only explicitly supplied records are used; synthetic fixtures are labeled.'))
    return dict(run_dir=str(run),prepared=len(jobs),skipped=len(skipped),profiles=len(compiled_rows),version='v2')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare_profiles(args.profiles,args.run_dir),ensure_ascii=False))

if __name__=='__main__':
    main()
