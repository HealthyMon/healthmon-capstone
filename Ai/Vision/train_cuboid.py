"""빠른 Cuboid 학습: ZIP/part 파일에서 5,000장만 읽고 ResNet18 특징 캐시 + 회귀 헤드 학습.

사용 방법 (Windows PowerShell):
    python train_cuboid_fast.py --smoke
    python train_cuboid_fast.py
    python train_cuboid_fast.py --max-samples 5000 --epochs 10 --workers 2
    python train_cuboid_fast.py --images "D:/VS.zip.part0" --labels "D:/VL.zip.part0"

실제 사진-라벨의 연결은 기존 AI Hub JSON data.image_info.file_name 기준.
VS/VL 사용 시 원 데이터셋의 공식 검증 분할이 아닌 내부 그룹 분할로 평가.

핵심: ImageNet pretrained ResNet18 백본을 고정하여 이미지마다 특징을 한 번 추출,
.feature_cache에 보관. 이후 10 epoch는 저장된 512차원 특징만으로 fc(16좌표) 학습.
정확도에 불리할 수 있으므로 정식 결과 전에 충분히 검증하세요.
"""
from __future__ import annotations
import argparse
import bisect
import collections
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parent
IMAGE_DIR = r""
LABEL_DIR = r""
EPOCHS = 10
BATCH_SIZE = 32
MAX_SAMPLES = 5000

def bootstrap():
    """기존 MMCV용 .venv는 건드리지 않고 별도 CUDA 환경을 사용합니다."""
    target = ROOT / '.train_venv' / 'Scripts' / 'python.exe'
    base = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not target.is_file():
        if not base.is_file():
            raise RuntimeError('같은 폴더에 .venv 또는 .train_venv가 없습니다. 먼저 main.py를 실행하여 .venv를 준비하세요.')
        print('학습 전용 가상환경을 생성합니다: .train_venv', flush=True)
        subprocess.run([str(base), '-m', 'venv', str(target.parent.parent)], check=True)

    torch_check = ('import torch, torchvision; '
                   'assert torch.__version__.startswith("2.5.1"); '
                   'assert torch.cuda.is_available()')
    if subprocess.run([str(target), '-c', torch_check], capture_output=True).returncode != 0:
        print('CUDA PyTorch 2.5.1 설치 중... (최초 1회)', flush=True)
        subprocess.run([str(target), '-m', 'pip', 'install', 'pip==24.0'], check=True)
        subprocess.run([str(target), '-m', 'pip', 'install',
                        'torch==2.5.1+cu121', 'torchvision==0.20.1+cu121',
                        '--extra-index-url', 'https://download.pytorch.org/whl/cu121'], check=True)

    deps_check = 'import cv2,numpy,PIL,tqdm,tkinter'
    if subprocess.run([str(target), '-c', deps_check], capture_output=True).returncode != 0:
        print('학습 의존성 설치 중...', flush=True)
        subprocess.run([str(target), '-m', 'pip', 'install',
                        'numpy==1.26.4', 'pillow==10.4.0',
                        'opencv-python==4.10.0.84', 'tqdm'], check=True)

    subprocess.run([str(target), '-c', torch_check + '; ' + deps_check], check=True)
    return target

def choose_source(title):
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    window.withdraw()
    try:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[('ZIP/분할 파일', '*.zip *.part*'), ('모든 파일', '*.*')],
        )
    finally:
        window.destroy()
    if not path:
        raise RuntimeError('파일 선택을 취소했습니다. --images, --labels로 경로를 지정할 수도 있습니다.')
    return Path(path)

def norm_name(name):
    """ZIP 안의 경로 구분자와 Unicode 표기 차이를 제거하고 파일명만 비교."""
    return unicodedata.normalize('NFC', PurePosixPath(str(name).replace('\\', '/')).name).casefold()

