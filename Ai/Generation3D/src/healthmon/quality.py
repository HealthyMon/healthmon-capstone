"""Conservative image checks. Semantic character quality still requires review."""
import json
import csv
import datetime as dt
import io
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def inspect_image(path, *, output_report=None, rejected_dir=None):
    path = Path(path)
    failures, concerns = [], []
    report = {'path': str(path.resolve()), 'technical_status': 'FAIL',
              'visual_quality': 'REVIEW_REQUIRED', 'failures': failures, 'concerns': concerns}
    try:
        im = Image.open(path)
        im.verify()
        im = Image.open(path).convert('RGBA')
        arr = np.array(im)
        report.update(size=list(im.size), mode=Image.open(path).mode)
        if min(im.size) < 512:
            failures.append('Generated reference is smaller than 512 pixels')
        alpha = arr[:, :, 3]
        has_alpha = bool((alpha < 16).any() and (alpha > 200).any())
        report['usable_alpha'] = has_alpha
        if has_alpha:
            # Ignore faint matte noise for clipping, but retain it as a concern.
            # The actual opaque subject still fails if it reaches any border.
            mask = alpha > 128
            faint = alpha > 32
            if (faint[0].any() or faint[-1].any() or faint[:,0].any() or faint[:,-1].any()) and not (
                mask[0].any() or mask[-1].any() or mask[:,0].any() or mask[:,-1].any()):
                concerns.append('Faint alpha noise reaches the border; opaque subject has margin. Matte quality needs review.')
            report['clipping_alpha_threshold'] = 128
        else:
            # White-background fallback detects only gross layout; never claims segmentation correctness.
            mask = np.min(arr[:, :, :3], axis=2) < 235
            concerns.append('No usable transparency; scenery/background needs review before 3D')
        ys, xs = np.where(mask)
        if not len(xs):
            failures.append('No visible subject')
        else:
            box = [int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)]
            report['subject_bbox'] = box
            if box[0] <= 2 or box[1] <= 2 or box[2] >= im.width-2 or box[3] >= im.height-2:
                failures.append('Subject reaches image edge; appendage clipping is possible')
            fraction = float(mask.mean())
            report['foreground_fraction'] = fraction
            if fraction < .03 or fraction > .94:
                failures.append('Unusable subject occupancy')
            labels, _ = ndimage.label(mask)
            sizes = np.bincount(labels.ravel())[1:]
            large = sorted((int(x) for x in sizes if x >= mask.size * .025), reverse=True)
            report['large_connected_components'] = large
            if len(large) > 1:
                concerns.append('Multiple large components: inspect for extra creatures or disconnected anatomy')
                if large[1] >= large[0] * .2:
                    failures.append('Multiple substantial disconnected silhouettes; unsuitable as a single-creature reconstruction input')
        if shutil.which('tesseract'):
            ocr = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '11', 'tsv'],
                                 capture_output=True, text=True, timeout=60)
            words=[]
            for row in csv.DictReader(io.StringIO(ocr.stdout),delimiter='\t'):
                try:
                    if row.get('text','').strip():
                        words.append({'text':row['text'],'confidence':float(row['conf'])})
                except (ValueError,KeyError):
                    continue
            report['ocr_words']=words
            confident=' '.join(w['text'] for w in words if w['confidence'] >= 80)
            if sum(c.isalnum() for c in confident) >= 8:
                failures.append('OCR detected substantial lettering; inspect graphic artifacts')
            elif words:
                concerns.append('Ambiguous OCR detections require visual inspection')
            concerns.append('Default OCR language is English; absence of detections does not exclude Korean labels')
        else:
            concerns.append('OCR unavailable; text artifacts are not automatically ruled out')
        concerns.append('Creature count, identity, full anatomy, and evolution semantics require visual review')
        report['technical_status'] = 'FAIL' if failures else 'PASS'
    except Exception as e:
        failures.append(f'{type(e).__name__}: {e}')
    if output_report:
        Path(output_report).parent.mkdir(parents=True, exist_ok=True)
        Path(output_report).write_text(json.dumps(report, indent=2))
    if failures and rejected_dir and path.exists():
        target = Path(rejected_dir)
        target.mkdir(parents=True, exist_ok=True)
        name=path.stem+'_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+path.suffix
        shutil.copy2(path, target / name)
        (target / (name + '.rejection.json')).write_text(json.dumps(report, indent=2))
    return report


def comparison_sheet(run_dir):
    from PIL import ImageDraw
    r = Path(run_dir)
    slots = [('ZIP reference', r/'references/source_poster_region.png','references'),
             ('Clean starting character', r/'bootstrap/start_character.png','clean_source'),
             ('Starting 3D', r/'renders/three_quarter.png','render_source'),
             ('Evolved Qwen image', r/'qwen/evolved.png','evolution'),
             ('Evolved 3D', r/'trellis/evolved_preview.png','render_evolved'),
             ('Rigged model: pose test', r/'validation/pose_test.png','validation')]
    report_file=r/'validation/report.json'
    stages=json.loads(report_file.read_text()).get('stages',{}) if report_file.exists() else {}
    sheet = Image.new('RGB', (384*3, 424*2), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (name, path,stage) in enumerate(slots):
        x, y = (i % 3)*384, (i // 3)*424
        draw.text((x+12, y+10), name, fill='black')
        status=stages.get(stage,{}).get('status','NOT RUN')
        draw.text((x+12,y+26),status+(' / REVIEW REQUIRED' if path.is_file() and stage!='references' else ''),fill=(90,90,90))
        if path.is_file():
            im = Image.open(path).convert('RGBA')
            im.thumbnail((360, 370))
            sheet.paste(im, (x+(384-im.width)//2, y+40+(370-im.height)//2), im)
        else:
            draw.text((x+12, y+65), 'NOT RUN / UNAVAILABLE', fill=(130, 40, 40))
    sheet.save(r/'comparison.png')
    return r/'comparison.png'
