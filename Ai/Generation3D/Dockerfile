# Rebuild on the target x86_64 PC. No Spark ARM binaries or model weights enter this image.
ARG BASE_IMAGE=nvidia/cuda@sha256:435220c0fef35cbf712e11999f8670a83835ef3cdd18564e5e8122f83078c88c
FROM --platform=linux/amd64 ${BASE_IMAGE}
ARG MAX_JOBS=4
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 \
    TORCH_CUDA_ARCH_LIST=8.6 FLASH_ATTN_CUDA_ARCHS=80 \
    FLASH_ATTENTION_FORCE_BUILD=TRUE MAX_JOBS=${MAX_JOBS}
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential cmake ninja-build pkg-config util-linux \
    python3 python3-dev python3-venv python3-pip blender=4.0.2+dfsg-1ubuntu8 \
    libgl1 libgl1-mesa-dev libegl1 libegl1-mesa-dev libglib2.0-0 libxrender1 libxi6 libxkbcommon0 \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev uuid-dev \
    && rm -rf /var/lib/apt/lists/*
ENV HEALTHMON_RUNTIME=/opt/healthmon/Ai/Generation3D HEALTHMON_ENVS=/opt/healthmon-envs \
    HEALTHMON_BLENDER=/usr/bin/blender
WORKDIR /opt/healthmon/Ai/Generation3D
COPY . .
RUN bash migration/environment/build_target.sh --target-container
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    HEALTHMON_MATTING_PYTHON=/opt/healthmon-envs/matting/bin/python \
    HEALTHMON_MATTING_CHECKPOINT=/opt/healthmon/Ai/Generation3D/models/matting/bria-rmbg.onnx \
    HOME=/tmp/healthmon-home
COPY migration/environment/docker-entrypoint.sh /usr/local/bin/healthmon-entrypoint
ENTRYPOINT ["bash", "/usr/local/bin/healthmon-entrypoint"]
CMD ["bash"]
