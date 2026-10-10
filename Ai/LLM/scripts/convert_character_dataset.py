"""Convert reviewed exports through the existing assistant-only ChatML encoder.

This command never loads model weights, trains, downloads, or overwrites a file.
Analyzer classification and character speech remain different tasks/targets.
"""
import argparse
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.chatml import encode_chatml
from src.character_lab_schema import ConversationLabel
from src.character_lab_models import CONVERSATION_SYSTEM
from src.contracts import ModelOutput


def convert_row(row, kind, tokenizer, max_length=4096):
    if row['reviewer_status'] not in ('approved','corrected'):
        raise ValueError('Unreviewed training row rejected')
    if kind=='analyzer':
        label=ConversationLabel.model_validate(row['label']).model_dump()
        prompt=row.get('prompt') or [{'role':'system','content':CONVERSATION_SYSTEM},
                {'role':'user','content':json.dumps({'text':row['text']},ensure_ascii=False)}]
        target=json.dumps(label,ensure_ascii=False,separators=(',',':'))
    else:
        prompt=row['prompt']
        response=row['response']
        if not response.strip():
            raise ValueError('Empty response target')
        # Existing serving/training uses a guarded speech envelope, not analysis labels.
        contract=ModelOutput.model_validate({**row['response_contract'],'speech':response}).model_dump()
        target=json.dumps(contract,ensure_ascii=False,separators=(',',':'))
    encoded=encode_chatml(tokenizer,prompt,target,max_length)
    return {'sample_id':row['sample_id'],'task':kind,'messages':prompt+[{'role':'assistant','content':target}],
            'reviewer_status':row['reviewer_status'],'prompt_version':row['prompt_version'],
            'token_count':len(encoded['input_ids']), **encoded}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',required=True,choices=['analyzer','response'])
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--max-length',type=int,default=4096)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists; choose a new export path')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'models/qwen3.5-9b',local_files_only=True)
    rows=[convert_row(json.loads(line),args.kind,tokenizer,args.max_length)
          for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    with args.output.open('x',encoding='utf-8') as out:
        for row in rows:out.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(json.dumps({'rows':len(rows),'task':args.kind,'max_tokens':max((r['token_count'] for r in rows),default=0),'training_executed':False}))


if __name__=='__main__':main()
