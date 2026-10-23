import os

import pytest

from Server.local_probe import checkpoint_loading


@pytest.mark.parametrize('fail', [False, True])
def test_windows_reader_preserves_tensor_values_and_restores_loader(tmp_path, monkeypatch, fail):
    torch = pytest.importorskip('torch')
    from safetensors.torch import save_file
    from transformers import modeling_utils

    monkeypatch.setattr(checkpoint_loading.sys, 'platform', 'win32')
    monkeypatch.setenv('HF_DEACTIVATE_ASYNC_LOAD', '0')
    weights = torch.arange(24, dtype=torch.bfloat16).reshape(6, 4)
    path = tmp_path / 'weights.safetensors'
    save_file({'weight': weights}, path)
    original = modeling_utils.safe_open

    class Loader:
        @staticmethod
        def from_pretrained(checkpoint, **kwargs):
            assert kwargs == {'local_files_only': True, 'dtype': torch.bfloat16}
            assert os.environ['HF_DEACTIVATE_ASYNC_LOAD'] == '1'
            with modeling_utils.safe_open(checkpoint, framework='pt', device='cpu') as reader:
                actual = reader.get_slice('weight')[...]
                assert torch.equal(actual, weights) and actual.dtype == weights.dtype
            if fail:
                raise ValueError('controlled model loading failure')
            return actual

    if fail:
        with pytest.raises(ValueError, match='controlled'):
            checkpoint_loading.load_pretrained(Loader, path, local_files_only=True, dtype=torch.bfloat16)
    else:
        actual = checkpoint_loading.load_pretrained(Loader, path, local_files_only=True, dtype=torch.bfloat16)
        assert torch.equal(actual, weights)
    assert modeling_utils.safe_open is original
    assert os.environ['HF_DEACTIVATE_ASYNC_LOAD'] == '0'
