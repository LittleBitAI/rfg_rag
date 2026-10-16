---
scope: project
severity: preference
triggers: []
domain: ''
title: "Installation guide: Install torch and torchvision together from the CUDA repository"
pr: 50
merged: 2026-10-16
branch: "feature/install-torchvision-cuda"
---

# Installation guide: Install torch and torchvision together from the CUDA repository

What. Changed the first step of the installation guide (README · requirements.txt comments) from `pip install torch` to `pip install torch torchvision`. Both are installed from the cu128 repository. The code and dependency list remain unchanged.

Why. Embedding (creating an index) took over 9 hours on a team member's PC. Upon checking, `.venv`'s torch was `2.14.1+cpu`, and `torch.cuda.is_available()` was `False`. Since `Embedder` runs on CPU without warning if CUDA is missing, it took that long to embed about 19,000 chunks with KURE-v1 on the CPU. The cause is the installation order. `requirements.txt`'s `easyocr==1.7.2` (for CRAFT image selection) requires `torchvision>=0.5`. If you install only torch with cu128 first as instructed, then subsequently `pip install -r requirements. …

Source. PR #50 · `feature/install-torchvision-cuda`
