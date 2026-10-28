# Reviewed sources

Reviewed: 2026-10-25. Installation defaults were compared to the files below;
this is not a claim that upstream has validated the combined image.

## Exact source revisions

- OpenPI: https://github.com/Physical-Intelligence/openpi/tree/215abfb217dbac7d5f1273282331b9b1866c0479
- FTP-1: https://github.com/michaelyuancb/ftp1-policy/tree/89fa681d6c014cce28300946b7526db808e0b1c1
- UniVTAC isaac51: https://github.com/univtac/UniVTAC/tree/d541e5568227ca3b66104d294f63c80acad7c52c

Review focused on pyproject.toml, upstream lock metadata, README, workspace-client
metadata, UniVTAC scripts/install.sh, docs/Installation.md, and vendored
TacEx/libuipc installer/toolchain metadata. All source downloads in the Docker
build use the exact revision in config/repos.json and recursive submodules.

## Hardware and binary choices

- GPU compute capability: https://developer.nvidia.com/cuda/gpus
- CUDA 12.8 compiler support for SM_120: https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html
- PyTorch 2.7.1 / torchvision 0.22.1 cu128 pairing: https://pytorch.org/get-started/previous-versions/
- TorchCodec compatibility: https://github.com/meta-pytorch/torchcodec#installing-torchcodec
- PyG torch-scatter cp311/pt27cu128 wheel index: https://data.pyg.org/whl/torch-2.7.0+cu128.html
- Isaac Sim 5.1 requirements: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html
- Miniforge installer release: https://github.com/conda-forge/miniforge/releases/tag/25.3.1-0

## Version adjustment decisions

- Separate pi05 and ftp1 environments because both distributions install `openpi`.
- Keep their upstream torch 2.7.1, Transformers 4.53.2, JAX 0.5.3, Flax 0.10.2.
- Route torch/vision/audio to explicit cu128 index. Pin NumPy 1.26.4 and the
  OpenCV 4.11 generation to avoid NumPy 2 ABI/dependency drift.
- Keep a matched TorchCodec 0.4.0, hub 0.32.3, diffusers 0.33.1 baseline.
- Apply each repository's own Transformers patch to its own environment.
- Preserve UniVTAC's vendored TacEx/libuipc and pinned cuRobo/vcpkg sources;
  change CUDA toolchain/runtime/binary-extension choices consistently to 12.8.
- Treat UniVTAC's source-build migration as experimental until compiled and
  tested on the assigned GPU. Do not silently ignore build failures.
- Keep FTP-1's bundled Isaac Sim 4.5 evaluation workflow distinct from the
  standalone UniVTAC isaac51 branch; no claim of automatic policy adaptation.

Upstream test fixtures in tests/fixtures are metadata/installer excerpts from
the exact reviewed projects, retained for CPU-only patch regression checks.
Their upstream project licenses continue to apply. The Docker build fetches
the original repositories with their license files; it does not redistribute
model weights or datasets here.
