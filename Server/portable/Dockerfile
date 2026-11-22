# All AI Python environments are isolated in one image. The supervisor releases
# only the dialogue process while sequential evolution subprocesses own the GPU.
ARG BASE_IMAGE=healthmon-evolution-2511:local
FROM ${BASE_IMAGE}
USER root
ENV HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0
COPY Server/portable/requirements-control.txt /tmp/control.txt
RUN python3 -m venv /opt/healthmon-envs/control \
    && /opt/healthmon-envs/control/bin/python -m pip install -r /tmp/control.txt \
    && python3 -m venv --system-site-packages /opt/healthmon-envs/dialogue \
    && /opt/healthmon-envs/dialogue/bin/python -m pip install -r /tmp/control.txt \
       transformers==5.5.1 tokenizers==0.22.2 peft==0.18.1 accelerate==1.13.0 \
       safetensors==0.8.0 sentencepiece==0.2.1 einops==0.8.1 \
    && /opt/healthmon-python310/bin/python3.10 -m venv /opt/healthmon-envs/vision \
    && /opt/healthmon-envs/vision/bin/python -m pip install setuptools==69.5.1 wheel \
       numpy==1.23.5 Pillow==9.5.0 opencv-python==4.8.1.78 yapf==0.40.1 \
    && /opt/healthmon-envs/vision/bin/python -m pip install \
       torch==1.13.1+cpu torchvision==0.14.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu \
    && /opt/healthmon-envs/vision/bin/python -m pip install --only-binary=mmcv-full \
       mmcv-full==1.7.0 -f https://download.openmmlab.com/mmcv/dist/cpu/torch1.13.0/index.html \
    && /opt/healthmon-envs/vision/bin/python -m pip install --no-build-isolation mmdet==2.26.0 \
    && python3 -m venv /opt/healthmon-envs/pose \
    && /opt/healthmon-envs/pose/bin/python -m pip install -r /tmp/control.txt \
       numpy==2.2.6 onnxruntime==1.32.0 opencv-python==4.11.0.86 opencv-contrib-python==4.11.0.86 rtmlib==0.0.16
WORKDIR /app
COPY Server/ /app/Server/
COPY Ai/Generation3D/ /app/Ai/Generation3D/
COPY Ai/LLM/config/ /app/Ai/LLM/config/
COPY Ai/Pose/ /app/Ai/Pose/
COPY Ai/Vision/ /app/Ai/Vision/
ENV HEALTHMON_SERVICE_STATE=/app/.runtime/portable \
    HEALTHMON_ROUTER_BIND=0.0.0.0 HEALTHMON_POSE_BIND=0.0.0.0 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DIFFSYNTH_SKIP_DOWNLOAD=True \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["/opt/healthmon-envs/control/bin/python", "-B", "-m", "Server.portable.bootstrap"]
CMD ["serve"]
