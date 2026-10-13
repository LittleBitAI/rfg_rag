#!/usr/bin/env bash
# GCP VM(Ubuntu · NVIDIA L4)에서 .venv 를 만들고 패키지를 설치한다.  저장소 최상위에서: bash setup_vm.sh
set -euo pipefail
cd "$(dirname "$0")"

# 권장 이미지(ubuntu-accelerator-2204-amd64-with-nvidia-550)의 드라이버 550 은 CUDA 12.4 까지 지원한다.
# PyPI 기본 torch 는 CUDA 13 빌드라 드라이버 580 이상이 필요 → 이 VM 에서는 GPU 를 못 쓴다. 그래서 cu126 빌드를 먼저 설치한다.
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

if [ ! -x .venv/bin/python ]; then
  # 우분투 기본 python3 에는 venv 에 필요한 ensurepip 가 빠져 있다
  python3 -c "import ensurepip" 2>/dev/null || { sudo apt-get update && sudo apt-get install -y python3-venv; }
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install "torch>=2.7" --index-url https://download.pytorch.org/whl/cu126
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python -c "import torch; assert torch.cuda.is_available(), 'torch 가 GPU 를 찾지 못했습니다'; print('torch', torch.__version__, '·', torch.cuda.get_device_name(0))"
mkdir -p data