class MultipartReader:
    """VS.zip.part0, .part1073741824 등을 하나의 seekable 이진 파일처럼 읽음.

    메모리에 전체 압축파일을 올리지 않고 파일 하나씩 열어 읽습니다.
    """
    def __init__(self, parts):
        self.parts = parts
        self.starts = []
        self.part_sizes = []
        pos = 0
        for offset, path in parts:
            if offset != pos:
                raise ValueError(f'분할 파일이 빠졌거나 크기가 맞지 않습니다: {path.name} (필요 오프셋 {pos})')
            self.starts.append(pos)
            part_size = path.stat().st_size
            self.part_sizes.append(part_size)
            pos += part_size
        self.length = pos
        self.position = 0
        self.active_index = -1
        self.handle = None
        self.closed = False

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self.position + offset
        elif whence == io.SEEK_END:
            pos = self.length + offset
        else:
            raise ValueError(f'지원하지 않는 seek 방식: {whence}')
        if pos < 0:
            raise ValueError('음수 위치로 이동할 수 없습니다.')
        self.position = pos
        return pos

    def read(self, size=-1):
        if self.closed:
            raise ValueError('닫힌 파일입니다.')
        remaining = max(0, self.length - self.position)
        if size is None or size < 0:
            size = remaining
        size = min(size, remaining)
        blocks = []
        while size > 0:
            idx = bisect.bisect_right(self.starts, self.position) - 1
            offset, path = self.parts[idx]
            local_pos = self.position - offset
            amount = min(size, self.part_sizes[idx] - local_pos)
            if amount <= 0:
                raise OSError('분할 파일에서 읽을 수 없습니다: ' + str(path))
            if self.active_index != idx:
                if self.handle is not None:
                    self.handle.close()
                self.handle = open(path, 'rb')
                self.active_index = idx
            self.handle.seek(local_pos)
            block = self.handle.read(amount)
            if len(block) != amount:
                raise OSError('분할 파일을 끝까지 읽지 못했습니다: ' + str(path))
            blocks.append(block)
            self.position += amount
            size -= amount
        return b''.join(blocks)

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        self.closed = True

def archive_parts(path):
    """*.zip.part0이 주어졌을 때 partN 목록을 오프셋 기준으로 정렬."""
    filename = path.name
    base, sep, part = filename.rpartition('.part')
    if not sep or not part.isdecimal():
        return None
    parts = []
    for candidate in path.parent.glob(base + '.part*'):
        suffix = candidate.name[len(base) + len('.part'):]
        if suffix.isdecimal():
            parts.append((int(suffix), candidate))
    return sorted(parts)

