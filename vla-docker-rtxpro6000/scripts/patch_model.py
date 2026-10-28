"""Make narrowly scoped dependency edits; original and adjusted manifests are recorded."""
import json
from pathlib import Path
import re
import sys
import tomllib


def patch(root: Path, name: str, records: Path):
    path = root / 'pyproject.toml'
    text = path.read_text()
    original = tomllib.loads(text)
    if original['project']['name'] != 'openpi':
        raise ValueError('Expected an OpenPI-based project')
    if '"torch==2.7.1"' not in text or '"transformers==4.53.2"' not in text:
        raise ValueError('Upstream core pins changed; review before patching')
    records.mkdir(parents=True, exist_ok=True)
    (records / f'{name}.pyproject.upstream.toml').write_text(text)
    # Restrict the universal resolver to the interpreter actually installed here.
    text, count = re.subn(r'(?m)^requires-python = .*$', 'requires-python = "==3.11.*"', text, count=1)
    assert count == 1
    # LeRobot already uses headless OpenCV. Avoid two wheels owning the cv2 namespace.
    text = text.replace('"opencv-python>=4.10.0.84"', '"opencv-python-headless==4.11.0.86"')
    overrides = original['tool']['uv'].get('override-dependencies', [])
    pins = {
        'numpy': 'numpy==1.26.4',
        'opencv-python': 'opencv-python==4.11.0.86',
        'opencv-python-headless': 'opencv-python-headless==4.11.0.86',
        'torch': 'torch==2.7.1',
        'torchvision': 'torchvision==0.22.1',
        'torchaudio': 'torchaudio==2.7.1',
        'torchcodec': 'torchcodec==0.4.0',
        'huggingface-hub': 'huggingface-hub==0.32.3',
        'diffusers': 'diffusers==0.33.1',
        # Keep the JAX PTX assembler within CUDA 12.8, like the base/toolchain.
        'nvidia-cuda-nvcc-cu12': 'nvidia-cuda-nvcc-cu12==12.8.93',
    }
    overrides = [x for x in overrides if re.split(r'[<>=!~\[; ]', x, maxsplit=1)[0] not in pins]
    overrides.extend(pins.values())
    replacement = 'override-dependencies = ' + json.dumps(overrides)
    text, count = re.subn(r'(?m)^override-dependencies\s*=\s*\[[^\]]*\]', replacement, text, count=1)
    assert count == 1
    # Explicit index routing prevents a PyPI/cu126 torch from replacing cu128.
    sources = '\n'.join(f'{p} = {{ index = "pytorch-cu128" }}' for p in ['torch', 'torchvision', 'torchaudio']) + '\n'
    text = text.replace('[tool.uv.sources]\n', '[tool.uv.sources]\n' + sources, 1)
    text += '\n[[tool.uv.index]]\nname = "pytorch-cu128"\nurl = "https://download.pytorch.org/whl/cu128"\nexplicit = true\n'
    parsed = tomllib.loads(text)
    assert parsed['tool']['uv']['sources']['torch']['index'] == 'pytorch-cu128'
    path.write_text(text)
    (records / f'{name}.pyproject.adjusted.toml').write_text(text)


if __name__ == '__main__':
    patch(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
