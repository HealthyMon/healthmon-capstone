"""Export versioned common API and future GPU gateway schemas without loading models."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Server.healthmon.app import create_app
from Server.healthmon.config import Settings
from Server.healthmon.gateway import Classification, EmbeddingResult, Envelope, EvolutionResult, FoodResult, Speech


def export():
    folder = ROOT / 'Docs/api'
    folder.mkdir(exist_ok=True)
    app = create_app(Settings(database_url='postgresql://example.invalid/unused', worker_enabled=False))
    (folder / 'common.openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    schemas = {}
    for model in (Classification, EmbeddingResult, Envelope, EvolutionResult, FoodResult, Speech):
        schema = model.model_json_schema(ref_template='#/components/schemas/{model}')
        schemas.update(schema.pop('$defs', {}))
        schemas[model.__name__] = schema
    common = {'contract_version': {'const': 'healthmon.ai.v1'}, 'request_id': {'type': 'string', 'minLength': 1}, 'pet_id': {'type': 'string'}}
    inputs = {
        'chat': {'type': 'object', 'required': ['text', 'context'], 'properties': {'text': {'type': 'string'}, 'context': {'type': 'object'}}},
        'food': {'type': 'object', 'required': ['image_base64', 'content_type'], 'properties': {'image_base64': {'type': 'string', 'contentEncoding': 'base64'}, 'content_type': {'enum': ['image/jpeg', 'image/png']}}},
        'embedding': {'type': 'object', 'required': ['text'], 'properties': {'text': {'type': 'string'}}},
        'evolutions': {'type': 'object', 'required': ['stage', 'state', 'profile', 'rule_version', 'adapter_version'], 'properties': {'stage': {'type': 'integer', 'minimum': 1, 'maximum': 3}, 'state': {'type': 'object'}, 'profile': {'type': 'object'}, 'rule_version': {'const': 'healthmon.v2.2'}, 'adapter_version': {'const': 'healthmon.evolution.v2.2'}, 'source_contract': {'type': 'string'}, 'legacy_compatibility': {'type': 'object'}}},
    }
    inputs['evolutions']['properties']['parent_asset'] = {
        'type': 'object', 'additionalProperties': False,
        'description': 'Optional authenticated common-server starter binding for stage0 to1. Never supplied by a game client. PNG bytes are bounded to1MiB and verified against their immutable hash.',
        'required': ['stage', 'revision', 'species', 'species_contract', 'image_base64', 'image_sha256', 'model_sha256', 'source_kind'],
        'properties': {
            'stage': {'const': 0}, 'revision': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,100}$'},
            'species': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,100}$'},
            'species_contract': {'type': ['object', 'null']},
            'image_base64': {'type': 'string', 'contentEncoding': 'base64', 'maxLength': 1398104},
            'image_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
            'model_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
            'source_kind': {'const': 'common_server_verified_starter'},
        },
    }
    paths = {}
    for name, result in [('chat', 'Speech'), ('food', 'FoodResult'), ('embedding', 'EmbeddingResult'), ('evolutions', 'EvolutionResult')]:
        request_schema = {'type': 'object', 'required': ['contract_version', 'request_id', 'pet_id', 'input'], 'additionalProperties': False, 'properties': {**common, 'input': inputs[name]}}
        response_schema = {'type': 'object', 'required': ['contract_version', 'request_id', 'provenance', 'result'], 'additionalProperties': False,
                           'properties': {'contract_version': {'const': 'healthmon.ai.v1'}, 'request_id': {'type': 'string'}, 'provenance': {'enum': ['real', 'synthetic']}, 'result': {'$ref': '#/components/schemas/' + result}}}
        operation = {'operationId': name, 'security': [{'serverBearer': []}], 'requestBody': {'required': True, 'content': {'application/json': {'schema': request_schema}}},
                     'responses': {'200': {'description': 'Validated result with the same request_id', 'content': {'application/json': {'schema': response_schema}}}, '401': {'description': 'Server authentication required'}, '409': {'description': 'ID reused with different input'}}}
        path = '/v1/' + name + ('/{job_id}' if name == 'evolutions' else '')
        paths[path] = {'put' if name == 'evolutions' else 'post': operation}
        if name == 'evolutions':
            operation['parameters'] = [{'in': 'path', 'name': 'job_id', 'required': True, 'schema': {'type': 'string'}}]
            paths[path]['get'] = {key: value for key, value in operation.items() if key != 'requestBody'}
            paths[path]['get']['operationId'] = 'evolutions_status'
    spec = {'openapi': '3.1.0', 'info': {'title': 'HEALTHMON remote AI server implementation contract', 'version': 'healthmon.ai.v1',
            'description': 'New gateway contract, not a claim that legacy GPU services already implement these endpoints. Evolution PUT must atomically deduplicate the same job_id and frozen input.'},
            'paths': paths, 'components': {'securitySchemes': {'serverBearer': {'type': 'http', 'scheme': 'bearer'}}, 'schemas': schemas}}
    (folder / 'ai-gateway.openapi.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Exported common API and remote AI implementation schemas.')


if __name__ == '__main__':
    export()
