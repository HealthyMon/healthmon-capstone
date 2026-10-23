"""BGE-M3 dense CLS embedding, CPU only; no remote code or paid API."""
import json, os, threading
from .db import ROOT

class Embedder:
    def __init__(self): self.model=None; self.lock=threading.Lock()
    def encode(self,text):
        import torch
        from transformers import AutoModel,AutoTokenizer
        with self.lock:
            if self.model is None:
                path=ROOT/os.getenv('EMBEDDING_PATH','models/bge-m3')
                self.tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
                self.model=AutoModel.from_pretrained(path,local_files_only=True).eval().cpu()
                self.revision=json.loads((ROOT/'config/bge-m3.json').read_text())['revision']
            batch=self.tokenizer(text,return_tensors='pt',max_length=512,truncation=False)
            if batch['input_ids'].shape[1]>512: raise ValueError('Memory exceeds 512 tokens')
            with torch.inference_mode():
                v=self.model(**batch).last_hidden_state[:,0]
                v=torch.nn.functional.normalize(v,p=2,dim=1)[0].tolist()
            if len(v)!=1024: raise ValueError('Embedding dimension mismatch')
            return v

embedder=Embedder()
