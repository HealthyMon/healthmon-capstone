import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def resolve_adapter(adapter=None,base=False):
    if base:return None
    return adapter or os.getenv('ADAPTER_PATH') or json.loads((ROOT/'config/serving.json').read_text(encoding='utf-8'))['adapter_path']

def main():
    from dotenv import load_dotenv
    p=argparse.ArgumentParser()
    p.add_argument('--env-file',type=Path,default=ROOT/'.env',help='Local credentials file (never committed)')
    p.add_argument('--model-path',type=Path,help='Existing local base model directory')
    p.add_argument('--embedding-path',type=Path,help='Existing local BGE-M3 directory')
    choice=p.add_mutually_exclusive_group()
    choice.add_argument('--adapter',help='Override config/serving.json adapter')
    choice.add_argument('--base',action='store_true',help='Explicitly serve the base model without LoRA')
    p.add_argument('--warmup',action='store_true',help='Legacy flag; models remain on demand');args=p.parse_args()
    load_dotenv(args.env_file)
    from src.db import connect
    with connect() as connection:
        connection.execute((ROOT/'migrations/003_food_analyses.sql').read_text(encoding='utf-8'))
    for key,path in (('MODEL_PATH',args.model_path),('EMBEDDING_PATH',args.embedding_path)):
        if path is not None:
            if not path.is_dir():p.error(f'{key} directory does not exist: {path}')
            os.environ[key]=str(path.resolve())
    adapter=resolve_adapter(args.adapter,args.base)
    if adapter and not (ROOT/adapter/'adapter_config.json').is_file():
        p.error(f'LoRA adapter_config.json not found: {ROOT/adapter}')
    if adapter:os.environ['ADAPTER_PATH']=adapter
    else:os.environ.pop('ADAPTER_PATH',None)
    (ROOT/'runs').mkdir(exist_ok=True)
    (ROOT/'runtime').mkdir(exist_ok=True)
    (ROOT/'runs/server-worker.pid').write_text(str(os.getpid()))
    os.environ['PYTHONUTF8']='1'
    print('Serving adapter: '+(adapter or 'base'),flush=True)
    import uvicorn
    if args.warmup:
        print('Conversation mode: preload starts only when the dialogue tab opens.',flush=True)
    uvicorn.run('src.app:app',host='127.0.0.1',port=8000,workers=1)

if __name__=='__main__':main()
