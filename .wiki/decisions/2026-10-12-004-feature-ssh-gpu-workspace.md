---
scope: project
severity: preference
triggers: []
domain: ''
title: "Add instructions for working with VS Code Remote-SSH on the team VM codeit"
pr: 4
merged: 2026-10-12
branch: "feature/ssh-gpu-workspace"
---

# Add instructions for working with VS Code Remote-SSH on the team VM codeit

What. `README.md`: Add `codeit` usage instructions in Korean — `Host codeit` SSH section, selecting a host in VS Code Remote-SSH, Linux venv + cu128 torch installation, copy `.env` and `data/` once (since it is a shared VM, `chmod 600 .env`), `artifacts/` separately for each device. I also added Linux gate commands to the development rules block. - `CLAUDE.md` = `AGENTS. …

Why. The team VM `codeit` (NVIDIA L4) was running an old BidMate deployment. Now, we place the newly received rfg_rag on this VM, and team members connect via VS Code Remote-SSH to run embeddings on the VM's GPU without changing the code.

Source. PR #4 · `feature/ssh-gpu-workspace`
