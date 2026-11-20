import json, os, sys, threading, time
from .db import ROOT
from .prompts import messages

class QwenBackend:
    name='qwen3.5-9b-bf16'
    def __init__(self,runtime_guidance=True): self.model=None; self.lock=threading.Lock();self.runtime_guidance=runtime_guidance
    def load(self):
        if self.model is not None:return
        started=time.monotonic()
        from .qwen_loading import loading_kwargs, verify_adapter_base
        path=ROOT/os.getenv('MODEL_PATH','models/qwen3.5-9b')
        quantization=os.getenv('MODEL_QUANTIZATION','none')
        kwargs=loading_kwargs(quantization)
        adapter=os.getenv('ADAPTER_PATH')
        if adapter:verify_adapter_base(path,ROOT/adapter)
        self.name=path.name+('-nf4' if quantization=='nf4' else '-bf16')
        from filelock import FileLock,Timeout
        self.gpu_lease=FileLock(str(ROOT/'runtime/gpu.lock'),timeout=0)
        try:self.gpu_lease.acquire()
        except Timeout:raise RuntimeError('Another Healthmon process is using the GPU')
        import torch
        torch.set_num_threads(8)
        from transformers import AutoTokenizer,Qwen3_5ForConditionalGeneration
        imported=time.monotonic()
        free,_=torch.cuda.mem_get_info()
        required=sum(file.stat().st_size for file in path.glob('*.safetensors')) + 1536 * 1024**2
        if quantization=='none' and free < required:
            self.gpu_lease.release()
            raise RuntimeError('Insufficient free GPU memory for Qwen and its inference workspace')
        self.tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
        tokenized=time.monotonic()
        try:
            self.model=Qwen3_5ForConditionalGeneration.from_pretrained(path,**kwargs)
        except Exception:
            self.gpu_lease.release();raise
        weighted=time.monotonic()
        if adapter:
            from peft import PeftModel
            try:self.model=PeftModel.from_pretrained(self.model,ROOT/adapter)
            except Exception:
                self.model=None;torch.cuda.empty_cache();self.gpu_lease.release();raise
            self.name+='-lora'
        self.model.eval()
        self.load_timings={'runtime_import_seconds':imported-started,
                           'tokenizer_load_seconds':tokenized-imported,
                           'weights_load_seconds':weighted-tokenized,
                           'adapter_load_seconds':time.monotonic()-weighted}
    def generate(self,context,text,repair=None):
        return self.generate_prompt(messages(context,text,repair,runtime_guidance=self.runtime_guidance))

    def generate_prompt(self,prompt,**generation_overrides):
        """Run an existing caller's prompt without changing its input contract."""
        import torch
        with self.lock:
            self.load()
            batch=self.tokenizer.apply_chat_template(prompt,tokenize=True,
                 enable_thinking=False,add_generation_prompt=True,return_dict=True,return_tensors='pt').to('cuda')
            n=batch['input_ids'].shape[1]
            if n>4096: raise ValueError('Context exceeds inference budget; no silent truncation')
            print(f'[Qwen] Processing {n} prompt tokens',file=sys.stderr,flush=True)
            # The Editor shares this GPU. Release unused cached workspaces between turns
            # instead of letting Windows page model memory when a longer prompt arrives.
            torch.cuda.empty_cache()
            out=None
            try:
                with torch.inference_mode():
                    options=dict(max_new_tokens=240,do_sample=True,temperature=0.7,top_p=0.9,
                                 repetition_penalty=1.05,max_time=90)
                    options.update(generation_overrides)
                    out=self.model.generate(**batch,**options)
                return self.tokenizer.decode(out[0,n:],skip_special_tokens=True)
            finally:
                del out, batch
                torch.cuda.empty_cache()
