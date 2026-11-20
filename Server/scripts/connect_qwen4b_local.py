"""Configure the existing local Docker API and Editor without printing credentials."""
import json
import secrets
from pathlib import Path
import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[2]
runtime = ROOT / '.runtime' / 'qwen4b-live'
runtime.mkdir(parents=True, exist_ok=True)
env_path = ROOT / '.env'
env = dotenv_values(env_path)
backup = runtime / 'before.env'
if not backup.exists():
    backup.write_bytes(env_path.read_bytes())
token = env.get('AI_SERVER_TOKEN') or secrets.token_urlsafe(48)
config = json.loads((ROOT / 'Ai/LLM/config/common-gateway.qwen4b.example.json').read_text())
config.update(server_token=token, embedding_path=str(ROOT / 'Ai/LLM/models/bge-m3'))
(runtime / 'gateway.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
url = 'http://127.0.0.1:' + env.get('API_PORT', '18092')
user_token = next(iter(json.loads(env['DEV_TOKENS'])))
with httpx.Client(trust_env=False, timeout=15) as client:
    response = client.get(url + '/pets', headers={'Authorization': 'Bearer ' + user_token})
    response.raise_for_status()
    pets = response.json()['pets']
if not pets:
    raise RuntimeError('Existing account has no pet; no existing state was changed')
(runtime / 'unity-session.json').write_text(json.dumps({'api_base_url': url, 'bearer_token': user_token}), encoding='utf-8')
(ROOT / '.runtime/unity-server.json').write_text(json.dumps({'base_url': url, 'session': '.runtime/qwen4b-live/unity-session.json', 'pet_id': pets[0]['pet_id']}), encoding='utf-8')
for key, value in {'AI_MODE': 'remote', 'AI_BASE_URL': 'http://host.docker.internal:18091', 'AI_SERVER_TOKEN': token, 'ALLOW_HTTP_AI': 'true', 'AI_TIMEOUT_SECONDS': '180'}.items():
    set_key(env_path, key, value)
print('Configured existing API, trained 4B adapter, BGE-M3, and private Unity Editor session.')
