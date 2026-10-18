"""Install the team's legacy CPU stack separately from the Qwen CUDA environment."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path(r'E:\qwen-llm'))
    args = parser.parse_args()
    uv = shutil.which('uv')
    if not uv:
        parser.error('Install uv or put an existing uv executable on PATH.')
    vision = Path(__file__).resolve().parents[2] / 'Vision'
    environment = vision / '.venv'
    python = environment / 'Scripts/python.exe'
    cache = args.runtime_root / 'runtime/uv-cache'
    env = {**os.environ, 'UV_CACHE_DIR': str(cache),
           'UV_PYTHON_INSTALL_DIR': str(args.runtime_root / 'runtime/vision-python')}
    if not python.is_file():
        subprocess.run([uv, 'venv', '--python', '3.10', '--seed', str(environment)], env=env, check=True)
    commands = [
        ['--index-strategy', 'unsafe-best-match', 'numpy==1.23.5', 'pillow==9.5.0',
         'opencv-python==4.8.1.78', 'yapf==0.40.1', 'setuptools==69.5.1', 'wheel',
         'torch==1.13.1+cpu', 'torchvision==0.14.1+cpu', '--extra-index-url', 'https://download.pytorch.org/whl/cpu'],
        ['--find-links', 'https://download.openmmlab.com/mmcv/dist/cpu/torch1.13.0/index.html', 'mmcv-full==1.7.0'],
        ['--no-build-isolation', 'numpy==1.23.5', 'mmdet==2.26.0'],
    ]
    for command in commands:
        subprocess.run([uv, 'pip', 'install', '--python', str(python), *command], env=env, check=True)
    subprocess.run([str(python), '-c', 'import torch,torchvision,mmdet; from mmcv.ops import nms; assert not torch.cuda.is_available()'], check=True)
    print('Vision CPU environment ready. The existing LLM CUDA environment was not modified.')


if __name__ == '__main__':
    main()
