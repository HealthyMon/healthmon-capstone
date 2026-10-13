# CPU 실행용 예시 (Linux x86_64 기준)
FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir 'setuptools==69.5.1' wheel
RUN python -m pip install --no-cache-dir \
    fastapi uvicorn python-multipart \
    'numpy==1.23.5' 'Pillow==9.5.0' 'opencv-python==4.8.1.78' 'yapf==0.40.1'
RUN python -m pip install --no-cache-dir \
    'torch==1.13.1+cpu' 'torchvision==0.14.1+cpu' \
    --extra-index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --no-cache-dir --only-binary=mmcv-full \
    'mmcv-full==1.7.0' \
    -f https://download.openmmlab.com/mmcv/dist/cpu/torch1.13.0/index.html
RUN python -m pip install --no-cache-dir --no-build-isolation 'mmdet==2.26.0'

# 라이브러리가 정상 설치되었는지 빌드 중 확인한다.
RUN python -c 'import torch, torchvision, cv2, mmcv, mmdet; from mmcv.ops import nms; print("AI dependencies OK")'

COPY app.py main.py nutrition.py ./
# 아래 파일 네 개를 Dockerfile과 같은 폴더에 준비해야 한다.
COPY food_detector.pth food_weight_checkpoint.pth cuboid_model.pth nutrition.json ./
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
