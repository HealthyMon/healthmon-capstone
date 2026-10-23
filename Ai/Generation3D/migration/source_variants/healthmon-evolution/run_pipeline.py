#!/usr/bin/env python3
"""Sequential, resumable local HEALTHMON inference. No fabricated fallback assets."""
import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from healthmon.prompts import clean_prompt, evolution_prompt, form_for, health_history, settings
from healthmon.quality import comparison_sheet, inspect_image
from healthmon.references import locate_zip, select_references, sha256
from healthmon.qwen_runner import MODEL_REVISION as QWEN_REVISION

STAGES = ['references', 'clean_source', 'clean_target', 'bootstrap_3d', 'render_source',
          'evolution', 'evolved_3d', 'render_evolved', 'rigging', 'validation', 'comparison']


class Blocked(RuntimeError):
    pass


def load_runtime(path):
    config = json.loads((ROOT/'configs/runtime.json').read_text())
    for name in ['qwen', 'trellis', 'rigging']:
        fragment = ROOT / f'configs/{name}_runtime.json'
        if fragment.exists():
            config.update(json.loads(fragment.read_text()))
    if Path(path).resolve() != (ROOT/'configs/runtime.json').resolve():
        config.update(json.loads(Path(path).read_text()))
    return config


def command(cmd, log_path, *, cwd=None):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info('Executing %s; output: %s', json.dumps([str(x) for x in cmd]), log_path)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT/'src') + os.pathsep + env.get('PYTHONPATH', '')
    env['PYTHONUNBUFFERED'] = '1'
    with log_path.open('a') as stream:
        stream.write('\nATTEMPT '+dt.datetime.now(dt.timezone.utc).isoformat()+'\n'+json.dumps([str(x) for x in cmd])+'\n')
        stream.flush()
        attempt_start=stream.tell()
        try:
            p = subprocess.run([str(x) for x in cmd], stdout=stream, stderr=subprocess.STDOUT,
                               cwd=cwd or ROOT, env=env)
        except FileNotFoundError as e:
            raise Blocked(f'Required executable unavailable: {e}') from e
    if p.returncode:
        with log_path.open(errors='replace') as failed_log:
            failed_log.seek(attempt_start)
            tail = failed_log.read()[-12000:]
        if any(x in tail.lower() for x in ['401', 'gatedrepo', 'gated repo', 'blocked_checkpoint',
                                          '403', 'access restricted', 'checkpoint access']):
            raise Blocked(f'Official checkpoint access is blocked (exit {p.returncode}). See {log_path}.\n{tail[-2500:]}')
        raise RuntimeError(f'Command failed, exit {p.returncode}. See {log_path}.\n{tail[-2500:]}')
    return [str(x) for x in cmd]


