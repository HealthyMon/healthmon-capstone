import asyncio
import io
import json
import logging
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

app = FastAPI()
ROOT = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 300
logger = logging.getLogger(__name__)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/food/analyze')
async def analyze_food(image: UploadFile = File(...)):
    data = await image.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail='사진이 비어 있습니다.')
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail='사진은 8MB 이하로 보내주세요.')

    # 파일 이름이나 MIME type이 아닌 이미지 내용으로 형식을 검사한다.
    try:
        with Image.open(io.BytesIO(data)) as picture:
            image_format = picture.format
            picture.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail='올바른 이미지 파일이 아닙니다.')
    suffix = {'JPEG': '.jpg', 'PNG': '.png'}.get(image_format)
    if suffix is None:
        raise HTTPException(status_code=415, detail='JPG 또는 PNG 파일만 지원합니다.')

    # 요청마다 독립된 폴더를 사용해 동시 요청의 파일명 충돌을 방지한다.
    with tempfile.TemporaryDirectory(prefix='food_') as folder:
        image_path = Path(folder) / f'food{suffix}'
        result_path = Path(folder) / 'result.json'
        image_path.write_bytes(data)

        # main.py의 Windows 전용 설치 로직을 건너뛰고, 현재 Docker Python으로 AI 실행.
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / 'main.py'),
            '--internal-worker', str(image_path),
            '--output', str(result_path),
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise HTTPException(status_code=504, detail='AI 분석 제한 시간을 초과했습니다.')

        if process.returncode != 0:
            logger.error('main.py 실패 (exit %s): %s', process.returncode,
                         stderr.decode('utf-8', errors='replace')[-5000:])
            raise HTTPException(status_code=500, detail='AI 분석 중 오류가 발생했습니다. Docker 로그를 확인하세요.')
        if not result_path.is_file():
            logger.error('main.py가 결과 JSON을 만들지 못했습니다. stdout=%s stderr=%s',
                         stdout.decode('utf-8', errors='replace')[-2000:],
                         stderr.decode('utf-8', errors='replace')[-2000:])
            raise HTTPException(status_code=500, detail='AI 분석 결과 파일이 생성되지 않았습니다.')

        try:
            result = json.loads(result_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            logger.exception('결과 JSON 읽기 실패')
            raise HTTPException(status_code=500, detail='AI 분석 결과를 읽을 수 없습니다.')

        # 서버 내부 임시 경로를 클라이언트에 노출하지 않는다.
        result['image'] = image.filename or f'food{suffix}'
        return {'status': 'success', 'ai_analyzed': True, 'result': result}
