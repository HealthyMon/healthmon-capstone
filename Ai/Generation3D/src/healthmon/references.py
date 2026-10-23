"""Safe archive handling and documented, species-specific reference selection."""
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def locate_zip(requested=None):
    candidates = [Path(requested)] if requested else []
    candidates += [Path('/workspace/input/healthmon_evolution_reference_pack.zip'),
                   Path('/workspace/healthmon_evolution_reference_pack.zip')]
    for base in [Path('/workspace/input'), Path('/workspace'), Path('/tmp'),
                 Path('/root/.codex/attachments')]:
        if base.exists():
            candidates.extend(base.glob('**/healthmon_evolution_reference_pack.zip'))
    for p in candidates:
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError('Required HEALTHMON reference ZIP missing. Place it at /workspace/input/healthmon_evolution_reference_pack.zip')


def extract_reference_zip(archive, assets):
    assets = Path(assets).resolve()
    assets.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if sum(x.file_size for x in z.infolist()) > 2 * 1024**3:
            raise ValueError('Reference archive exceeds 2 GiB extraction limit')
        for info in z.infolist():
            name = PurePosixPath(info.filename)
            destination = (assets / str(name)).resolve()
            if (name.is_absolute() or '..' in name.parts or '\\' in info.filename
                    or not destination.is_relative_to(assets)
                    or name.parts[0] != 'healthmon_references'
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError(f'Unsafe archive member: {info.filename}')
        # Read required documentation BEFORE decoding or processing any image.
        readme = z.read('healthmon_references/README_KO.md').decode('utf-8')
        manifest = json.loads(z.read('healthmon_references/manifest.json'))
        if manifest.get('stage_indices') != [0, 1, 2, 3]:
            raise ValueError('Reference pack does not describe exactly four stages')
        for info in z.infolist():
            z.extract(info, assets)
    return assets / 'healthmon_references', manifest, readme


def select_references(archive, run_dir, species, scenario, source_stage, target_stage):
    base, manifest, readme = extract_reference_zip(archive, ROOT / 'assets')
    regions = json.loads((ROOT / 'configs/reference_regions.json').read_text())
    if species not in manifest['species'] or scenario not in manifest['cases']:
        raise ValueError('Selected species or scenario is absent from archive manifest')
    out = Path(run_dir) / 'references'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'README_KO.original.md').write_text(readme)
    poster = base / manifest['primary_poster']
    sheet = base / f'species_sheets/{species}/{scenario}.png'
    image = Image.open(poster).convert('RGBA')
    if list(image.size) != regions['poster_size']:
        raise ValueError('Poster dimensions changed; region coordinates require review')
    selected = {}
    for role, stage in [('source', source_stage), ('target', target_stage)]:
        candidate = base / f'candidate_crops_NOT_CLEAN/{species}/{scenario}/stage_{stage}.png'
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        raw = out / f'{role}_crop.png'
        shutil.copy2(candidate, raw)
        x0, x1 = regions['x_ranges'][stage]
        y0, y1 = regions['y_ranges'][species][scenario]
        isolated = out / f'{role}_poster_region.png'
        image.crop((x0, y0, x1, y1)).save(isolated)
        selected[role] = {
            'stage': stage, 'candidate_original': str(candidate),
            'raw_crop': str(raw), 'poster_region': str(isolated),
            'poster_region_xyxy': [x0, y0, x1, y1],
            'reference_quality': 'ROUGH_DESIGN_HINT_REQUIRES_QWEN_RECONSTRUCTION',
            'uncertain_details': ['Occluded rear surfaces and exact tail anatomy are not established by this draft.',
                                  'Any full-body completion is an inference, not confirmed canonical artwork.']
        }
    result = {
        'archive': str(Path(archive).resolve()), 'archive_sha256': sha256(archive),
        'extracted_to': str(base), 'manifest': manifest,
        'readme_read_before_images': True, 'primary_poster': str(poster),
        'species_sheet': str(sheet), 'species': species, 'scenario': scenario,
        'selection_notes': regions['notes'], 'selected': selected
    }
    (Path(run_dir) / 'reference_selection.json').write_text(json.dumps(result, indent=2))
    return result
