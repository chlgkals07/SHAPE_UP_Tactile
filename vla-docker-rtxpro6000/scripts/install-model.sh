#!/usr/bin/env bash
set -Eeuo pipefail
name=${1:?pi05 or ftp1}
case "$name" in
    pi05) repo=/opt/repos/openpi ;;
    ftp1) repo=/opt/repos/ftp1-policy ;;
    *) echo 'Expected pi05 or ftp1' >&2; exit 2 ;;
esac
conda create -y -p "/opt/conda/envs/$name" --override-channels -c conda-forge python=3.11 pip
python /opt/vla/scripts/patch_model.py "$repo" "$name" /opt/vla/manifests
cd "$repo"
export UV_PROJECT_ENVIRONMENT="/opt/conda/envs/$name"
export UV_CACHE_DIR=/tmp/vla-uv-cache
export UV_LINK_MODE=copy
# Re-resolve intentionally: the upstream lock points at the default CUDA build.
# The resulting lock and package inventory are retained in the built image.
uv lock --python "$UV_PROJECT_ENVIRONMENT/bin/python"
uv sync --no-dev --inexact --python "$UV_PROJECT_ENVIRONMENT/bin/python"
"$UV_PROJECT_ENVIRONMENT/bin/python" /opt/vla/scripts/patch_transformers.py "$repo"
uv pip check --python "$UV_PROJECT_ENVIRONMENT/bin/python"
JAX_PLATFORMS=cpu "$UV_PROJECT_ENVIRONMENT/bin/python" /opt/vla/scripts/smoke_model.py --cpu --project "$name"
cp uv.lock "/opt/vla/manifests/$name.uv.lock"
uv pip freeze --python "$UV_PROJECT_ENVIRONMENT/bin/python" > "/opt/vla/manifests/$name.freeze.txt"
conda list -p "/opt/conda/envs/$name" --explicit > "/opt/vla/manifests/$name.conda-explicit.txt"
