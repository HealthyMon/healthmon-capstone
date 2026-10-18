"""Durable local evolution jobs; a published version is immutable."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import threading
import time

LEVELS = (0, 15, 30, 50)
AXES = ('UpperBody', 'LowerBody', 'Nutrition', 'EnergyBalance', 'Activity', 'Affinity', 'Initiative', 'Mood')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('Use a 1-64 character identifier: letters, digits, underscore or hyphen')
    return value


def checked_stats(stats):
    import math
    if set(stats) != set(AXES):
        raise ValueError('All eight growth axes must be supplied; dialogue traits are not body scores')
    result = {}
    for axis in AXES:
        value = stats[axis]
        low, high = (-1, 1) if axis == 'EnergyBalance' else (0, 100)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{axis} must be a finite number in [{low}, {high}]')
        result[axis] = float(value)
    return result


def inspect_glb(path):
    """Reject truncated files, external resources, missing textures or skin data."""
    with Path(path).open('rb') as stream:
        magic, version, length = struct.unpack('<4sII', stream.read(12))
        if magic != b'glTF' or version != 2 or length != Path(path).stat().st_size:
            raise ValueError('Invalid/truncated GLB')
        size, kind = struct.unpack('<II', stream.read(8))
        if kind != 0x4E4F534A or size > length - 20:
            raise ValueError('Invalid GLB JSON chunk')
        doc = json.loads(stream.read(size))
    if not doc.get('skins') or not doc.get('images'):
        raise ValueError('A textured, rigged GLB is required')
    if any('uri' in item for key in ('buffers', 'images') for item in doc.get(key, [])):
        raise ValueError('GLB must be self-contained')
    primitives = [p for mesh in doc.get('meshes', []) for p in mesh['primitives']]
    if not primitives or any(not {'JOINTS_0', 'WEIGHTS_0'} <= set(p['attributes']) for p in primitives):
        raise ValueError('Missing vertex skin attributes')
    return dict(bones=sum(len(s['joints']) for s in doc['skins']),
                vertices=sum(doc['accessors'][p['attributes']['POSITION']]['count'] for p in primitives),
                triangles=sum(doc['accessors'][p['indices']]['count'] // 3 for p in primitives),
                animation_clips=len(doc.get('animations', [])))


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def pet_dir(self, pet):
        return self.root / 'pets' / identifier(pet)

    def current(self, pet):
        path = self.pet_dir(pet) / 'current.json'
        if not path.exists():
            raise FileNotFoundError('Starter is not provisioned for this pet')
        return read(path)

    def job(self, job_id):
        return read(self.root / 'jobs' / (identifier(job_id) + '.json'))

    def update(self, job_id, **fields):
        with self.lock:
            value = self.job(job_id)
            value.update(fields, updated_at=time.time())
            atomic_json(self.root / 'jobs' / (job_id + '.json'), value)
            return value

    def jobs(self):
        return sorted((read(p) for p in (self.root / 'jobs').glob('*.json')), key=lambda j: j['created_at'])

    def submit(self, pet, request):
        pet = identifier(pet)
        request_id = identifier(request['request_id'])
        stats = checked_stats(request['stats'])
        level = request['level']
        seed = request.get('seed', 42)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
            raise ValueError('Invalid generation seed')
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError('level must be an integer from 0 to 100')
        if not isinstance(request.get('score_source'), str) or not request['score_source'].strip():
            raise ValueError('score_source is required (use synthetic_demo for example scores)')
        body = dict(pet_id=pet, request_id=request_id, level=level, stats=stats,
                    score_source=request['score_source'])
        if seed != 42: body['seed'] = seed  # Preserve keys of existing seed-42 requests.
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        job_id = hashlib.sha256((pet + ':' + request_id).encode()).hexdigest()[:32]
        with self.lock:
            path = self.root / 'jobs' / (job_id + '.json')
            if path.exists():
                old = read(path)
                if old['request_key'] != key:
                    raise ValueError('Request ID already belongs to different input')
                return old
            current = self.current(pet)
            stage = current['stage'] + 1
            if stage > 3 or level < LEVELS[stage]:
                raise ValueError('The next sequential evolution milestone has not been reached')
            for active in self.jobs():
                if active['pet_id'] == pet and active['status'] not in ('READY', 'FAILED'):
                    raise ValueError('This pet already has an unfinished evolution job')
            job = dict(**body, job_id=job_id, request_key=key, status='QUEUED', phase='queued',
                       source_revision=current['revision'], source_stage=current['stage'],
                       target_stage=stage, created_at=time.time(), updated_at=time.time(), error=None)
            job.update(seed=seed, species=current.get('species', 'lucan'))
            if current.get('species_contract') is not None:
                job.update(species_contract=current['species_contract'], species_contract_sha256=current['species_contract_sha256'])
            atomic_json(path, job)
            return job

    def publish(self, pet, revision, stage, image, model, *, source_revision=None, provenance=None, species=None, species_contract=None):
        pet, revision = identifier(pet), identifier(revision)
        mesh = inspect_glb(model)
        with self.lock:
            base = self.pet_dir(pet)
            if source_revision is not None and self.current(pet)['revision'] != source_revision:
                raise ValueError('Stale result cannot replace a newer model')
            parent = self.current(pet) if (base / 'current.json').exists() else None
            parent_species = parent.get('species', 'lucan') if parent else None
            species = identifier(species or parent_species or 'lucan')
            inherited = parent.get('species_contract') if parent else None
            if parent and (species != parent_species or (species_contract is not None and species_contract != inherited)):
                raise ValueError('An existing pet lineage cannot change species identity')
            species_contract = species_contract or inherited
            if species_contract is not None:
                import sys
                source_path = str(Path(__file__).resolve().parents[2] / 'src')
                if source_path not in sys.path: sys.path.insert(0, source_path)
                from healthmon.species_contract import validate_contract, contract_hash
                species_contract = validate_contract(species_contract, species)
                species_digest = contract_hash(species_contract)
            elif species != 'lucan':
                raise ValueError('A new species requires an explicit identity contract')
            version = base / 'versions' / revision
            previous_manifest = version / 'manifest.json'
            if previous_manifest.exists():
                existing = read(previous_manifest)
                if existing['species'] != species or existing['stage'] != stage or existing.get('species_contract') != species_contract:
                    raise ValueError('Published identity metadata is immutable')
            version.mkdir(parents=True, exist_ok=True)
            for name, source in (('image.png', image), ('model.glb', model)):
                target = version / name
                if target.exists():
                    if sha(target) != sha(source):
                        raise ValueError('Published revisions cannot be overwritten')
                else:
                    temporary = target.with_suffix('.part')
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, target)
            manifest = dict(pet_id=pet, species=species, stage=stage, revision=revision,
                image_sha256=sha(version / 'image.png'), model_sha256=sha(version / 'model.glb'),
                image_url=f'/v1/pets/{pet}/versions/{revision}/image.png',
                model_url=f'/v1/pets/{pet}/versions/{revision}/model.glb', mesh=mesh,
                published_at=time.time(), provenance=provenance or {},
                visual_quality='REQUIRES_REVIEW', animation_quality='REQUIRES_REVIEW')
            if species_contract is not None:
                manifest.update(species_contract=species_contract, species_contract_sha256=species_digest)
            atomic_json(version / 'manifest.json', manifest)
            # Only this last small atomic write changes what Unity sees.
            atomic_json(base / 'current.json', manifest)
            return manifest