class Pipeline:
    def __init__(self, args):
        self.args = args
        self.config = load_runtime(args.config)
        self.source_form = args.source_form or form_for(args.scenario, args.source_stage)
        self.target_form = args.target_form or form_for(args.scenario, args.target_stage)
        spec = {'species': args.species, 'scenario': args.scenario, 'source_stage':args.source_stage,
                'target_stage':args.target_stage, 'source_form':self.source_form,
                'target_form':self.target_form, 'seed':args.seed, 'personality':args.personality,
                'reference_requested':str(args.reference_zip),
                'input_glb_sha256':sha256(args.input_glb) if args.input_glb else None,
                'prompt_config_sha256':sha256(ROOT/'configs/evolution.json'),
                'reference_regions_sha256':sha256(ROOT/'configs/reference_regions.json'),
                'qwen_sampling':{k:self.config.get(k) for k in ['qwen_width','qwen_height','qwen_steps']}}
        try:
            self.archive = locate_zip(args.reference_zip)
            spec['reference_zip_sha256'] = sha256(self.archive)
        except FileNotFoundError:
            self.archive = None
            spec['reference_zip_sha256'] = None
        self.spec = spec
        self.fingerprint = hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
        slug = f'{args.species}_{args.scenario}_s{args.source_stage}_to_s{args.target_stage}_seed{args.seed}'
        outputs = ROOT/'outputs'
        if args.run_dir:
            self.run = Path(args.run_dir).resolve()
        elif args.resume and args.resume != 'latest':
            self.run = Path(args.resume).resolve()
        elif args.resume:
            matches = sorted(outputs.glob(slug+'_*'))
            if not matches:
                raise ValueError('No matching previous run exists for --resume')
            self.run = matches[-1]
        else:
            self.run = outputs / (slug+'_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        self.run.mkdir(parents=True, exist_ok=True)
        for d in ['references','bootstrap','renders','qwen','trellis','rigging','validation','logs','rejected']:
            (self.run/d).mkdir(exist_ok=True)
        self.report_path = self.run/'validation/report.json'
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
            handlers=[logging.StreamHandler(), logging.FileHandler(self.run/'logs/pipeline.log')], force=True)
        if args.resume and self.report_path.exists():
            self.report = json.loads(self.report_path.read_text())
            if self.report['fingerprint'] != self.fingerprint:
                raise ValueError('Resume configuration/input hashes changed. Start a separate run.')
        else:
            if self.report_path.exists():
                raise ValueError('Run directory already contains a run; use --resume or another directory')
            self.report = {'schema_version':1, 'fingerprint':self.fingerprint,
                'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'spec':spec,
                'run_directory':str(self.run), 'overall_status':'NOT RUN',
                'visual_quality':'NOT RUN', 'stages':{s:{'status':'NOT RUN'} for s in STAGES},
                'limitations':['Reference artwork consists of unconfirmed drafts, not official canonical designs.',
                                'Unseen surfaces reconstructed by image/3D models require visual review.']}
        (self.run/'run_config.json').write_text(json.dumps({'spec':spec,'runtime':self.config},indent=2))
        self.save()

    def save(self):
        self.report['updated_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        temp = self.report_path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.report, indent=2))
        temp.replace(self.report_path)

    def input_fingerprint(self, name):
        """Invalidate downstream stages when their real inputs or requested semantics change."""
        files=[]
        params={'stage':name,'seed':self.args.seed}
        if name=='references':
            files=[self.archive,ROOT/'configs/reference_regions.json'] if self.archive else []
            params.update(species=self.args.species,scenario=self.args.scenario,
                          source=self.args.source_stage,target=self.args.target_stage)
        elif name in ['clean_source','clean_target']:
            role='source' if name=='clean_source' else 'target'
            n=self.args.source_stage if role=='source' else self.args.target_stage
            form=self.source_form if role=='source' else self.target_form
            files=[self.run/f'references/{role}_poster_region.png',self.run/f'references/{role}_crop.png']
            params.update(prompt=clean_prompt(self.args.species,n,form),revision=QWEN_REVISION,
                          sampling={k:self.config.get(k) for k in ['qwen_width','qwen_height','qwen_steps']})
            if role=='source' and self.args.input_glb:
                files=[self.args.input_glb];params={'skipped_for_input_glb':True}
        elif name=='evolution':
            files=[self.run/f'renders/{v}.png' for v in self.identity_views()]+[self.run/'references/target_clean.png']
            params.update(prompt=self.build_evolution_prompt(),revision=QWEN_REVISION,
                          sampling={k:self.config.get(k) for k in ['qwen_width','qwen_height','qwen_steps']})
        elif name in ['bootstrap_3d','evolved_3d']:
            files=[self.args.input_glb] if name=='bootstrap_3d' and self.args.input_glb else [
                self.run/('bootstrap/start_character.png' if name=='bootstrap_3d' else 'qwen/evolved.png'),
                ROOT/'src/healthmon/trellis_runner.py']
            params.update(config={k:v for k,v in self.config.items() if k.startswith('trellis_')})
        elif name in ['render_source','render_evolved','rigging','validation']:
            files=[self.run/{'render_source':'bootstrap/start_character.glb','render_evolved':'trellis/evolved.glb',
                            'rigging':'trellis/evolved.glb','validation':'rigging/final_rigged.glb'}[name],
                   ROOT/'src/healthmon/blender_tool.py']
            params.update(blender=self.config.get('blender'))
            if name=='rigging':
                files += [ROOT/'src/healthmon/rigging_runner.py',ROOT/'src/healthmon/riganything_blender_entry.py']
                params.update(config={k:v for k,v in self.config.items() if k.startswith('rigging_')})
        else:
            files=[self.run/p for p in ['references/source_poster_region.png','bootstrap/start_character.png',
                    'renders/three_quarter.png','qwen/evolved.png','trellis/evolved_preview.png','validation/pose_test.png']]
        params['files']={str(p):sha256(p) if Path(p).is_file() else None for p in files if p is not None}
        return hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()

    def legacy_provenance_valid(self,name):
        # First-run records written before fingerprints can be migrated only using actual evidence.
        if name=='references':
            return True  # Archive/region hashes are already part of the immutable run spec.
        if name=='clean_source' and self.args.input_glb:
            return True
        if name not in ['clean_source','clean_target','evolution']:
            return False
        try:
            path=self.run/{'clean_source':'bootstrap/start_character.png','clean_target':'references/target_clean.png',
                           'evolution':'qwen/evolved.png'}[name]
            meta=json.loads(Path(str(path)+'.json').read_text())
            if name=='evolution':
                expected=self.build_evolution_prompt()
            else:
                expected=clean_prompt(self.args.species,
                    self.args.source_stage if name=='clean_source' else self.args.target_stage,
                    self.source_form if name=='clean_source' else self.target_form)
            return (meta.get('status')=='PASS' and meta.get('model_revision')==QWEN_REVISION
                    and meta.get('source_prompt_sha256')==hashlib.sha256(expected.encode()).hexdigest()
                    and meta.get('output',{}).get('sha256')==sha256(path)
                    and all(Path(ref['path']).is_file() and sha256(ref['path'])==ref['sha256']
                            for ref in meta['ordered_references']))
        except (OSError,ValueError,KeyError):
            return False

    def stage(self, name, action):
        previous = self.report['stages'][name]
        signature=self.input_fingerprint(name)
        if self.args.resume and previous['status'] == 'PASS':
            artifacts = previous.get('artifact_sha256',{})
            valid_signature=(previous.get('input_fingerprint')==signature if previous.get('input_fingerprint')
                             else self.legacy_provenance_valid(name))
            if valid_signature and all(Path(p).is_file() and sha256(p)==h for p,h in artifacts.items()):
                previous['input_fingerprint']=signature
                self.save()
                logging.info('Resume: verified saved outputs for %s', name)
                return True
            logging.warning('Saved artifacts changed: rerunning %s and all downstream stages', name)
            for downstream in STAGES[STAGES.index(name):]:
                self.report['stages'][downstream] = {'status':'NOT RUN'}
        start = time.monotonic()
        if previous.get('status') in ['FAIL','BLOCKED']:
            self.report.setdefault('attempt_history',{}).setdefault(name,[]).append(previous)
        record = {'status':'NOT RUN','input_fingerprint':signature,
                  'started_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        self.report['stages'][name] = record
        self.save()
        try:
            result = action() or {}
            record.update(result)
            artifacts = result.get('outputs', [])
            for output in artifacts:
                if not Path(output).is_file() or Path(output).stat().st_size == 0:
                    raise RuntimeError(f'Stage {name} did not produce required output: {output}')
            record['artifact_sha256'] = {str(p):sha256(p) for p in artifacts}
            record['status'] = 'PASS'
            logging.info('PASS %s', name)
        except Blocked as e:
            record.update(status='BLOCKED',reason=str(e))
            logging.error('BLOCKED %s: %s', name, e)
        except Exception as e:
            record.update(status='FAIL',reason=f'{type(e).__name__}: {e}')
            logging.exception('FAIL %s', name)
        finally:
            record['duration_seconds'] = round(time.monotonic()-start,2)
            self.save()
        return record['status']=='PASS'

    def qwen(self, images, roles, prompt, output, stage):
        prompt_path = self.run / (f'qwen/{stage}_prompt.txt' if stage != 'evolution' else 'qwen/evolution_prompt.txt')
        prompt_path.write_text(prompt)
        cmd = [self.config['qwen_python'],ROOT/'src/healthmon/qwen_runner.py',
               '--images',*images,'--roles',*roles,'--prompt-file',prompt_path,
               '--output',output,'--seed',self.args.seed,
               '--width',self.config.get('qwen_width',768),'--height',self.config.get('qwen_height',768),
               '--steps',self.config.get('qwen_steps',40)]
        metadata_path=Path(str(output)+'.json')
        effective_path=output.with_suffix('.effective_prompt.txt')
        reuse=False
        if self.args.resume and output.is_file() and metadata_path.is_file() and effective_path.is_file():
            try:
                old=json.loads(metadata_path.read_text())
                expected=[{'index':i,'path':str(Path(p).resolve()),'role':role,'sha256':sha256(p)}
                          for i,(p,role) in enumerate(zip(images,roles),1)]
                recorded=[{k:ref.get(k) for k in ['index','path','role','sha256']}
                          for ref in old.get('ordered_references',[])]
                params=old.get('parameters',{})
                expected_prompt='Ordered reference images and their roles:\n'+'\n'.join(
                    f'Image {i}: {role}.' for i,role in enumerate(roles,1))+'\n\n'+prompt.strip()
                reuse=(old.get('status')=='PASS' and old.get('model_id')=='Qwen/Qwen-Image-2.1'
                    and old.get('model_revision')==QWEN_REVISION
                    and old.get('output',{}).get('sha256')==sha256(output)
                    and old.get('source_prompt_sha256')==sha256(prompt_path)
                    and old.get('prompt')==expected_prompt and effective_path.read_text().strip()==expected_prompt
                    and recorded==expected and all(params.get(k)==v for k,v in {
                        'seed':self.args.seed,'width':self.config.get('qwen_width',768),
                        'height':self.config.get('qwen_height',768),
                        'num_inference_steps':self.config.get('qwen_steps',40)}.items()))
            except (ValueError,OSError,KeyError):
                reuse=False
        if reuse:
            logging.info('Reuse verified real Qwen inference for QC recheck: %s',output)
        else:
            command(cmd, self.run/f'logs/{stage}.log')
        metadata=json.loads(metadata_path.read_text())
        if metadata.get('status') != 'PASS' or metadata.get('output',{}).get('sha256') != sha256(output):
            raise RuntimeError('Qwen generation provenance is incomplete or does not match the image')
        qc = inspect_image(output,output_report=self.run/f'validation/{stage}_image.json',
                           rejected_dir=self.run/f'rejected/{stage}')
        if qc['technical_status'] != 'PASS':
            raise RuntimeError(f'Image failed automated QC: {qc["failures"]}; rejected output retained')
        return {'outputs':[str(output),str(prompt_path),str(metadata_path),
                           str(output.with_suffix('.effective_prompt.txt')),
                           str(self.run/f'validation/{stage}_image.json')],'command':[str(x) for x in cmd],
                'execution':'REUSED_VERIFIED_QWEN_FOR_QC_RECHECK' if reuse else 'REAL_QWEN_INFERENCE',
                'visual_quality':qc['visual_quality'],'quality_report':str(self.run/f'validation/{stage}_image.json')}

    def references(self):
        if not self.archive:
            raise Blocked('Required reference ZIP missing. Place it at /workspace/input/healthmon_evolution_reference_pack.zip')
        self.selection = select_references(self.archive,self.run,self.args.species,self.args.scenario,
                                           self.args.source_stage,self.args.target_stage)
        return {'outputs':[str(self.run/'reference_selection.json'),
                           *[v[k] for v in self.selection['selected'].values() for k in ['raw_crop','poster_region']]],
                'archive':str(self.archive)}

    def clean(self, role):
        selection = json.loads((self.run/'reference_selection.json').read_text())['selected'][role]
        stage = self.args.source_stage if role=='source' else self.args.target_stage
        form = self.source_form if role=='source' else self.target_form
        output = self.run/('bootstrap/start_character.png' if role=='source' else 'references/target_clean.png')
        if role=='source' and self.args.input_glb:
            return {'outputs':[], 'execution':'SKIPPED: input GLB supplies current identity'}
        return self.qwen([selection['poster_region'],selection['raw_crop']],
                         ['primary_design_region','rough_location_hint'],
                         clean_prompt(self.args.species,stage,form), output, 'clean_'+role)

    def trellis(self, image, output, name):
        # Write resolved per-run runtime, including setup fragments, for independent replay.
        self.config = load_runtime(self.args.config)
        config_path = self.run/'runtime.resolved.json'
        config_path.write_text(json.dumps(self.config,indent=2))
        cmd = [sys.executable,ROOT/'src/healthmon/trellis_runner.py','--image',image,
               '--output',output,'--seed',self.args.seed,'--config',config_path]
        command(cmd,self.run/f'logs/{name}.log')
        return {'outputs':[str(output)],'command':[str(x) for x in cmd]}

    def bootstrap(self):
        output = self.run/'bootstrap/start_character.glb'
        if self.args.input_glb:
            if Path(self.args.input_glb).resolve() != output.resolve():
                shutil.copy2(self.args.input_glb,output)
            return {'outputs':[str(output)],'execution':'SUPPLIED_EXISTING_GLB','source':str(Path(self.args.input_glb).resolve())}
        return self.trellis(self.run/'bootstrap/start_character.png',output,'bootstrap_3d')

    def render(self, source):
        glb = self.run/('bootstrap/start_character.glb' if source else 'trellis/evolved.glb')
        out = self.run/('renders' if source else 'trellis/renders')
        validation_path=self.run/('validation/bootstrap_glb.json' if source else 'validation/evolved_glb.json')
        check_cmd=[self.config['blender'],'-b','--python-exit-code','1','-P',ROOT/'src/healthmon/blender_tool.py','--',
                   'validate','--input',glb,'--report',validation_path]
        command(check_cmd,self.run/('logs/validate_bootstrap_glb.log' if source else 'logs/validate_evolved_glb.log'))
        checked=json.loads(validation_path.read_text())
        if not checked.get('technical_valid'):
            raise RuntimeError(f'Generated GLB geometry/material validation failed: {validation_path}')
        cmd=[self.config['blender'],'-b','--python-exit-code','1','-P',ROOT/'src/healthmon/blender_tool.py','--',
             'render','--input',glb,'--out-dir',out,'--size','768']
        command(cmd,self.run/('logs/render_source.log' if source else 'logs/render_evolved.log'))
        outputs=[str(validation_path),*[str(out/(v+'.png')) for v in ['front','three_quarter','side','back']]]
        if not source:
            preview=self.run/'trellis/evolved_preview.png'
            shutil.copy2(out/'three_quarter.png',preview)
            outputs.append(str(preview))
        return {'outputs':outputs,'command':[str(x) for x in cmd]}

    def identity_views(self):
        views=self.config.get('qwen_identity_views',['front','three_quarter','side'])
        if not isinstance(views,list) or not views or len(set(views))!=len(views) or any(
            v not in ['front','three_quarter','side','back'] for v in views):
            raise ValueError('qwen_identity_views must be a nonempty list of unique rendered view names')
        return views

    def build_evolution_prompt(self):
        views=self.identity_views()
        prompt=evolution_prompt(self.args.species,self.args.source_stage,self.args.target_stage,
                                self.source_form,self.target_form,views,self.args.personality)
        history=health_history(self.args.scenario,self.target_form)
        prompt += '\nExercise History: '+history['exercise']+'\nDiet History: '+history['diet']+'\n'
        return prompt

    def evolve(self):
        views=self.identity_views()
        images=[str(self.run/f'renders/{v}.png') for v in views]+[str(self.run/'references/target_clean.png')]
        roles=['edit_base_primary_identity_'+views[0]]+['identity_'+v for v in views[1:]]+['design_only_same_individual_future_stage']
        return self.qwen(images,roles,self.build_evolution_prompt(),
                         self.run/'qwen/evolved.png','evolution')

    def rig(self):
        self.config = load_runtime(self.args.config)
        config_path=self.run/'runtime.resolved.json'
        config_path.write_text(json.dumps(self.config,indent=2))
        cmd=[sys.executable,ROOT/'src/healthmon/rigging_runner.py',
             '--config',config_path,'--seed',self.args.seed,
             '--input',self.run/'trellis/evolved.glb','--output-dir',self.run/'rigging',
             '--backend',self.config['rigging_backend'],'--repo',self.config['rigging_repo'],
             '--python',self.config['rigging_python'],'--checkpoint',self.config['rigging_checkpoint'],
             '--blender',self.config['blender']]
        command(cmd,self.run/'logs/rigging.log')
        return {'outputs':[str(self.run/'rigging/final_rigged.glb')],'command':[str(x) for x in cmd]}

    def validate(self):
        cmd=[self.config['blender'],'-b','--python-exit-code','1','-P',ROOT/'src/healthmon/blender_tool.py','--',
             'validate','--input',self.run/'rigging/final_rigged.glb',
             '--report',self.run/'validation/glb_report.json','--require-rig',
             '--preview-dir',self.run/'validation']
        command(cmd,self.run/'logs/validation.log')
        report=json.loads((self.run/'validation/glb_report.json').read_text())
        if report.get('status') != 'PASS':
            raise RuntimeError('Final GLB validation did not pass; inspect glb_report.json')
        return {'outputs':[str(self.run/'validation/glb_report.json'),str(self.run/'validation/pose_test.png')],
                'command':[str(x) for x in cmd]}

    def execute(self):
        actions=[self.references,lambda:self.clean('source'),lambda:self.clean('target'),self.bootstrap,
                 lambda:self.render(True),self.evolve,
                 lambda:self.trellis(self.run/'qwen/evolved.png',self.run/'trellis/evolved.glb','evolved_3d'),
                 lambda:self.render(False),self.rig,self.validate,
                 lambda:{'outputs':[str(comparison_sheet(self.run))]}]
        okay=True
        for name,action in zip(STAGES,actions):
            if not self.stage(name,action):
                okay=False
                break
            if self.args.stop_after == name:
                break
        statuses=[s['status'] for s in self.report['stages'].values()]
        if all(x=='PASS' for x in statuses): self.report['overall_status']='PASS'
        elif 'FAIL' in statuses: self.report['overall_status']='FAIL'
        elif 'BLOCKED' in statuses: self.report['overall_status']='BLOCKED'
        else: self.report['overall_status']='NOT RUN'
        self.report['technical_completion']=self.report['overall_status']=='PASS'
        self.report['visual_quality']='REVIEW_REQUIRED' if (self.run/'bootstrap/start_character.png').exists() else 'NOT RUN'
        self.report['final_artifact']=str(self.run/'rigging/final_rigged.glb') if self.report['technical_completion'] else None
        comparison_sheet(self.run)
        self.report['comparison_sheet']=str(self.run/'comparison.png')
        self.report['comparison_sheet_kind']='COMPLETE' if self.report['technical_completion'] else 'PARTIAL'
        self.save()
        print(json.dumps({'run_directory':str(self.run),'status':self.report['overall_status'],
                          'report':str(self.report_path),'final_artifact':self.report['final_artifact']},indent=2))
        return 0 if okay else 2


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--numeric-profiles',type=Path,help='Score-driven image evolution; stages and Forms are computed from recorded inputs')
    p.add_argument('--numeric-prepare-only',action='store_true',help='Validate numeric inputs and queue without GPU inference')
    p.add_argument('--species',choices=['mongle','tori','lucan'],default='lucan')
    p.add_argument('--scenario',choices=['A_fit_then_heavy','B_heavy_then_recovery'],default='A_fit_then_heavy')
    p.add_argument('--source-stage',type=int,choices=range(4),default=2)
    p.add_argument('--target-stage',type=int,choices=range(4),default=3)
    p.add_argument('--reference-zip',type=Path,default=Path('/workspace/input/healthmon_evolution_reference_pack.zip'))
    p.add_argument('--input-glb',type=Path)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--stop-after',choices=STAGES)
    p.add_argument('--resume',nargs='?',const='latest')
    p.add_argument('--run-dir',type=Path)
    p.add_argument('--config',type=Path,default=ROOT/'configs/runtime.json')
    p.add_argument('--source-form',choices=list(settings()['form_prompts']))
    p.add_argument('--target-form',choices=list(settings()['form_prompts']))
    p.add_argument('--personality',default=settings()['personality'])
    return p


if __name__=='__main__':
    args=parser().parse_args()
    if args.numeric_profiles:
        if args.input_glb or args.source_form or args.target_form or args.resume or args.stop_after or args.seed != 42:
            parser().error('Numeric mode derives stages/Forms from profiles, uses seed42 and performs image inference only; omit legacy pipeline overrides')
        cmd=[sys.executable,str(ROOT/'scripts/run_numeric_evolution.py'),'--profiles',str(args.numeric_profiles)]
        if args.run_dir:cmd.extend(['--run-dir',str(args.run_dir)])
        if args.numeric_prepare_only:cmd.append('--prepare-only')
        raise SystemExit(subprocess.call(cmd,cwd=ROOT))
    if args.numeric_prepare_only:
        parser().error('--numeric-prepare-only requires --numeric-profiles')
    if args.input_glb and not args.input_glb.is_file():
        parser().error('--input-glb must be an existing file')
    if args.target_stage < args.source_stage:
        parser().error('Target stage cannot be earlier than current stage')
    raise SystemExit(Pipeline(args).execute())
