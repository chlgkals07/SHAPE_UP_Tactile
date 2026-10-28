#!/usr/bin/env bash
set -Eeuo pipefail
# At image build time use /opt/conda/envs; on a running instance use /workspace.
env_parent=${1:-/workspace/conda-envs}
if [[ "$env_parent" != /* ]]; then
    echo 'Environment directory must be absolute' >&2; exit 2
fi
if [[ "${OMNI_KIT_ACCEPT_EULA:-NO}" != YES ]]; then
    echo 'Review NVIDIA terms, then set OMNI_KIT_ACCEPT_EULA=YES for this installer.' >&2
    exit 2
fi
if [[ "$env_parent" == /opt/conda/envs ]]; then
    repo=/opt/repos/UniVTAC
    records=/opt/vla/manifests
else
    repo=${UNIVTAC_WORK_ROOT:-/workspace/src/UniVTAC}
    records=/workspace/manifests
    if [[ ! -e "$repo" ]]; then
        mkdir -p "$(dirname "$repo")"
        cp -a /opt/repos/UniVTAC "$repo"
    fi
fi
mkdir -p "$env_parent" "$records"
python /opt/vla/scripts/patch_univtac.py "$repo" "$records"
export CONDA_ENVS_PATH="$env_parent:/opt/conda/envs"
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-/workspace/.cache/conda-pkgs}"
export UNIVTAC_CONDA_ENV=univtac
export UNIVTAC_CUDA_ARCH=120
export UNIVTAC_BUILD_JOBS=${UNIVTAC_BUILD_JOBS:-4}
export PIP_CONSTRAINT=/opt/vla/config/constraints-univtac.txt
# Crucially, Isaac/TacEx/cuRobo cannot overwrite the pi05 or ftp1 environments.
bash "$repo/scripts/install.sh"
conda run --no-capture-output -p "$env_parent/univtac" python -m pip freeze > "$records/univtac.freeze.txt"
conda list -p "$env_parent/univtac" --explicit > "$records/univtac.conda-explicit.txt"
printf '%s\n' "$repo" > "$records/univtac-source-path.txt"
echo "Installed experimental UniVTAC stack; next run vla-check univtac on the GPU."
