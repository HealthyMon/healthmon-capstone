"""Keep valid generated speech when a display-only enum is unsupported."""
import json

from pydantic import ValidationError

from Server.healthmon.gateway import Speech


def parse_generated_speech(raw):
    try:
        return Speech.model_validate_json(raw), []
    except ValidationError as error:
        failures = error.errors(include_url=False)
        defaults = {'emotion': 'neutral', 'animation': 'idle'}
        # Do not repair speech, classifications, memory references, missing
        # fields, invalid JSON or invalid value types. Those remain failures.
        if not all(len(item['loc']) == 1 and item['loc'][0] in defaults
                   and item['type'] == 'literal_error'
                   and isinstance(item.get('input'), str)
                   and 0 < len(item['input']) <= 64 for item in failures):
            raise
        data = json.loads(raw)
        changed = sorted({item['loc'][0] for item in failures})
        for field in changed:
            data[field] = defaults[field]
        return Speech.model_validate(data), changed
