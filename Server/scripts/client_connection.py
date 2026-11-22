"""Private local client handoff. No HTTP credential-discovery endpoint."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def write_connection(root, *, base_url, token, owner_id, pet_id, server_instance_id, environment):
    address = urlsplit(base_url)
    if (environment != 'test' or address.scheme not in ('http', 'https')
            or address.hostname not in ('127.0.0.1', 'localhost', '::1')
            or address.username or address.password or address.query or address.fragment):
        raise ValueError('Automatic client setup requires the local test server')
    if any(not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value
           for value in (token, owner_id, server_instance_id)):
        raise ValueError('Incomplete local client identity')
    payload = dict(schema_version=1, environment=environment, api_base_url=base_url.rstrip('/'),
                   bearer_token=token, owner_id=owner_id, pet_id=pet_id or '', server_instance_id=server_instance_id)
    directory = Path(root) / '.runtime'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'client-connection.json'
    temporary = target.with_suffix('.json.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        if os.name != 'nt': os.chmod(temporary, 0o600)
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    temporary.replace(target)
    return target
