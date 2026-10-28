"""Each environment gets its own Transformers patch files (UV_LINK_MODE=copy)."""
from importlib.metadata import version
import importlib.util
from pathlib import Path
import shutil
import sys

if version('transformers') != '4.53.2':
    raise SystemExit('Expected transformers==4.53.2 before applying upstream model patch')
src = Path(sys.argv[1]) / 'src/openpi/models_pytorch/transformers_replace'
spec = importlib.util.find_spec('transformers')
assert spec and spec.origin
dest = Path(spec.origin).parent
if not src.is_dir() or not any(src.iterdir()):
    raise SystemExit(f'No upstream Transformers patch at {src}')
shutil.copytree(src, dest, dirs_exist_ok=True)
print(f'Applied {src} -> {dest}')
