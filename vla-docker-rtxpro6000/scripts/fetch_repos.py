"""Fetch exact upstream commits over HTTPS; never store credentials in an image."""
import json
import os
from pathlib import Path
import subprocess

root = Path('/opt/repos')
manifest = json.loads(Path('/opt/vla/config/repos.json').read_text())
env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
for name, spec in manifest.items():
    dest = root / spec['directory']
    subprocess.run(['git', 'init', str(dest)], check=True, env=env)
    subprocess.run(['git', '-C', str(dest), 'remote', 'add', 'origin', spec['url']], check=True, env=env)
    subprocess.run(['git', '-C', str(dest), 'fetch', '--depth', '1', 'origin', spec['ref']], check=True, env=env)
    subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', 'FETCH_HEAD'], check=True, env=env)
    got = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
    if got != spec['ref']:
        raise RuntimeError(f'{name}: commit mismatch {got}')
    subprocess.run(['git', '-C', str(dest), 'submodule', 'update', '--init', '--recursive', '--depth', '1'], check=True, env=env)
Path('/opt/vla/manifests/repos.json').write_text(json.dumps(manifest, indent=2) + '\n')
