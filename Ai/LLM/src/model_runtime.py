"""Keep Qwen only during an explicit conversation lease; other jobs are one-shot."""
import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


class ModelBusy(RuntimeError):
    pass


class ConversationClosed(RuntimeError):
    pass


class ModelRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.active = None
        self.residency = lambda: {}
        self.before_vision = lambda: None

    @contextmanager
    def reserve(self, name):
        if not self.lock.acquire(blocking=False):
            raise ModelBusy('Another model is processing a request; retry shortly.')
        previous = self.active
        self.active = name
        try:
            yield
        finally:
            self.active = previous
            self.lock.release()

    def status(self):
        return {'policy': 'conversation_session', 'active_model': self.active,
                'idle_models_resident': False, 'concurrent_model_jobs': 1, **self.residency()}


runtime = ModelRuntime()


def stop_worker(process):
    """Terminate only this Popen's descendants, including Windows venv launchers."""
    if process.poll() is not None:
        return
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    process.kill()
    process.wait(timeout=10)


class ModelWorker:
    def __init__(self, kind):
        self.kind = kind
        self.process = None

    def run(self, payload, timeout=150):
        with runtime.reserve(self.kind):
            (ROOT / 'runs').mkdir(exist_ok=True)
            with (ROOT / 'runs' / (self.kind + '-worker.log')).open('a', encoding='utf-8') as log:
                self.process = subprocess.Popen(
                    [sys.executable, '-u', str(ROOT / 'scripts/model_worker.py'), self.kind],
                    cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                    text=True, encoding='utf-8',
                    env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    output, _ = self.process.communicate(json.dumps(payload, ensure_ascii=False), timeout=timeout)
                    if self.process.returncode:
                        raise RuntimeError(self.kind + ' model failed; inspect its worker log.')
                    return json.loads(output)
                except subprocess.TimeoutExpired as error:
                    raise TimeoutError(self.kind + ' model exceeded the request deadline.') from error
                finally:
                    stop_worker(self.process)
                    for stream in (self.process.stdin, self.process.stdout):
                        if stream and not stream.closed:
                            stream.close()
                    self.process = None


class ConversationWorker(ModelWorker):
    """Line-delimited RPC, with one CUDA process for the current dialogue tab."""
    def __init__(self):
        super().__init__('qwen')
        self.responses = None
        self.log = None
        self.ready = False
        self.can_load = lambda: True

    def start(self, timeout=150):
        if self.ready and self.process is not None and self.process.poll() is None:
            return
        if not self.can_load():
            raise ConversationClosed('Conversation closed before startup')
        self.close()
        (ROOT / 'runs').mkdir(exist_ok=True)
        self.log = (ROOT / 'runs/qwen-worker.log').open('a', encoding='utf-8')
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'scripts/model_worker.py'), 'qwen', '--session'],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding='utf-8',
            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
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
        try:
            if self._receive(timeout, cancelled=lambda: not self.can_load()) != {'ready': True}:
                raise RuntimeError('Unexpected Qwen startup response')
            self.ready = True
        except Exception:
            self.close()
            raise

    def _receive(self, timeout, cancelled=lambda: False):
        deadline = time.monotonic() + timeout
        while True:
            if cancelled():
                raise ConversationClosed('Conversation closed during startup')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Qwen exceeded the request deadline')
            try:
                result = self.responses.get(timeout=min(.25, remaining))
                break
            except queue.Empty:
                continue
        if result is None:
            raise RuntimeError('Qwen worker stopped; inspect its worker log')
        return result

    def run(self, payload, timeout=150):
        try:
            self.start(timeout)
            ident = uuid.uuid4().hex
            self.process.stdin.write(json.dumps({**payload, 'id': ident}, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
            result = self._receive(timeout)
            if result.get('id') != ident or 'error' in result:
                raise RuntimeError('Qwen session failed; inspect its worker log')
            return result
        except (Exception, KeyboardInterrupt):
            self.close()
            raise

    def close(self):
        self.ready = False
        if self.process is not None:
            stop_worker(self.process)
            for stream in (self.process.stdin, self.process.stdout):
                if stream and not stream.closed:
                    stream.close()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None


class OnDemandQwen:
    def __init__(self):
        self.worker = ModelWorker('qwen')
        self.conversation = ConversationWorker()
        self.state_lock = threading.Lock()
        self.lease = None
        self.expires = 0
        self.ttl = 90
        self.closed = deque(maxlen=64)
        self.monitor = None
        self.shutdown = threading.Event()
        self.conversation.can_load = self._lease_open
        runtime.residency = self.status
        runtime.before_vision = self.release_for_vision
        atexit.register(self.close)

    @property
    def name(self):
        return 'qwen3.5-9b-bf16' + ('-lora' if os.getenv('ADAPTER_PATH') else '')

    @property
    def model(self):
        process = self.conversation.process
        return process if process is not None and process.poll() is None else self.worker.process

    def status(self):
        with self.state_lock:
            active = self.lease is not None and time.monotonic() < self.expires
        return {'conversation_active': active, 'idle_models_resident': self.model is not None,
                'resident_model': 'qwen' if self.model is not None else None}

    def _lease_open(self):
        with self.state_lock:
            return self.lease is not None and time.monotonic() < self.expires

    def _session_status(self, key):
        with self.state_lock:
            active = self.lease == key and time.monotonic() < self.expires
        alive = self.conversation.process is not None and self.conversation.process.poll() is None
        return {'active': active, 'ready': active and self.conversation.ready and alive,
                'policy': 'conversation_session', 'heartbeat_timeout_seconds': self.ttl}

    def open_session(self, key):
        with runtime.reserve('qwen_load'):
            self._close_if_unleased()
            with self.state_lock:
                if key in self.closed:
                    return self._closed_status()
                if self.lease is not None and self.lease != key and time.monotonic() < self.expires:
                    raise ModelBusy('Another conversation is active; close it before switching')
                self.lease = key
                self.expires = time.monotonic() + self.ttl
                if self.monitor is None or not self.monitor.is_alive():
                    self.monitor = threading.Thread(target=self._watch_lease, daemon=True)
                    self.monitor.start()
            try:
                self.conversation.start()
                return self._session_status(key)
            except ConversationClosed:
                return self._closed_status()
            except Exception:
                self.close_session(key)
                raise
            finally:
                self._close_if_unleased()

    def heartbeat(self, key):
        with self.state_lock:
            if self.lease == key and time.monotonic() < self.expires:
                self.expires = time.monotonic() + self.ttl
        return self._session_status(key)

    def _closed_status(self):
        return {'active': False, 'ready': False, 'policy': 'conversation_session',
                'heartbeat_timeout_seconds': self.ttl}

    def close_session(self, key):
        with self.state_lock:
            self.closed.append(key)  # A delayed open must not resurrect a closed tab.
            if self.lease == key:
                self.lease = None
        self._close_if_unleased()
        return self._closed_status()

    def _close_if_unleased(self):
        if not runtime.lock.acquire(blocking=False):
            return  # A running load/generation releases the child in its finally block.
        try:
            with self.state_lock:
                if self.lease is not None and time.monotonic() >= self.expires:
                    self.closed.append(self.lease)
                    self.lease = None
                keep = self.lease is not None
            if not keep:
                self.conversation.close()
        finally:
            runtime.lock.release()

    def _watch_lease(self):
        while not self.shutdown.wait(5):
            self._close_if_unleased()

    def release_for_vision(self):
        # Called while Vision owns runtime.reserve; no Qwen job can overlap this.
        with self.state_lock:
            if self.lease is not None:
                self.closed.append(self.lease)
            self.lease = None
        self.conversation.close()

    def close(self):
        self.shutdown.set()
        with self.state_lock:
            self.lease = None
        self.conversation.close()

    def respond(self, context, text, owner=None, pet=None):
        from .contracts import ModelOutput
        started = time.monotonic()
        with runtime.reserve('qwen'):
            self._close_if_unleased()
            with self.state_lock:
                key = self.lease
            if key is not None and key[:2] != (owner, pet):
                raise ModelBusy('Another conversation is active; retry after it closes')
            try:
                worker = self.conversation if key is not None else self.worker
                result = worker.run({'context': context, 'text': text})
            finally:
                self._close_if_unleased()
        result['metrics'].setdefault('timings', {})['worker_roundtrip_seconds'] = time.monotonic() - started
        return ModelOutput.model_validate(result['response']), result['metrics']


class OnDemandEmbedder:
    def __init__(self):
        self.worker = ModelWorker('embedding')
        self.revision = json.loads((ROOT / 'config/bge-m3.json').read_text())['revision']

    def encode(self, text):
        result = self.worker.run({'text': text}, timeout=60)
        if 'error' in result:
            raise ValueError(result['error'])
        return result['vector']
