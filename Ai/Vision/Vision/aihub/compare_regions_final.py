"""One final comparison against the previous locator; no test-time tuning."""
import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import torch
from pathlib import Path
from PIL import Image
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
from detect import ROOT,DEFAULT_WEIGHT,load_model,predict_regions,save
from region_model import load,locate
from final_validation import counts,summarize

def ap(ground_truth,predictions):
    with contextlib.redirect_stdout(io.StringIO()):
        gt=COCO();gt.dataset=ground_truth;gt.createIndex()
        if predictions:dt=gt.loadRes(predictions)
        else:
            dt=COCO();dt.dataset=dict(ground_truth,annotations=[]);dt.createIndex()
        evaluator=COCOeval(gt,dt,'bbox');evaluator.evaluate();evaluator.accumulate();evaluator.summarize()
    return {'map50_95':float(evaluator.stats[0]),'ap50':float(evaluator.stats[1])}

def evaluate(old,new,manifest):
    source=json.loads(manifest.read_text(encoding='utf-8'))
    rows=[];gt={'info':{},'images':[],'annotations':[],'categories':[{'id':1,'name':'food'}]}
    detections={'before':[],'after':[]}
    for i,row in enumerate(source,1):
        with Image.open(row['image']) as opened:image=opened.convert('RGB')
        gt['images'].append({'id':i,'width':image.width,'height':image.height})
        for x1,y1,x2,y2 in row['boxes']:
            gt['annotations'].append({'id':len(gt['annotations'])+1,'image_id':i,'category_id':1,
                                       'bbox':[x1,y1,x2-x1,y2-y1],'area':(x2-x1)*(y2-y1),'iscrowd':0})
        record={'image':row['image'],'ground_truth_count':len(row['boxes'])}
        for key,model in [('before',old),('after',new)]:
            proposals=locate(model,image,0.05)
            record[key]=counts([p for p in proposals if p['confidence']>=.5],row['boxes'])
            for proposal in proposals:
                x1,y1,x2,y2=proposal['bbox_xyxy']
                detections[key].append({'image_id':i,'category_id':1,'bbox':[x1,y1,x2-x1,y2-y1],'score':proposal['confidence']})
        rows.append(record)
    result={key:dict(summarize(rows,key),**ap(gt,detections[key])) for key in ('before','after')}
    result.update(multi_before=summarize(rows,'before',True),multi_after=summarize(rows,'after',True))
    return result,rows

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--regression-data',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--user-image',type=Path)
    a=p.parse_args()
    torch.set_num_threads(4)
    if a.output.exists():p.error('New output required')
    a.output.mkdir(parents=True)
    tests=subprocess.run([sys.executable,str(ROOT/'test_multifood.py')],capture_output=True,text=True)
    (a.output/'tests.txt').write_text(tests.stdout+tests.stderr,encoding='utf-8')
    if tests.returncode:raise RuntimeError('Contract tests failed')
    old=load(a.baseline);new=load(a.candidate)
    dish,rows=evaluate(old,new,a.data/'eval.json')
    (a.output/'dishseg_per_image.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    regression,_=evaluate(old,new,a.regression_data/'eval.json')
    # Predeclared selection: improve target-domain F1, limit prior-domain F1 loss to 5 points.
    selected=dish['after']['f1']>dish['before']['f1'] and regression['after']['f1']>=regression['before']['f1']-.05
    report={'dishseg':dish,'uec_regression':regression,'threshold':.5,'iou':.5,'ap_min_score':.05,
            'class_agnostic':True,'candidate_selected':selected,
            'selection_rule':'DishSeg F1 increases and UEC F1 drop <= 0.05; fixed before evaluation',
            'training':json.loads((a.candidate.parent/'training.json').read_text()),
            'baseline_sha256':sha(a.baseline),'candidate_sha256':sha(a.candidate),
            'original_aihub_sha256':sha(DEFAULT_WEIGHT),
            'original_weight_sha256':sha(ROOT.parent/'02.중량 예측 모델/food_weight_checkpoint.pth'),
            'baseline_input_size':[old.transform.min_size[0],old.transform.max_size],
            'candidate_input_size':[new.transform.min_size[0],new.transform.max_size],
            'scope':'Food instance localization, not physical plate counting or food-name accuracy',
            'dishseg_provenance':json.loads((a.data/'provenance.json').read_text()),'contract_tests':'passed'}
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    naming=load_model()
    source=json.loads((a.data/'eval.json').read_text())
    for row in [r for r in source if len(r['boxes'])>1][:3]:
        payload,image=predict_regions(naming,new,row['image'])
        save(payload,image,a.output/('example_'+Path(row['image']).stem))
    if a.user_image:
        payload,image=predict_regions(naming,new,a.user_image)
        save(payload,image,a.output/'user_image')
    from legacy_weight import restore_weight
    restore_weight('cpu')
    report['legacy_weight_load']='passed; accuracy not evaluated'
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    active={'path':str((a.candidate if selected else a.baseline).resolve()),
            'evaluation':str((a.output/'metrics.json').resolve())}
    (ROOT.parent/'active_region.json').write_text(json.dumps(active,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='dishseg_provenance'},indent=2))

if __name__=='__main__':main()
