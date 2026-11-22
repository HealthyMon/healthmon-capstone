"""Train continuity; evaluate real generated-history rollouts; restore current server."""
import argparse,json,subprocess,sys,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
OUT=ROOT/'runs/dialogue-continuity-20261121';DATA=ROOT/'data/dialogue_continuity_20261121'

def evaluate():
 from evaluate_healthmon_sft import load_candidate
 from prepare_qwen4b_common import make
 from difflib import SequenceMatcher
 selected=json.loads((OUT/'training/selection.json').read_text())['selected']['path']
 model=load_candidate(Path(selected),OUT/'evaluation-runtime')
 chains=[
  ['오늘 퍼즐을 시작했어.','풍경 그림이고 300조각이야.','테두리는 완성했고 하늘 부분을 맞추고 있어.','방금 말했잖아. 같은 질문은 하지 마.'],
  ['요즘 오카리나를 배우고 있어요.','짧은 민요 한 곡을 배웠어요.','느린 부분은 잘 되는데 빠른 부분이 어려워요.','연습 이야기는 그만하고 다른 이야기를 해요.'],
  ['운동 말고 쉬면서 놀고 싶어.','음악을 들을 거야.','오늘은 재즈를 골랐어.','질문하지 말고 그냥 들어줘.'],
 ]
 report={'scope':'3 fresh topics x 4 axis combinations x 4 turns; actual prior outputs passed to next turn','results':[],'complete':False}
 try:
  for ci,texts in enumerate(chains):
   for a,n in [(10,10),(10,90),(90,10),(90,90)]:
    recent=[];prior=[]
    for ti,text in enumerate(texts):
     row=make(f'rollout-{ci}-{a}-{n}-{ti}',text,'',axes=dict(activity=a,affinity=90,initiative=n),recent=list(reversed(recent[-6:])))
     row['context']['settings']['speech_level']='formal' if ci==1 else 'casual'
     started=time.monotonic()
     try: answer,metrics=model.chat({'text':text,'context':row['context']});error=None
     except Exception as exc:answer=None;metrics=model.last_metrics;error=str(exc)
     speech=answer['speech'] if answer else ''
     report['results'].append(dict(id=row['sample_id'],input=text,axes=row['context']['personality'],recent=row['context']['recent'],answer=answer,error=error,seconds=time.monotonic()-started,metrics=metrics,exact_prior_repeat=bool(speech) and speech in prior,max_prior_similarity=max([SequenceMatcher(None,speech,p).ratio() for p in prior] or [0])))
     if answer:recent.append({'speech':speech,'source_id':row['sample_id']});prior.append(speech)
     (OUT/'final-rollout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  report['complete']=True
  (OUT/'final-rollout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 finally:model.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--evaluate',action='store_true');args=p.parse_args()
 if args.evaluate:return evaluate()
 OUT.mkdir(parents=True,exist_ok=False)
 state={'status':'training','started':time.time(),'pid':os.getpid(),'server_promoted':False}
 def save():
  tmp=OUT/'status.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(OUT/'status.json')
 save()
 try:
  with (OUT/'training.stdout.log').open('w',encoding='utf-8') as log,(OUT/'training.stderr.log').open('w',encoding='utf-8') as err:
   subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/train_qwen4b.py'),'--data',str(DATA),'--run',str(OUT/'training'),'--init-adapter',str(ROOT/'runs/parameter-dialogue-20261121/training/checkpoint-epoch-2'),'--epochs','2','--lr','0.00002','--final-only-validation'],cwd=REPO,stdout=log,stderr=err,check=True)
  state['status']='evaluating';save()
  with (OUT/'evaluation.log').open('w',encoding='utf-8') as log:
   subprocess.run([sys.executable,'-X','utf8','-B',__file__,'--evaluate'],cwd=REPO,stdout=log,stderr=log,check=True)
  state.update(status='awaiting_semantic_review',completed=time.time());save()
 except Exception as exc:state.update(status='failed',error=str(exc));save();raise
 finally:
  # Restore the selected, already deployed model; do not auto-promote unreviewed training.
  with (OUT/'server-restore.log').open('w',encoding='utf-8') as log:
   code=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(REPO/'Start-Qwen4B.ps1'),'-LlmOnly'],cwd=REPO,stdout=log,stderr=log).returncode
  state['previous_server_restored']=code==0;save()

if __name__=='__main__':main()
