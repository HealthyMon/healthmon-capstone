import pytest
from filelock import FileLock
from src.db import ROOT
from src.model import QwenBackend

def test_second_model_does_not_load_when_gpu_reserved():
    # No CUDA allocation in this test; the lock must fail before model construction.
    with FileLock(str(ROOT/'runtime/gpu.lock'),timeout=0):
        with pytest.raises(RuntimeError,match='Another Healthmon process'):
            QwenBackend().load()
