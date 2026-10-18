"""A single job per process. No model or CUDA context survives the response."""
import contextlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def conversation():
    with contextlib.redirect_stdout(sys.stderr):
        from src.agent import respond
        from src.model import QwenBackend
        backend = QwenBackend()
        started = time.monotonic()
        backend.load()
        print(json.dumps({'model': 'qwen', 'session_load_seconds': time.monotonic()-started,
                          'timings': backend.load_timings}), file=sys.stderr, flush=True)
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        with contextlib.redirect_stdout(sys.stderr):
            response, metrics = respond(backend, job['context'], job['text'])
            metrics['timings'] = {'model_load_seconds': 0., 'generation_seconds': metrics['latency_seconds'],
                                  'conversation_reused': True}
            result = {'id': job['id'], 'response': response.model_dump(), 'metrics': metrics}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    if '--session' in sys.argv:
        conversation()
        return
    started = time.monotonic()
    job = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        if sys.argv[1] == 'qwen':
            from src.agent import respond
            from src.model import QwenBackend
            imported = time.monotonic()
            backend = QwenBackend()
            backend.load()  # Resource/load failures become API failures, not character fallback speech.
            loaded = time.monotonic()
            response, metrics = respond(backend, job['context'], job['text'])
            metrics['timings'] = {
                'worker_import_seconds': imported - started,
                'model_load_seconds': loaded - imported,
                'generation_seconds': time.monotonic() - loaded,
                **backend.load_timings,
            }
            result = {'response': response.model_dump(), 'metrics': metrics}
        else:
            import torch
            torch.set_num_threads(4)
            from src.embedding import Embedder
            try:
                result = {'vector': Embedder().encode(job['text'])}
            except ValueError:
                result = {'error': 'Memory exceeds the embedding input budget'}
        print(json.dumps({'model': sys.argv[1], 'worker_seconds': time.monotonic() - started,
                          'timings': result.get('metrics', {}).get('timings', {})}),
              file=sys.stderr, flush=True)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
