"""One explicit CPU Vision job, without legacy app or lifecycle imports."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def run(source, assets, job):
    # Source is this checkout's reviewed module; only its asset ROOT changes.
    # Importing under a private name avoids its __main__ installer/UI path.
    os.environ.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        torch.set_num_threads(4)
        if torch.version.cuda is not None:
            raise RuntimeError('Existing CPU-only Vision runtime required')
        spec = importlib.util.spec_from_file_location('healthmon_existing_vision', source / 'main.py')
        vision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vision)
        vision.ROOT = assets
        sys.modules['main'] = vision
        worker_spec = importlib.util.spec_from_file_location('healthmon_existing_vision_worker', source / 'service_worker.py')
        worker = importlib.util.module_from_spec(worker_spec)
        worker_spec.loader.exec_module(worker)
        result = worker.analyze(Path(job['image']))
    return {'id': job['id'], 'result': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    job = json.loads(sys.stdin.readline())
    try:
        response = run(args.source.resolve(), args.assets.resolve(), job)
    except Exception as exc:
        response = {'id': job.get('id'), 'error': type(exc).__name__}
    print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
