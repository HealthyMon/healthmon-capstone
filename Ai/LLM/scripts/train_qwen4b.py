"""Fresh 4B QLoRA candidate using the unchanged Healthmon prompt and JSON contract.

Never loads a 9B adapter or changes serving.json. Validation selects checkpoints;
the historical final test is not used by this script.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1]))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
from src.chatml import encode_chatml
from src.prompts import messages
from src.qwen_loading import loading_kwargs, verify_adapter_base


def training_prompt(row):
    target = json.dumps(row['answer'], ensure_ascii=False, separators=(',', ':'))
    if row.get('contract') == 'common':
        from Server.healthmon.gateway import Speech
        from Server.local_probe.gpu_gateway import projected_messages, validate_contract
        payload = {'text': row['user_text'], 'context': row['context']}
        validate_contract(Speech.model_validate_json(target), payload)
        return projected_messages(payload, full_personality_facts=True)[0], target
    from src.agent import validate
    validate(target, row['context'], row['user_text'])
    return messages(row['context'], row['user_text']), target


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_rows(tokenizer, directory, max_length):

    output = {}
    fingerprints = set()
    groups = set()
    for split in ('train', 'validation'):
        rows = [json.loads(line) for line in (directory / (split + '.jsonl')).read_text(encoding='utf-8').splitlines() if line.strip()]
        encoded = []
        split_fingerprints, split_groups = set(), set()
        for row in rows:
            prompt, target = training_prompt(row)
            key = hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            group = row.get('scenario_group', row['sample_id'])
            if key in fingerprints or group in groups:
                raise ValueError('Train/validation overlap: ' + row['sample_id'])
            if key in split_fingerprints:
                raise ValueError('Duplicate prompt: ' + row['sample_id'])
            split_fingerprints.add(key)
            split_groups.add(group)
            tokens = encode_chatml(tokenizer, prompt, target, max_length)
            encoded.append((row['sample_id'], tokens))
        if not encoded:
            raise ValueError('Empty ' + split)
        output[split] = encoded
        fingerprints.update(split_fingerprints)
        groups.update(split_groups)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=ROOT / 'models/qwen3.5-4b')
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--max-length', type=int, default=2048)
    parser.add_argument('--lr', type=float, default=5e-5)
    parser.add_argument('--rank', type=int, default=8)
    parser.add_argument('--grad-accum', type=int, default=8)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--init-adapter', type=Path, help='Optional same-4B adapter; never a 9B adapter')
    parser.add_argument('--final-only-validation', action='store_true',
                        help='Train all requested epochs, then evaluate only the final checkpoint')
    parser.add_argument('--skip-validation', action='store_true',
                        help='Explicit user-requested training only; select final epoch without loss evaluation')
    args = parser.parse_args()
    if not 1 <= args.epochs <= 5 or args.grad_accum < 1 or args.rank < 1 or args.lr <= 0:
        raise ValueError('Invalid training parameters')
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    # Keep the established training math independent of optional serving kernels.
    # Serving can use FLA; adapters retain the same parameter names and shapes.
    from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen_kernels
    qwen_kernels.chunk_gated_delta_rule = None
    qwen_kernels.fused_recurrent_gated_delta_rule = None
    qwen_kernels.FusedRMSNormGated = None
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
    from filelock import FileLock
    torch.set_num_threads(8)
    torch.manual_seed(42)
    random.seed(42)
    source = json.loads((args.model / 'healthmon-source.json').read_text(encoding='utf-8'))
    if source['model_id'] != 'Qwen/Qwen3.5-4B':
        raise ValueError('This run requires the official 4B base')
    if args.init_adapter:
        verify_adapter_base(args.model, args.init_adapter)
    tok = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    data = prepare_rows(tok, args.data, args.max_length)
    lengths = {split: {'count': len(rows), 'max_tokens': max(len(t['input_ids']) for _, t in rows)} for split, rows in data.items()}
    print(json.dumps({'event': 'prepared', 'splits': lengths}), flush=True)
    if args.prepare_only:
        return
    if args.smoke:
        data['train'] = sorted(data['train'], key=lambda r: len(r[1]['input_ids']), reverse=True)[:2]
        data['validation'] = data['validation'][:2]
    args.run.mkdir(parents=True, exist_ok=False)
    config = {**vars(args), 'model': str(args.model.resolve()), 'data': str(args.data.resolve()), 'run': str(args.run.resolve()),
              'base': source, 'quantization': 'nf4', 'fresh_lora': args.init_adapter is None,
              'init_adapter': str(args.init_adapter.resolve()) if args.init_adapter else None,
              'prompt_sha256': digest(ROOT / 'src/prompts.py'),
              'common_prompt_sha256': digest(ROOT.parents[1] / 'Server/local_probe/gpu_gateway.py'),
              'data_sha256': {s: digest(args.data / (s + '.jsonl')) for s in data}, 'splits': lengths,
              'selection': 'final_epoch_unvalidated' if args.skip_validation else 'final_epoch' if args.final_only_validation else 'validation_loss_only', 'production_quality_approved': False}
    (args.run / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.run / 'pid').write_text(str(os.getpid()))
    def emit(event, **values):
        line = json.dumps(dict(event=event, time=time.time(), **values))
        with (args.run / 'metrics.jsonl').open('a', encoding='utf-8') as f:
            f.write(line + '\n')
        print(line, flush=True)
    (ROOT / 'runtime').mkdir(exist_ok=True)
    with FileLock(str(ROOT / 'runtime/gpu.lock'), timeout=0):
        try:
            emit('loading')
            model = Qwen3_5ForConditionalGeneration.from_pretrained(args.model, **loading_kwargs('nf4'))
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                gradient_checkpointing_kwargs={'use_reentrant': False})
            # Quantized language Linear4bit layers only; leave the vision encoder frozen.
            targets = [n for n, m in model.named_modules() if n.startswith('model.language_model.layers.')
                       and isinstance(m, torch.nn.Linear)]
            if not targets:
                raise ValueError('No language LoRA targets')
            if args.init_adapter:
                model = PeftModel.from_pretrained(model, args.init_adapter, is_trainable=True)
            else:
                model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=4*args.rank,
                    lora_dropout=.05, target_modules=targets, task_type='CAUSAL_LM'))
            model.config.use_cache = False
            model.config.text_config.use_cache = False
            parameters = [p for p in model.parameters() if p.requires_grad]
            if any('visual' in n for n, p in model.named_parameters() if p.requires_grad):
                raise ValueError('Vision parameters must remain frozen')
            optimizer = torch.optim.AdamW(parameters, lr=args.lr)
            def batch(tokens):
                return {k: torch.tensor([tokens[k]], device='cuda') for k in ('input_ids', 'labels', 'attention_mask')}
            def evaluate():
                model.eval()
                total, count = 0., 0
                with torch.no_grad():
                    for _, tokens in data['validation']:
                        loss = model(**batch(tokens), use_cache=False).loss
                        n = tokens['target_tokens']
                        total += float(loss) * n
                        count += n
                        del loss
                        torch.cuda.empty_cache()
                model.train()
                return total / count
            emit('loaded', trainable=sum(p.numel() for p in parameters), allocated_gib=torch.cuda.memory_allocated()/2**30)
            baseline = None if args.final_only_validation or args.skip_validation else evaluate()
            if baseline is not None:
                emit('baseline_validation', loss=baseline)
            choices = []
            steps = 0
            best = float('inf')
            for epoch in range(1 if args.smoke else args.epochs):
                model.train()
                optimizer.zero_grad(set_to_none=True)
                order = list(range(len(data['train'])))
                random.Random(42+epoch).shuffle(order)
                for i, idx in enumerate(order):
                    ident, tokens = data['train'][idx]
                    window = min(args.grad_accum, len(order)-(i//args.grad_accum)*args.grad_accum)
                    loss = model(**batch(tokens), use_cache=False).loss
                    if not torch.isfinite(loss):
                        raise ValueError('Nonfinite loss')
                    value = float(loss.detach())
                    (loss/window).backward()
                    del loss
                    if (i+1)%args.grad_accum == 0 or i+1 == len(order):
                        norm = torch.nn.utils.clip_grad_norm_(parameters, 1., error_if_nonfinite=True)
                        optimizer.step()
                        optimizer.zero_grad(set_to_none=True)
                        steps += 1
                        emit('optimizer_step', step=steps, gradient_norm=float(norm))
                    emit('sample', epoch=epoch+1, sample=i+1, sample_id=ident, loss=value,
                         peak_gib=torch.cuda.max_memory_allocated()/2**30,
                         reserved_gib=torch.cuda.memory_reserved()/2**30)
                    # Variable sequence lengths otherwise fragment Windows WDDM VRAM.
                    torch.cuda.empty_cache()
                checkpoint = args.run / f'checkpoint-epoch-{epoch+1}'
                model.save_pretrained(checkpoint)
                tok.save_pretrained(checkpoint)
                final_epoch = epoch + 1 == (1 if args.smoke else args.epochs)
                stop_requested = (args.run / 'stop.request').exists()
                if args.skip_validation:
                    emit('checkpoint_saved', epoch=epoch+1, path=str(checkpoint.resolve()), validation_skipped=True)
                    if final_epoch or stop_requested:
                        choices.append({'path':str(checkpoint.resolve()),'validation_loss':None})
                        break
                    continue
                if args.final_only_validation and not final_epoch and not stop_requested:
                    emit('checkpoint_saved', epoch=epoch+1, path=str(checkpoint.resolve()), validation_deferred=True)
                    continue
                score = evaluate()
                choice = {'path': str(checkpoint.resolve()), 'validation_loss': score}
                choices.append(choice)
                emit('validation', epoch=epoch+1, **choice)
                if score >= best or stop_requested:
                    break
                best = score
            selected = choices[-1] if args.skip_validation else min(choices, key=lambda c: c['validation_loss'])
            del optimizer, parameters
            reloaded = None
            if not args.skip_validation:
                base = model.unload()
                del model
                torch.cuda.empty_cache()
                model = PeftModel.from_pretrained(base, selected['path'])
                reloaded = evaluate()
                if abs(reloaded-selected['validation_loss']) > .01:
                    raise ValueError('Reload validation differs')
            selection = {'selected': selected, 'candidates': choices, 'baseline_validation_loss': baseline,
                         'reload_validation_loss': reloaded, 'trained': True,
                         'validation_skipped_by_user': args.skip_validation,
                         'nine_b_parity_verified': False, 'production_quality_approved': False}
            (args.run / 'selection.json').write_text(json.dumps(selection, indent=2), encoding='utf-8')
            emit('complete', steps=steps, **selection)
        except Exception as exc:
            emit('failed', error=repr(exc))
            raise


if __name__ == '__main__':
    main()
