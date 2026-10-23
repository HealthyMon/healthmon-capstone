"""Avoid Windows mmap commit pressure while preserving checkpoint tensors."""
import os
import sys


def load_pretrained(model_class, *args, **kwargs):
    if sys.platform != 'win32':
        return model_class.from_pretrained(*args, **kwargs)

    from transformers import modeling_utils
    original_open = modeling_utils.safe_open
    original_async = os.environ.get('HF_DEACTIVATE_ASYNC_LOAD')

    def read_checkpoint(*open_args, **open_kwargs):
        # safetensors 0.8 supports bounded file reads without Windows' mmap
        # copy-on-write commit reservation for every open checkpoint shard.
        open_kwargs['backend'] = 'pread'
        return original_open(*open_args, **open_kwargs)

    # This gateway serializes all model loading under LocalModels.lock.
    # Scope the compatibility adapter to this load; do not patch installed libs.
    modeling_utils.safe_open = read_checkpoint
    os.environ['HF_DEACTIVATE_ASYNC_LOAD'] = '1'
    try:
        return model_class.from_pretrained(*args, **kwargs)
    finally:
        modeling_utils.safe_open = original_open
        if original_async is None:
            os.environ.pop('HF_DEACTIVATE_ASYNC_LOAD', None)
        else:
            os.environ['HF_DEACTIVATE_ASYNC_LOAD'] = original_async
