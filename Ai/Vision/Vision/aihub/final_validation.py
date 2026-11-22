"""Single final validation pass: contracts, held-out localization comparison, saved examples."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image
from detect import ROOT,DEFAULT_WEIGHT,load_model,predict,predict_regions,save,overlap
from region_model import load,locate

def counts(predictions,targets):
    used=set()
    for p in sorted(predictions,key=lambda x:x['confidence'],reverse=True):
        score,index=max(((overlap(p['bbox_xyxy'],b),i) for i,b in enumerate(targets) if i not in used),default=(0,-1))
        if score>=.5:used.add(index)
    return {'targets':len(targets),'predictions':len(predictions),'correct':len(used)}

def summarize(rows,key,multi=False):
    rows=[r for r in rows if not multi or r['ground_truth_count']>1]
    t=sum(r[key]['targets'] for r in rows);p=sum(r[key]['predictions'] for r in rows);c=sum(r[key]['correct'] for r in rows)
    return {'images':len(rows),'targets':t,'predictions':p,'correct':c,
            'precision':c/p if p else 0,'recall':c/t if t else 0,'f1':2*c/(p+t) if p+t else 0}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--regions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--user-image',type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('New output directory required; final validation must not overwrite prior evidence')
    a.output.mkdir(parents=True)
    tests=subprocess.run([sys.executable,str(ROOT/'test_multifood.py')],capture_output=True,text=True)
    (a.output/'tests.txt').write_text(tests.stdout+tests.stderr,encoding='utf-8')
    if tests.returncode:raise RuntimeError('Contract tests failed; see tests.txt')
    original=load_model()
    region=load(a.regions)
    source=json.loads((a.data/'eval.json').read_text(encoding='utf-8'))
    rows=[]
    for i,row in enumerate(source):
        baseline,image=predict(original,row['image'])
        proposed=locate(region,image,.5)
        rows.append({'image':row['image'],'ground_truth_count':len(row['boxes']),
                     'baseline':counts(baseline['foods'],row['boxes']),'locator':counts(proposed,row['boxes'])})
        if i%10==0:print(f'final evaluation {i+1}/{len(source)}',flush=True)
    report={'baseline':summarize(rows,'baseline'),'locator':summarize(rows,'locator'),
            'multi_baseline':summarize(rows,'baseline',True),'multi_locator':summarize(rows,'locator',True),
            'iou':.5,'baseline_threshold':.35,'locator_threshold':.5,'class_agnostic':True,
            'note':'Localization only on held-out official UEC test subset. Weak boxes from semantic masks; not Korean name accuracy or plate-instance ground truth.',
            'per_image':rows}
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    example=next((r['image'] for r in source if len(r['boxes'])>1),source[0]['image'])
    payload,image=predict_regions(original,region,example)
    save(payload,image,a.output/'multi_food_example')
    if a.user_image:
        payload,image=predict_regions(original,region,a.user_image)
        save(payload,image,a.output/'user_image')
    from legacy_weight import restore_weight
    restore_weight('cpu')
    report['legacy_weight_load']='passed; numerical food-weight accuracy not evaluated'
    report['contract_tests']='passed'
    report['training']=json.loads((a.regions.parent/'training.json').read_text(encoding='utf-8'))
    def sha256(path):
        digest=hashlib.sha256()
        with Path(path).open('rb') as f:
            for chunk in iter(lambda:f.read(8*1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()
    report['weights']={'original_detector_sha256':sha256(DEFAULT_WEIGHT),
                      'locator_sha256':sha256(a.regions), 'locator_file':str(a.regions.resolve()),
                      'legacy_weight_sha256':sha256(ROOT.parent/'02.중량 예측 모델/food_weight_checkpoint.pth')}
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='per_image'},indent=2))

if __name__=='__main__':main()
