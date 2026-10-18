"""Keep legacy CPU Vision dependencies out of the Qwen CUDA process."""
import atexit
import json
import os
import queue
import subprocess
import threading
import uuid
from pathlib import Path
from .model_runtime import runtime as model_runtime, stop_worker

ROOT = Path(__file__).resolve().parents[1]
VISION = ROOT.parent / 'Vision'


class VisionService:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self.responses = None
        self.log = None

    def status(self):
        python = Path(os.getenv('VISION_PYTHON', str(VISION / '.venv/Scripts/python.exe')))
        return {'configured': python.is_file(), 'running': self.process is not None and self.process.poll() is None,
                'lifecycle': 'on_demand', 'backend': 'team-fasterrcnn-swin-resnet18-cpu', 'interface': 'healthmon.food.v1'}

    def _start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        python = Path(os.getenv('VISION_PYTHON', str(VISION / '.venv/Scripts/python.exe')))
        if not python.is_file():
            raise RuntimeError('Vision environment missing; run scripts/setup_vision.py first.')
        (ROOT / 'runs').mkdir(exist_ok=True)
        self.log = (ROOT / 'runs/vision-worker.log').open('a', encoding='utf-8')
        self.process = subprocess.Popen([str(python), '-u', str(VISION / 'service_worker.py')],
                                        cwd=VISION, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, encoding='utf-8',
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.responses = queue.Queue()
        def read(process, responses):
            try:
                for line in process.stdout:
                    responses.put(json.loads(line))
            except (ValueError, OSError):
                pass
            finally:
                responses.put(None)
        threading.Thread(target=read, args=(self.process, self.responses), daemon=True).start()

    def analyze(self, image, timeout=240):
        with model_runtime.reserve('vision'):
            model_runtime.before_vision()
            return self._analyze(image, timeout)

    def _analyze(self, image, timeout):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Vision is busy; retry shortly.')
        try:
            self._start()
            ident = uuid.uuid4().hex
            self.process.stdin.write(json.dumps({'id': ident, 'image': str(image)}) + '\n')
            self.process.stdin.flush()
            response = self.responses.get(timeout=timeout)
            if response is None or response.get('id') != ident:
                self.close()
                raise RuntimeError('Vision worker stopped; inspect runs/vision-worker.log.')
            if 'error' in response:
                if response.get('invalid_image'):
                    raise ValueError('Vision could not decode or analyze this image.')
                raise RuntimeError('Vision model failed; inspect runs/vision-worker.log.')
            # The one-shot worker exits after its result, including its venv child.
            self.process.wait(timeout=10)
            return response['result']
        except (queue.Empty, BrokenPipeError, OSError, subprocess.TimeoutExpired) as error:
            self.close()
            raise RuntimeError('Vision worker unavailable or timed out.') from error
        finally:
            self.close()
            self.lock.release()

    def close(self):
        if self.process is not None:
            stop_worker(self.process)
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None


vision_service = VisionService()
atexit.register(vision_service.close)
