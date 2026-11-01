---
scope: project
severity: landmine
repeat: rule
triggers: ['(?i)langchain-community', '(?i)langchain-hwp', '(?i)hwp-hwpx', '(?i)ragas', '(?i)requirements', '업그레이드', '(?i)upgrade', '버전.*(올|바꾸|고정)', '(?i)\bpin']
slots: []
sources: ['https://github.com/LittleBitAI/rfg_rag/pull/59', 'commit 535ccbd', 'requirements.txt#L14', 'requirements.txt#L34']
links: []
---

# Keep the pinned parser and evaluation versions unless the reason in requirements.txt is gone

Rule. Do not raise these pins without re-checking the reason written beside
them in `requirements.txt`: `langchain-hwp-hwpx-loader>=0.1.1,<0.2`,
`langchain-community==0.3.31`, `ragas==0.4.3`, `kiwipiepy==0.24.0`. A version
change to any of them needs a check of the path it guards: HWP image
extraction for the loader, RAGAS imports for community, the BM25 index for
Kiwi. Keep the runtime patches in `rag/preprocessing/parsing.py` for the
PyMuPDF image skip and the `hwp-hwpx-parser` hyperlink hang while the pinned
versions still have those bugs.

Why. From 0.2 the HWP loader saves images as `<subfolder>/image_0000.png`
instead of the BinData names the `[IMAGE: BIN0003.bmp]` markers carry, so OCR
labelling found no HWP image at all: 503 HWP positions became 0 (commit
535ccbd, PR #59). `ragas 0.4.3` imports a module that community 0.4 removed.
Kiwi's version is part of the BM25 tokenizer fingerprint, so changing it
refuses the saved index.

What goes wrong. An upgrade passes install, then images, judges or search
quietly break or stop.
