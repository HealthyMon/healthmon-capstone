"""Reject cached/base-only/incorrect-parent results before publishing an evolution."""
from .assets import ADAPTER_SHA256, CONFIG, MODEL_ID, REVISION, SOURCE_COMMIT, read, sha256


def validate_image(metadata, image, prompt, parent):
    expected = read(CONFIG / 'model.json')
    if not (
        metadata.get('status') == 'PASS' and metadata.get('local_inference') is True
        and metadata.get('model_id') == MODEL_ID and metadata.get('model_revision') == REVISION
        and metadata.get('backend', {}).get('commit') == SOURCE_COMMIT
        and metadata.get('adapter', {}).get('sha256') == ADAPTER_SHA256
        and metadata.get('lora_layers_applied') == expected['linear_layer_pairs']
        and metadata.get('inference') == expected['inference']
        and metadata.get('mode') == 'native_image_edit'
        and metadata.get('output', {}).get('sha256') == sha256(image)
        and metadata.get('prompt_sha256') == sha256(prompt)
        and metadata.get('parent_sha256') == sha256(parent)
    ):
        raise ValueError('New 2511 image/adapter/parent provenance did not pass')
    return True
