#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /workspace/.cache/{huggingface,openpi,torch,uv,ov,nv} \
    /workspace/{data,checkpoints,runs,src,manifests,conda-envs}
# Stable, visible output locations even when upstream training uses relative paths.
for entry in 'openpi:pi05' 'ftp1-policy:ftp1' 'UniVTAC:univtac'; do
    repo=${entry%%:*}; name=${entry##*:}
    mkdir -p "/workspace/runs/$name/checkpoints"
    path="/opt/repos/$repo/checkpoints"
    if [[ ! -e "$path" && ! -L "$path" && -d "/opt/repos/$repo" ]]; then
        ln -s "/workspace/runs/$name/checkpoints" "$path"
    fi
done
if [[ ! -e /root/.nv && ! -L /root/.nv ]]; then
    ln -s /workspace/.cache/nv /root/.nv
fi
# Symlink only absent/empty caches. Never replace non-empty user data.
mkdir -p /root/.cache
for entry in 'ov:ov' 'nv:nv'; do
    src="/root/.cache/${entry%%:*}"
    if [[ ! -e "$src" && ! -L "$src" ]]; then
        ln -s "/workspace/.cache/${entry##*:}" "$src"
    fi
done
