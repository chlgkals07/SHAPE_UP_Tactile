# syntax=docker/dockerfile:1.7
ARG CUDA_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu22.04
FROM ${CUDA_IMAGE} AS base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git git-lfs build-essential gcc-12 g++-12 \
    pkg-config zip unzip ffmpeg libsndfile1 libglib2.0-0 libgl1 libegl1 \
    libvulkan1 libglx0 libxrandr2 libxcursor1 libxinerama1 libxi6 libxtst6 \
    libxkbcommon0 libfontconfig1 libsm6 libxext6 libxrender1 libnss3 libdbus-1-3 \
    openssh-server tmux tini && rm -rf /var/lib/apt/lists/*
RUN git config --system url."https://github.com/".insteadOf git@github.com: && \
    git config --system --add url."https://github.com/".insteadOf ssh://git@github.com/
ARG MINIFORGE_VERSION=25.3.1-0
RUN cd /tmp && \
    curl -fL --retry 3 -O "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-x86_64.sh" && \
    curl -fL --retry 3 -O "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-x86_64.sh.sha256" && \
    sha256sum -c "Miniforge3-${MINIFORGE_VERSION}-Linux-x86_64.sh.sha256" && \
    bash "Miniforge3-${MINIFORGE_VERSION}-Linux-x86_64.sh" -b -p /opt/conda && \
    rm Miniforge3-*.sh* && /opt/conda/bin/conda clean -afy
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /usr/local/bin/
ENV PATH=/opt/conda/bin:/opt/vla/bin:${PATH} \
    UV_LINK_MODE=copy GIT_LFS_SKIP_SMUDGE=1 PYTHONNOUSERSITE=1 \
    XLA_PYTHON_CLIENT_PREALLOCATE=false \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display \
    TORCH_CUDA_ARCH_LIST=12.0 CMAKE_CUDA_ARCHITECTURES=120 \
    HF_HOME=/workspace/.cache/huggingface \
    OPENPI_DATA_HOME=/workspace/.cache/openpi \
    XDG_CACHE_HOME=/workspace/.cache \
    TORCH_HOME=/workspace/.cache/torch \
    UV_CACHE_DIR=/workspace/.cache/uv \
    TMPDIR=/tmp
COPY config /opt/vla/config
COPY scripts /opt/vla/scripts
COPY bin /opt/vla/bin
COPY envs /opt/vla/envs
RUN chmod +x /opt/vla/bin/* /opt/vla/scripts/*.sh && \
    cp /opt/vla/scripts/profile.sh /etc/profile.d/vla.sh && \
    mkdir -p /workspace /opt/repos /opt/vla/manifests
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/vla/bin/entrypoint.sh"]
CMD ["bash"]

# Default: two model environments installed; all three source trees available.
FROM base AS sources
RUN bash /opt/vla/scripts/fetch-repos.sh

FROM sources AS pi05
RUN bash /opt/vla/scripts/install-model.sh pi05

FROM pi05 AS models
RUN bash /opt/vla/scripts/install-model.sh ftp1
RUN conda clean -afy && rm -rf /root/.cache/uv /tmp/vla-uv-cache

# Optional heavy/experimental stage. A failure does not affect target=models.
FROM models AS full
ARG ACCEPT_ISAAC_EULA=NO
ARG UNIVTAC_BUILD_JOBS=4
RUN test "${ACCEPT_ISAAC_EULA}" = YES || \
    (echo 'Set --build-arg ACCEPT_ISAAC_EULA=YES after reviewing NVIDIA terms.' >&2; exit 1)
RUN ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES \
    UNIVTAC_BUILD_JOBS=${UNIVTAC_BUILD_JOBS} \
    bash /opt/vla/scripts/install-univtac.sh /opt/conda/envs

# `docker build .` deliberately selects the higher-priority model-only target.
FROM models AS default
