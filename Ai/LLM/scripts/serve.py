import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def resolve_adapter(adapter=None,base=False):
    if base:return None
    return adapter or os.getenv('ADAPTER_PATH') or json.loads((ROOT/'config/serving.json').read_text(encoding='utf-8'))['adapter_path']

def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    p=argparse.ArgumentParser()
    choice=p.add_mutually_exclusive_group()
    choice.add_argument('--adapter',help='Override config/serving.json adapter')
    choice.add_argument('--base',action='store_true',help='Explicitly serve the base model without LoRA')
    p.add_argument('--warmup',action='store_true');args=p.parse_args()
    adapter=resolve_adapter(args.adapter,args.base)
    if adapter:os.environ['ADAPTER_PATH']=adapter
    else:os.environ.pop('ADAPTER_PATH',None)
    (ROOT/'runs/server-worker.pid').write_text(str(os.getpid()))
    os.environ['PYTHONUTF8']='1'
    print('Serving adapter: '+(adapter or 'base'),flush=True)
    import uvicorn
    if args.warmup:
        from src.app import backend
        backend.load()
    uvicorn.run('src.app:app',host='127.0.0.1',port=8000,workers=1)

if __name__=='__main__':main()
