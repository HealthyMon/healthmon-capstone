"""Prepare an isolated code/output tree; existing models/vendor are read-only mounts."""
import hashlib
import json
from pathlib import Path
import shutil

from .contracts import identifier
from .store import canonical,fingerprint

SOURCE=Path(__file__).resolve().parents[2]
CODE_FOLDERS=('configs','scripts','src','runtime','migration/tools')
EXCLUDED={'__pycache__','.pytest_cache','.git','runtime.local.json','trellis_runtime.json','qwen_runtime.json','rigging_runtime.json'}
EXECUTION_CACHES=('flex_gemm','torch_extensions','triton')


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): value.update(block)
    return value.hexdigest()


def code_manifest():
    result={}
    for directory in CODE_FOLDERS:
        for path in (SOURCE/directory).rglob('*'):
            if path.is_file() and not set(path.parts)&EXCLUDED and path.suffix in {'.py','.json','.sh','.yaml','.txt'}:
                result[path.relative_to(SOURCE).as_posix()]=sha(path)
    return result


def prepare_execution_caches(root,model_root):
    """Seed only mutable kernel caches; checkpoint and vendor mounts stay read-only."""
    root=Path(root).resolve();model_root=Path(model_root).resolve()
    record=root/'execution-cache-seed.json'
    if record.exists(): return
    copied={}
    for name in EXECUTION_CACHES:
        source=model_root/'trellis'/name
        target=root/'cache/trellis'/name
        target.mkdir(parents=True,exist_ok=True)
        for path in source.rglob('*'):
            if not path.is_file() or path.is_symlink() or path.name.endswith('.lock'): continue
            relative=path.relative_to(source)
            destination=target/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists(): raise ValueError('Untracked execution cache exists; use a fresh work root')
            shutil.copyfile(path,destination)
            copied[f'{name}/{relative.as_posix()}']=sha(destination)
    record.write_text(canonical({'source_root':str(model_root/'trellis'),'files':copied})+'\n',encoding='utf-8')


def prepare_runtime(root,model_root,vendor_root):
    root=Path(root).resolve();runtime=root/'runtime'
    model_root=Path(model_root).resolve();vendor_root=Path(vendor_root).resolve()
    if not model_root.is_dir() or not vendor_root.is_dir(): raise ValueError('Existing models and vendor directories are required')
    # Never write to either original tree, nor prepare a runtime over its own source.
    if runtime==SOURCE or runtime.is_relative_to(model_root) or runtime.is_relative_to(vendor_root):
        raise ValueError('Runtime must be an isolated new output/code directory')
    manifest=code_manifest()
    signature={'sources':manifest,'model_mount':str(model_root),'vendor_mount':str(vendor_root)}
    record=root/'runtime-provenance.json'
    if record.exists():
        old=json.loads(record.read_text(encoding='utf-8'))
        if old!=signature: raise ValueError('Runtime/source changed; preserve old jobs and use a fresh work root')
        if any(not (runtime/path).is_file() or sha(runtime/path)!=digest for path,digest in manifest.items()):
            raise ValueError('Prepared runtime source was modified')
        prepare_execution_caches(root,model_root)
        return runtime
    if runtime.exists(): raise ValueError('Untracked runtime exists; refusing overwrite')
    for relative in manifest:
        target=runtime/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SOURCE/relative,target)
    root.mkdir(parents=True,exist_ok=True)
    record.write_text(canonical(signature)+'\n',encoding='utf-8')
    prepare_execution_caches(root,model_root)
    return runtime


def provision_parent(store,pet,manifest_path):
    identifier(pet)
    path=Path(manifest_path).resolve()
    manifest=json.loads(path.read_text(encoding='utf-8-sig'))
    image=path.parent/'image.png';model=path.parent/'model.glb'
    if sha(image)!=manifest['image_sha256'] or sha(model)!=manifest['model_sha256']:
        raise ValueError('Historical parent files do not match their actual manifest')
    if type(manifest.get('stage')) is not int or manifest['stage'] not in (0,1,2):
        raise ValueError('Unsupported source stage')
    # Only the small parent image is copied. The old mesh/weights are never modified.
    relative=f"parents/{pet}/{manifest['image_sha256']}.png"
    target=store.root/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and sha(target)!=manifest['image_sha256']: raise ValueError('Parent image collision')
    if not target.exists(): shutil.copyfile(image,target)
    frozen={k:manifest[k] for k in ('stage','revision','image_sha256','model_sha256')}
    frozen.update(species=manifest.get('species','lucan'),species_contract=manifest.get('species_contract'),
                  image_relative=relative,source_kind='historical_parent',
                  source_manifest_sha256=sha(path))
    store.bind_parent(pet,frozen)
    return frozen
