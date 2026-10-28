# Loaded by login shells; entrypoint also sources this for local Docker runs.
source /opt/conda/etc/profile.d/conda.sh
export CONDA_ENVS_PATH=/workspace/conda-envs:/opt/conda/envs
export HF_HOME=/workspace/.cache/huggingface
export OPENPI_DATA_HOME=/workspace/.cache/openpi
export XDG_CACHE_HOME=/workspace/.cache
export TORCH_HOME=/workspace/.cache/torch
export UV_CACHE_DIR=/workspace/.cache/uv
export PYTHONNOUSERSITE=1
export UV_LINK_MODE=copy
export XLA_PYTHON_CLIENT_PREALLOCATE=false
vla-use() {
    local name=${1:-pi05} prefix repo
    case "$name" in
        pi05) prefix=/opt/conda/envs/pi05; repo=/opt/repos/openpi ;;
        ftp1) prefix=/opt/conda/envs/ftp1; repo=/opt/repos/ftp1-policy ;;
        univtac)
            prefix=/opt/conda/envs/univtac; repo=/opt/repos/UniVTAC
            if [[ -d /workspace/conda-envs/univtac ]]; then
                prefix=/workspace/conda-envs/univtac
                repo=${UNIVTAC_WORK_ROOT:-/workspace/src/UniVTAC}
            fi ;;
        *) echo 'Usage: vla-use {pi05|ftp1|univtac}' >&2; return 2 ;;
    esac
    if [[ ! -x "$prefix/bin/python" ]]; then
        echo "$name not installed. See README_ko.md for the optional installer." >&2
        return 1
    fi
    conda activate "$prefix" || return
    # Match uv to the active project env. Use uv run --frozen --no-sync after patching.
    export UV_PROJECT_ENVIRONMENT="$prefix"
    export VLA_PROJECT="$name" VLA_REPO="$repo"
    cd "$repo" || return
}
if [[ -x /opt/conda/envs/pi05/bin/python ]]; then
    conda activate /opt/conda/envs/pi05
    export UV_PROJECT_ENVIRONMENT=/opt/conda/envs/pi05
fi
