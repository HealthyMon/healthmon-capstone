"""Explicitly forced synthetic state demo. Stop live API before loading this GPU model."""
import argparse,copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--style',choices=['formal','play','blunt','rough','clean'],required=True);p.add_argument('--text',default='또 신발 끈이 풀려서 흐름이 끊겼어.');p.add_argument('--adapter');args=p.parse_args()
settings=json.loads((ROOT/'config/serving.json').read_text(encoding='utf-8'));os.environ['ADAPTER_PATH']=args.adapter or settings['adapter_path']
from src.model import QwenBackend
from src.agent import respond
from src.rules import RULES
c={'settings':{'name':'몽글이','speech_level':'formal' if args.style=='formal' else 'casual','profanity':'none' if args.style=='clean' else 'mild'},
 'traits':copy.deepcopy(RULES['initial']),'mood':{'valence':-25 if args.style=='rough' else 0,'energy':50},'recent':[],'memories':[],'activities':[],'candidates':[],'active_quests':[]}
axis={'formal':'courtesy','play':'playfulness','blunt':'bluntness','rough':'roughness','clean':'roughness'}[args.style];c['traits'][axis]=90
if args.style=='blunt':c['traits']['courtesy']=25
b=QwenBackend();trace=[];original=b.generate
def gen(*a,**kw):
 raw=original(*a,**kw);trace.append(raw);return raw
b.generate=gen
out,metrics=respond(b,c,args.text)
print(json.dumps({'test_kind':'forced synthetic state; not naturally grown DB personality','raw_attempts':trace,'final':out.model_dump(),'metrics':metrics},ensure_ascii=False,indent=2))
