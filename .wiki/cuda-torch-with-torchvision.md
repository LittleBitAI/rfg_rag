---
scope: project
severity: landmine
repeat: rule
triggers: ['(?i)torch', '(?i)cuda', '(?i)cu12', '(?i)easyocr', '(?i)\bgpu\b', '(?i)\bcpu\b', '설치', '(?i)pip install', '(?i)requirements', '임베딩.*느', '(?i)no kernel image']
slots: []
sources: ['commit e8656ad', 'README.md#L87', 'requirements.txt#L4']
links: []
---

# Install torch and torchvision together from the CUDA 12.8 index before requirements.txt

Rule. In a new `.venv`, run
`python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`
first, then `pip install -r requirements.txt`, then confirm
`torch.cuda.is_available()` is `True`. Install torchvision in the same command
as torch, never torch alone. RTX 50 (sm_120) needs cu128 or newer. On macOS
install plain torch instead. Do not change `requirements.txt` in a way that
lets pip pick torch or torchvision from PyPI.

Why. `easyocr` requires torchvision. With only torch from the cu128 index,
pip pulled torchvision from PyPI; that wheel pinned a newer torch, so the
CUDA torch was replaced by a CPU build and embedding ran on the CPU
(commit e8656ad). cu124 and older fail with `no kernel image` on Blackwell.

What goes wrong. Index building and the frontend's startup silently fall
back to CPU and take hours instead of minutes; `Embedder` only picks `cuda`
when torch reports it (`rag/retrieval/indexing.py:31`).
