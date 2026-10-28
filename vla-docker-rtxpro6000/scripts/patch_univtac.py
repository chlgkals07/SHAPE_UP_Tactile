"""Explicit experimental CUDA 12.8 migration of the pinned isaac51 installer.

No upstream model or simulator algorithms are changed. GPU validation remains
mandatory: successful dependency installation is not a benchmark result.
"""
import difflib
from pathlib import Path
import sys


def patch(root: Path, records: Path):
    records.mkdir(parents=True, exist_ok=True)
    stamp = root / '.vla-blackwell-patched'
    if stamp.exists():
        print('UniVTAC Blackwell patch already applied')
        return
    edits = {}
    install = root / 'scripts/install.sh'
    original = install.read_text()
    # Match real upstream facts rather than trying to patch an unknown release.
    for token in ['"torch==2.7.0"', '"torchvision==0.22.0"', 'release 12\\.6', 'pkgs/main']:
        if token not in original:
            raise ValueError(f'Unexpected upstream installer: missing {token}')
    changed = original.replace('12.6', '12.8').replace(r'12\.6', r'12\.8')
    changed = changed.replace('cu126', 'cu128').replace('2.7.0', '2.7.1').replace('0.22.0', '0.22.1')
    changed = changed.replace('--channel https://repo.anaconda.com/pkgs/main', '--channel conda-forge')
    # Wheel distribution metadata includes +cu128; compare public versions.
    changed = changed.replace('ok = installed == wanted', 'ok = installed.split("+")[0] == wanted')
    if '"${PIP[@]}" install pybind11' not in changed:
        raise ValueError('Unexpected UIPC prerequisites line')
    changed = changed.replace('install pybind11 mypy', 'install "pybind11==2.13.6" mypy')
    edits[install] = (original, changed)
    core = root / 'third_party/TacEx/source/tacex/setup.py'
    original = core.read_text()
    if 'torch_scatter-2.1.2%2Bpt27cu126' not in original:
        raise ValueError('Unexpected vendored TacEx torch-scatter requirement')
    changed = original.replace('cu126', 'cu128')
    # The PyG wheel family uses torch-2.7.0 for all 2.7.x patches; keep that URL.
    edits[core] = (original, changed)
    yaml = root / 'third_party/TacEx/source/tacex_uipc/libuipc/conda/env.yaml'
    original = yaml.read_text()
    changed = original.replace('  - https://repo.anaconda.com/pkgs/main\n', '')
    changed = changed.replace('cuda-toolkit=12.6', 'cuda-toolkit=12.8')
    if changed == original:
        raise ValueError('Expected CUDA toolkit pin in UIPC environment')
    edits[yaml] = (original, changed)
    report = []
    for path, (before, after) in edits.items():
        if before == after:
            raise ValueError(f'No edits applied to {path}')
        report.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                         fromfile=str(path.relative_to(root)), tofile=str(path.relative_to(root))))
        path.write_text(after)
    (records / 'univtac-blackwell.patch').write_text(''.join(report))
    stamp.write_text('experimental CUDA 12.8 / torch 2.7.1+cu128 / sm_120\n')


if __name__ == '__main__':
    patch(Path(sys.argv[1]), Path(sys.argv[2]))