@contextmanager
def open_archive(path):
    """일반 ZIP이나 AI Hub 연속 분할 ZIP을 직접 연다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'파일이 없습니다: {path}')
    parts = archive_parts(path)
    handle = None
    try:
        if parts is not None:
            if parts[0][0] != 0:
                raise ValueError('part0 파일이 없습니다: ' + str(path))
            handle = MultipartReader(parts)
            zf = zipfile.ZipFile(handle, 'r')
        else:
            zf = zipfile.ZipFile(path, 'r')
        with zf:
            yield zf
    except zipfile.BadZipFile as e:
        raise ValueError(f'{path.name}: 올바른 ZIP이 아닙니다. 다운로드/병합 누락을 확인하세요.') from e
    finally:
        if handle is not None:
            handle.close()

class DataSource:
    """ZIP 또는 압축 해제된 디렉터리에서 member 단위로 파일 목록/바이트를 읽음."""
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._ctx = None
        self._zip = None

    def __enter__(self):
        if self.path.is_file():
            self._ctx = open_archive(self.path)
            self._zip = self._ctx.__enter__()
        return self

    def __exit__(self, typ, value, tb):
        if self._ctx is not None:
            try:
                return self._ctx.__exit__(typ, value, tb)
            finally:
                self._ctx = self._zip = None

    def members(self, extensions):
        if self.path.is_file():
            if self._zip is None:
                raise RuntimeError('DataSource는 with 문 안에서 사용하세요.')
            return sorted(i.filename for i in self._zip.infolist()
                          if not i.is_dir() and PurePosixPath(i.filename.replace('\\', '/')).suffix.lower() in extensions)
        return sorted(p.relative_to(self.path).as_posix() for p in self.path.rglob('*')
                      if p.is_file() and p.suffix.lower() in extensions)

    def read_bytes(self, member):
        if self.path.is_file():
            if self._zip is None:
                raise RuntimeError('DataSource는 with 문 안에서 사용하세요.')
            with self._zip.open(member) as fp:
                return fp.read()
        # 디렉터리에서도 상대 경로만 사용
        return self.path.joinpath(*PurePosixPath(member).parts).read_bytes()

def rgb_from_bytes(blob, name):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'사진을 읽지 못했습니다: {name}')
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

def image_tensor(rgb):
    import cv2
    import numpy as np
    import torch
    a = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255
    a = (a - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)
    return torch.from_numpy(a.transpose(2, 0, 1).copy())

class Photos:
    """각 프로세스가 ZIP을 한 번만 열고, 사진 1장을 필요할 때 읽음."""
    def __init__(self, rows, source_path):
        self.rows = rows
        self.source_path = str(source_path)
        self._source = None

    def __len__(self):
        return len(self.rows)

    def __getstate__(self):
        state = self.__dict__.copy()
        state['_source'] = None
        return state

    def __getitem__(self, index):
        import torch
        if self._source is None:
            self._source = DataSource(self.source_path)
            self._source.__enter__()
        row = self.rows[index]
        rgb = rgb_from_bytes(self._source.read_bytes(row['image_member']), row['image_member'])
        target = torch.tensor(row['points'], dtype=torch.float32).reshape(16)
        return image_tensor(rgb), target

    def __del__(self):
        source = getattr(self, '_source', None)
        if source is not None:
            source.__exit__(None, None, None)

def build_model(pretrained):
    import torch
    from torchvision.models import resnet18, ResNet18_Weights
    model = resnet18(weights=ResNet18_Weights.DEFAULT if pretrained else None)
    model.fc = torch.nn.Linear(512, 16)
    return model

def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def save_preview(model, row, image_source, device, folder):
    """실제 검증 사진 1장에 정답/예측 꼭짓점 표시 (상자 연결선은 순서 검증 필요)."""
    import cv2
    import numpy as np
    import torch
    with DataSource(image_source) as photos:
        rgb = rgb_from_bytes(photos.read_bytes(row['image_member']), row['image_member'])
    h, w = rgb.shape[:2]
    model.eval()
    with torch.inference_mode():
        points = model(image_tensor(rgb).unsqueeze(0).to(device)).cpu().numpy().reshape(8, 2)
    image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for i, point in enumerate(points):
        x, y = round(float(point[0]) * w), round(float(point[1]) * h)
        cv2.circle(image, (x, y), 6, (0, 0, 255), -1)
        cv2.putText(image, str(i + 1), (x + 6, y - 5), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
    for i, point in enumerate(row['points']):
        x, y = round(point[0] * w), round(point[1] * h)
        cv2.circle(image, (x, y), 5, (0, 220, 0), 2)
    ok, encoded = cv2.imencode('.jpg', image)
    if ok:
        (folder / 'cuboid_preview.jpg').write_bytes(encoded.tobytes())
        print('꼭짓점 미리보기: cuboid_preview.jpg (빨강=예측 / 초록=정답)', flush=True)

def init_loader_worker(worker_id):
    """데이터로더 worker마다 OpenCV 과도한 CPU 스레드 사용 방지."""
    import cv2
    import torch
    cv2.setNumThreads(1)
    torch.set_num_threads(1)

def index_sample(images_path, labels_path, max_samples, seed):
    """JSON 순서를 무작위로 섞어서 필요한 샘플만 파싱(전체 라벨 스캔 안 함)."""
    from tqdm.auto import tqdm
    image_map = collections.defaultdict(list)
    print('이미지 ZIP의 파일 목록 확인...', flush=True)
    with DataSource(images_path) as images:
        photo_names = images.members({'.jpg', '.jpeg', '.png'})
    for member in photo_names:
        image_map[norm_name(member)].append(member)
    if not image_map:
        raise ValueError('ZIP에서 JPG/PNG를 찾지 못했습니다.')
    print(f'이미지 목록: {len(photo_names):,}개', flush=True)
    rows, seen, issues = [], set(), collections.Counter()
    with DataSource(labels_path) as labels:
        label_names = labels.members({'.json'})
        if not label_names:
            raise ValueError('라벨 ZIP에서 JSON을 찾지 못했습니다.')
        rng = random.Random(seed)
        rng.shuffle(label_names)
        # 무작위 라벨을 읽어 최대 max_samples개만 확보, 전수 JSON 파싱 방지
        with tqdm(total=min(max_samples, len(label_names)), desc='JSON 샘플 추출', unit='개') as bar:
            for member in label_names:
                if len(rows) >= max_samples:
                    break
                try:
                    doc = json.loads(labels.read_bytes(member).decode('utf-8-sig'))
                    data = doc['data']
                    info = data['image_info']
                    filename = str(info['file_name'])
                    matches = image_map.get(norm_name(filename), [])
                    if len(matches) != 1:
                        issues['missing_photo' if not matches else 'ambiguous_photo'] += 1
                        continue
                    if norm_name(filename) in seen:
                        issues['duplicate_label'] += 1
                        continue
                    w, h = float(info['width']), float(info['height'])
                    xs = data['3d_annotation']['x']
                    ys = data['3d_annotation']['y']
                    if not (math.isfinite(w) and math.isfinite(h) and w > 0 and h > 0
                            and len(xs) == 8 and len(ys) == 8):
                        raise ValueError('좌표 형식 오류')
                    points = [[float(x) / w, float(y) / h] for x, y in zip(xs, ys)]
                    if not all(math.isfinite(v) and abs(v) < 10 for point in points for v in point):
                        raise ValueError('좌표 값 오류')
                    parts = Path(filename).stem.split('_')
                    restaurant = data.get('restaurant', {})
                    grouping = [parts[:3], restaurant] if restaurant else (parts[:-1] if len(parts) > 1 else parts)
                    group = json.dumps(grouping, ensure_ascii=False, sort_keys=True)
                    rows.append({'image_member': matches[0], 'label_member': member,
                                 'points': points, 'group': group})
                    seen.add(norm_name(filename))
                    bar.update(1)
                except (ValueError, KeyError, TypeError, OSError, UnicodeError, zipfile.BadZipFile):
                    issues['invalid_label'] += 1
    print(f'샘플 확보: {len(rows):,}장 / 제외 사유: {dict(issues)}', flush=True)
    if not rows:
        raise ValueError('일치하는 이미지와 JSON이 없습니다. VS/VL 조합을 확인하세요.')
    if issues['ambiguous_photo'] or issues['duplicate_label']:
        print('주의: 이름이 중복되거나 매칭이 애매한 일부 샘플은 제외했습니다.', flush=True)
    return rows


def split_sample(rows, seed):
    """음식 촬영 그룹 단위 train/val/test 분할(약 70/15/15)."""
    groups = sorted({row['group'] for row in rows})
    if len(groups) < 6:
        raise ValueError(f'서로 다른 촬영 그룹이 {len(groups)}개뿐입니다. 최소 6개 필요합니다.')
    random.Random(seed).shuffle(groups)
    n = max(1, int(len(groups) * 0.15))
    test_groups, val_groups = set(groups[:n]), set(groups[n:2*n])
    splits = {'train': [], 'val': [], 'test': []}
    for r in rows:
        key = 'test' if r['group'] in test_groups else 'val' if r['group'] in val_groups else 'train'
        splits[key].append(r)
    if any(not v for v in splits.values()):
        raise ValueError('train/val/test 분할 중 빈 항목이 있습니다.')
    print('분할 수:', {k: len(v) for k,v in splits.items()}, flush=True)
    return splits


def archive_signature(path):
    """캐시가 다른 ZIP에서 재사용되지 않도록 파트별 위치/수정일/크기 기록."""
    path = Path(path).resolve()
    if path.is_file():
        parts = archive_parts(path)
        files = [p for offset, p in parts] if parts is not None else [path]
        return [(str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    # 폴더 입력 시 직접 수정 후 캐시 무효화가 필요할 수 있음
    return [('directory', str(path), path.stat().st_mtime_ns)]


def cache_filename(images_path, labels_path, args):
    signature = {
        'version': 'frozen_resnet18_features_v2',
        'images': archive_signature(images_path),
        'labels': archive_signature(labels_path),
        'sample_limit': args.max_samples,
        'seed': args.seed,
        'pretrained': not args.no_pretrained,
        'smoke': args.smoke,
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def extract_cache(model, source_path, splits, device, args):
    import torch
    from torch.utils.data import DataLoader
    from tqdm.auto import tqdm
    import cv2
    cv2.setNumThreads(1)
    combined = splits['train'] + splits['val'] + splits['test']
    dataset = Photos(combined, source_path)
    loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=args.workers,
                        pin_memory=(device.type == 'cuda'), shuffle=False,
                        worker_init_fn=init_loader_worker if args.workers else None,
                        persistent_workers=(args.workers > 0))
    # avgpool까지 추출하고 fc는 학습에서만 사용
    backbone = torch.nn.Sequential(*list(model.children())[:-1]).eval().to(device)
    for p in backbone.parameters():
        p.requires_grad_(False)
    features, labels = [], []
    begin = time.time()
    with torch.inference_mode():
        for images, targets in tqdm(loader, desc='ResNet18 특징 추출 (최초 1회)', unit='배치'):
            images = images.to(device, non_blocking=True)
            with torch.autocast('cuda', dtype=torch.float16, enabled=device.type == 'cuda'):
                batch_features = backbone(images).flatten(1)
            features.append(batch_features.float().cpu())
            labels.append(targets.float().cpu())
    feats = torch.cat(features, dim=0).contiguous()
    y = torch.cat(labels, dim=0).contiguous()
    assert feats.shape == (len(combined), 512)
    assert y.shape == (len(combined), 16)
    cuts = {
        'train': [0, len(splits['train'])],
        'val': [len(splits['train']), len(splits['train']) + len(splits['val'])],
        'test': [len(splits['train']) + len(splits['val']), len(combined)],
    }
    print(f'특징 추출 완료: {len(combined):,}장 / {time.time()-begin:.1f}초, 메모리 {feats.numel()*4 / 2**20:.1f} MiB', flush=True)
    return {'features': feats, 'targets': y, 'splits': cuts, 'rows': combined}


def train_head(model, cache, args, device, run_dir, fingerprint):
    import torch
    from tqdm.auto import trange
    model = model.to(device)
    model.fc.train()
    for param in model.parameters():
        param.requires_grad_(False)
    for param in model.fc.parameters():
        param.requires_grad_(True)
    # 특징이 작아 GPU 메모리에 전부 넣고 초고속 반복 사용 가능
    feat = cache['features'].to(device, non_blocking=True)
    target = cache['targets'].to(device, non_blocking=True)
    cuts = cache['splits']
    a, b = cuts['train']; vx, vy = cuts['val']; tx, ty = cuts['test']
    optimizer = torch.optim.AdamW(model.fc.parameters(), lr=args.lr, weight_decay=1e-4)
    start_epoch, best, best_epoch, patience_count = 0, float('inf'), 0, 0
    if args.resume:
        ckpt = torch.load(args.resume, map_location='cpu', weights_only=True)
        if ckpt.get('training_method') != 'frozen_resnet18_feature_cache' or ckpt.get('fingerprint') != fingerprint:
            raise ValueError('이 체크포인트는 현재 캐시/학습 방식과 호환되지 않습니다. 이전 전체 미세조정 모델은 이어 학습할 수 없습니다.')
        model.load_state_dict(ckpt['state_dict'])
        optimizer.load_state_dict(ckpt['optimizer'])
        start_epoch, best = int(ckpt['epoch']), float(ckpt['best_val'])
        if start_epoch >= args.epochs:
            raise ValueError('--epochs는 체크포인트의 완료 epoch보다 커야 합니다.')
        prior_best = Path(args.resume).parent / 'best_cuboid.pth'
        if prior_best.is_file():
            shutil.copy2(prior_best, run_dir / 'best_cuboid.pth')
        print(f'{start_epoch} epoch부터 이어 학습합니다.', flush=True)

    def measure(begin, end):
        model.fc.eval()
        with torch.inference_mode():
            p = model.fc(feat[begin:end])
            loss = torch.nn.functional.smooth_l1_loss(p, target[begin:end], beta=0.05).item()
            err = (p - target[begin:end]).reshape(-1, 8, 2).norm(dim=2).mean().item()
        return loss, err

    for epoch in trange(start_epoch, args.epochs, desc='헤드 학습 (캐시 사용)', unit='epoch'):
        model.fc.train()
        order = torch.randperm(b-a, device=device)
        for idx in order.split(args.head_batch):
            pred = model.fc(feat[a + idx])
            loss = torch.nn.functional.smooth_l1_loss(pred, target[a + idx], beta=0.05)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        train_loss, _ = measure(a, b)
        val_loss, val_err = measure(vx, vy)
        improved = val_loss < best - 1e-7
        if improved:
            best, best_epoch, patience_count = val_loss, epoch + 1, 0
        else:
            patience_count += 1
        state = {
            'architecture': 'resnet18_cuboid_v1',
            'state_dict': model.state_dict(),
            'epoch': epoch + 1, 'best_val': best, 'fingerprint': fingerprint,
            'input': 'opencv_oriented_RGB_resize224_imagenet',
            'smoke_test': args.smoke or args.no_pretrained,
            'training_method': 'frozen_resnet18_feature_cache',
            'sample_limit': args.max_samples,
        }
        if improved:
            torch.save(state, run_dir / 'best_cuboid.pth')
        torch.save({**state, 'optimizer': optimizer.state_dict()}, run_dir / 'last_checkpoint.pth')
        with (run_dir / 'history.jsonl').open('a', encoding='utf-8') as fp:
            fp.write(json.dumps({'epoch': epoch+1, 'train_loss': train_loss,
                                 'val_loss': val_loss, 'val_normalized_vertex_error': val_err})+'\n')
        print(f'Epoch {epoch+1}/{args.epochs}: train={train_loss:.5f}, val={val_loss:.5f}, vertex_err={val_err:.5f}', flush=True)
        if args.patience and patience_count >= args.patience:
            print(f'검증 성능 개선 없음: 조기 종료 ({epoch+1}/{args.epochs})', flush=True)
            break
    if not (run_dir / 'best_cuboid.pth').exists():
        raise RuntimeError('최적 모델이 저장되지 않았습니다.')
    best_ckpt = torch.load(run_dir / 'best_cuboid.pth', map_location='cpu', weights_only=True)
    model.load_state_dict(best_ckpt['state_dict'])
    test_loss, test_err = measure(tx, ty)
    save_json(run_dir / 'test_metrics.json', {
        'loss': test_loss, 'normalized_vertex_error': test_err, 'test_samples': ty-tx,
        'best_epoch': best_epoch or best_ckpt['epoch'],
        'training_method': 'frozen_resnet18_feature_cache',
    })
    print(f'테스트: loss={test_loss:.5f}, normalized_vertex_error={test_err:.5f}', flush=True)
    return model


def main_worker():
    import numpy as np
    import torch
    parser = argparse.ArgumentParser(description='ZIP 직접 읽기 + ResNet18 특징 캐시 + 빠른 Cuboid 학습')
    parser.add_argument('--images', type=Path, default=Path(IMAGE_DIR) if IMAGE_DIR else None)
    parser.add_argument('--labels', type=Path, default=Path(LABEL_DIR) if LABEL_DIR else None)
    parser.add_argument('--max-samples', type=int, default=MAX_SAMPLES)
    parser.add_argument('--epochs', type=int, default=EPOCHS)
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help='특징 추출 배치 크기')
    parser.add_argument('--head-batch', type=int, default=256, help='캐시 특징을 학습하는 배치 크기')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--patience', type=int, default=3, help='조기 종료(0이면 비활성화)')
    parser.add_argument('--resume', type=Path, default=None, help='이 빠른 학습 코드에서 생성한 last_checkpoint.pth만 지원')
    parser.add_argument('--rebuild-cache', action='store_true', help='기존 특징 캐시 무시')
    parser.add_argument('--smoke', action='store_true', help='1 Epoch, 최대 24장으로 동작만 확인')
    parser.add_argument('--no-pretrained', action='store_true', help='디버그용. 임의 가중치로 특징 추출 (실사용 금지)')
    args = parser.parse_args()
    if args.max_samples < 6 or args.epochs < 1 or args.batch_size < 1 or args.head_batch < 2 or args.workers < 0:
        parser.error('max-samples>=6, epochs>=1, batch-size>=1, head-batch>=2, workers>=0 필요')
    if args.no_pretrained and not args.smoke:
        parser.error('--no-pretrained는 --smoke 테스트에서만 사용할 수 있습니다.')
    if args.smoke:
        args.max_samples = min(args.max_samples, 24)
        args.epochs = 1
    device = torch.device(args.device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU를 사용할 수 없습니다. .train_venv의 CUDA torch와 드라이버를 확인하세요.')
    if device.type == 'cuda':
        print('[GPU]', torch.cuda.get_device_name(0), '| AMP FP16 특징 추출', flush=True)
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
    else:
        print('[CPU] 디버그 모드', flush=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    args.images = (args.images or choose_source('원천 사진 ZIP (VS.zip / VS.zip.part0)')).resolve()
    args.labels = (args.labels or choose_source('라벨 JSON ZIP (VL.zip / VL.zip.part0)')).resolve()
    print('이미지:', args.images, '\n라벨:', args.labels, flush=True)
    cache_key = cache_filename(args.images, args.labels, args)
    cache_dir = ROOT / '.feature_cache'
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / f'features_{cache_key}.pt'
    model = build_model(not args.no_pretrained)
    # pretrained 특징 추출용: backbone은 학습 내내 고정한다
    if cache_path.is_file() and not args.rebuild_cache:
        print('[캐시 재사용] JSON 스캔·사진 ZIP 읽기·특징 추출을 건너뜁니다.', flush=True)
        cache = torch.load(cache_path, map_location='cpu', weights_only=True)
    else:
        print(f'최대 {args.max_samples:,}장만 무작위 추출합니다. 이미지를 반복 압축 해제하지 않습니다.', flush=True)
        rows = index_sample(args.images, args.labels, args.max_samples, args.seed)
        splits = split_sample(rows, args.seed)
        cache = extract_cache(model, args.images, splits, device, args)
        cache_temp = cache_path.with_suffix('.tmp')
        torch.save(cache, cache_temp)
        cache_temp.replace(cache_path)
        print('[캐시 저장]', cache_path, flush=True)
    run_dir = ROOT / 'training_runs' / time.strftime('%Y%m%d_%H%M%S')
    if run_dir.exists():
        run_dir = ROOT / 'training_runs' / (time.strftime('%Y%m%d_%H%M%S') + '_' + str(os.getpid()))
    run_dir.mkdir(parents=True, exist_ok=False)
    save_json(run_dir / 'manifest.json', {
        'images': str(args.images), 'labels': str(args.labels),
        'sample_limit': args.max_samples, 'cached_feature_path': str(cache_path),
        'cache_fingerprint': cache_key, 'grouped_split': True, 'official_benchmark': False,
        'feature_extractor': 'ImageNet ResNet18 frozen',
        'train_samples': cache['splits']['train'][1]-cache['splits']['train'][0],
        'val_samples': cache['splits']['val'][1]-cache['splits']['val'][0],
        'test_samples': cache['splits']['test'][1]-cache['splits']['test'][0],
    })
    print('[저장 폴더]', run_dir, flush=True)
    model = train_head(model, cache, args, device, run_dir, cache_key)
    try:
        row = cache['rows'][cache['splits']['test'][0]]
        save_preview(model, row, args.images, device, run_dir)
    except Exception as e:
        print(f'미리보기 이미지 생성은 생략했습니다: {type(e).__name__}: {e}', flush=True)
    print('학습 완료:', run_dir / 'best_cuboid.pth', flush=True)
    print('이 모델은 Cuboid 꼭짓점만 예측하며, 무게 예측은 별도 모델이 필요합니다.', flush=True)
    print('예측할 때: predict_cuboid.py --model "' + str(run_dir / 'best_cuboid.pth') + '" --image food.jpg', flush=True)


if __name__ == '__main__':
    try:
        if '--worker' in sys.argv:
            sys.argv.remove('--worker')
            main_worker()
        else:
            python = bootstrap()
            subprocess.run([str(python), str(Path(__file__).resolve()), '--worker', *sys.argv[1:]], check=True)
    except KeyboardInterrupt:
        print('사용자 중단', flush=True)
        sys.exit(130)
    except Exception as exc:
        print(f'오류: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
