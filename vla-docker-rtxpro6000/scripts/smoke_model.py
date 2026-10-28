"""Dependency/import and GPU-kernel checks; does not claim full model validation."""
import argparse
from importlib.metadata import version
import importlib
import json

p = argparse.ArgumentParser()
p.add_argument('--cpu', action='store_true')
p.add_argument('--jax', action='store_true')
p.add_argument('--project', choices=['pi05', 'ftp1'], required=True)
args = p.parse_args()
expected = {'torch': '2.7.1', 'torchvision': '0.22.1', 'numpy': '1.26.4', 'transformers': '4.53.2', 'jax': '0.5.3'}
for package, wanted in expected.items():
    got = version(package)
    if got.split('+')[0] != wanted:
        raise RuntimeError(f'{package}: got {got}, wanted {wanted}')
import numpy as np
import torch
import torchvision
import torchcodec
import cv2
import openpi
from openpi.models import pi0_config
from openpi.models_pytorch import pi0_pytorch
from openpi.training import config
if args.project == 'pi05':
    assert config.get_config('pi05_droid').model.pi05
if args.project == 'ftp1':
    # The officially documented standalone inference entry point.
    from openpi.policies import FTP1InferenceWrapper
    assert FTP1InferenceWrapper
report = {'project': args.project, 'openpi_path': list(openpi.__path__), 'packages': {k: version(k) for k in expected}}
if not args.cpu:
    assert torch.cuda.is_available(), 'CUDA unavailable; check host driver/GPU assignment'
    assert torch.version.cuda == '12.8', f'Unexpected CUDA runtime {torch.version.cuda}'
    report['gpu'] = torch.cuda.get_device_name(0)
    report['capability'] = torch.cuda.get_device_capability(0)
    a = torch.ones((256, 256), device='cuda')
    out = a @ a
    assert torch.all(out == 256).item()
    torch.cuda.synchronize()
    boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 9., 9.]], device='cuda')
    scores = torch.tensor([0.9, 0.8], device='cuda')
    assert torchvision.ops.nms(boxes, scores, 0.5).tolist() == [0]
if args.jax:
    import jax
    import jax.numpy as jnp
    devices = jax.devices('gpu')  # Explicit: never silently report a CPU fallback as success.
    with jax.default_device(devices[0]):
        result = jax.jit(lambda x: x @ x)(jnp.ones((64, 64)))
        result.block_until_ready()
        assert np.all(np.asarray(result) == 64)
    report['jax_devices'] = [str(x) for x in devices]
print(json.dumps(report, indent=2))
