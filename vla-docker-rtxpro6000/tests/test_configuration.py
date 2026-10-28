"""CPU-only integration checks against reviewed, real upstream manifests.

Run: python -m unittest discover -s tests -v
These checks do not substitute for a Docker build or GPU evaluation.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class ConfigurationTests(unittest.TestCase):
    def test_real_model_manifests_have_separate_install_destinations(self):
        patcher = module('patch_model')
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            for name in ['pi05', 'ftp1']:
                repo = temp / name
                repo.mkdir()
                shutil.copy(FIXTURES / f'{name}.toml', repo / 'pyproject.toml')
                patcher.patch(repo, name, temp / 'records')
                conf = tomllib.loads((repo / 'pyproject.toml').read_text())
                self.assertEqual(conf['project']['requires-python'], '==3.11.*')
                self.assertEqual(conf['tool']['uv']['sources']['torch']['index'], 'pytorch-cu128')
                deps = conf['project']['dependencies']
                self.assertIn('opencv-python-headless==4.11.0.86', deps)
                self.assertFalse(any(x.startswith('opencv-python>') for x in deps))
                self.assertIn('numpy==1.26.4', conf['tool']['uv']['override-dependencies'])
                self.assertIn('torchcodec==0.4.0', conf['tool']['uv']['override-dependencies'])
                self.assertTrue((temp / 'records' / f'{name}.pyproject.upstream.toml').is_file())
            # This is the actual upstream collision that requires separate envs.
            for name in ['pi05', 'ftp1']:
                self.assertEqual(tomllib.loads((temp / name / 'pyproject.toml').read_text())['project']['name'], 'openpi')

    def test_changed_upstream_cannot_be_silently_patched(self):
        patcher = module('patch_model')
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            text = (FIXTURES / 'pi05.toml').read_text().replace('torch==2.7.1', 'torch==2.8.0')
            (repo / 'pyproject.toml').write_text(text)
            with self.assertRaises(ValueError):
                patcher.patch(repo, 'pi05', repo / 'records')

    def test_blackwell_patch_covers_toolchain_runtime_and_binary_extension(self):
        patcher = module('patch_univtac')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = {
                'uni-install.sh': 'scripts/install.sh',
                'uni-tacex-setup.py': 'third_party/TacEx/source/tacex/setup.py',
                'uni-toolchain.yaml': 'third_party/TacEx/source/tacex_uipc/libuipc/conda/env.yaml',
            }
            for src, dest in mapping.items():
                path = root / dest
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(FIXTURES / src, path)
            patcher.patch(root, root / 'records')
            install = (root / 'scripts/install.sh').read_text()
            self.assertNotIn('12.6', install)
            self.assertNotIn(r'12\.6', install)
            self.assertNotIn('cu126', install)
            self.assertIn('release 12\\.8', install)
            self.assertIn('"torch==2.7.1"', install)
            self.assertIn('"torchvision==0.22.1"', install)
            self.assertIn('installed.split("+")[0]', install)
            subprocess.run(['bash', '-n', str(root / 'scripts/install.sh')], check=True)
            setup = (root / mapping['uni-tacex-setup.py']).read_text()
            self.assertIn('torch-2.7.0%2Bcu128/torch_scatter-2.1.2%2Bpt27cu128-cp311', setup)
            yaml = (root / mapping['uni-toolchain.yaml']).read_text()
            self.assertIn('cuda-toolkit=12.8', yaml)
            self.assertNotIn('pkgs/main', yaml)
            patcher.patch(root, root / 'records')  # Safe retry after an install failure.

    def test_build_targets_preserve_priority(self):
        text = (ROOT / 'Dockerfile').read_text()
        self.assertIn('FROM sources AS pi05', text)
        self.assertIn('FROM pi05 AS models', text)
        self.assertIn('FROM models AS full', text)
        self.assertIn('FROM models AS default', text)
        for name, spec in json.loads((ROOT / 'config/repos.json').read_text()).items():
            self.assertRegex(spec['ref'], r'^[0-9a-f]{40}$')


if __name__ == '__main__':
    unittest.main()
