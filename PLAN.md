# AX Cluster — plan (index)

**Goal (AX, AI Transformation):** fundamentally raise AI usage across an entire Unreal Engine 5
game production pipeline — beyond coding assistance, unifying an ontology-based digital twin,
Unreal MCP (UE 5.8.1+), and code-writing agents into one pipeline.

**Started:** 2026-08-05 · **Split into sections:** 2026-08-08 (one 1,839-line file → 13 in `docs/`)

> 🔴 **This file is an index. The content lives in `docs/`.**
> **Section numbers are unchanged by the split** — cross-references like `§5.5.3-④` in other
> documents and commit messages remain valid.
> Edit the file under `docs/`, and add a row here when you add a section.
>
> The section documents are in Korean (they are the user's original prose, moved verbatim — not
> retranslated, to avoid drift in hard-won decisions). This index and the `CLAUDE.md` guidance
> files are English: only Claude reads those, and Korean costs ~2.7× the tokens.

---

## Contents

| § | Document | What you get from it | What it settled |
|---|---|---|---|
| 1 | [Background](docs/1-background.md) | What carries over from earlier projects; BC-250 infra status | ROCm impossible on GFX1013 → Ollama Vulkan backend instead |
| 2 | [Architecture](docs/2-architecture.md) | Role split and topology across master, 2 Windows workshops, BC-250 | Files stay on Windows; master is context infrastructure; BC-250 is an inference node |
| 3 | [Open items](docs/3-open-items.md) | Settled vs still-open status — **start here before working** | Inference requests go through the master broker |
| 4 | [Work loop](docs/4-work-loop.md) | The path one task travels, and the hallucination-verification pipeline | 3 verification layers — L1 self-check / L2 syntax+API / L3 UE5 build |
| 5 | [Master orchestration](docs/5-master-orchestration.md) | Language choice, what to port and in what order, systemd execution model | Python, plus a systemd+venv execution model |
| 5.5 | [Project isolation](docs/5_5-project-isolation.md) | Multi-project directory layout and the mount contract | Many directories, **one mount** — mismatched requests get 409, fail-closed |
| 6 | [Node failover](docs/6-node-failover.md) | Liveness detection and remote power recovery | Streaming chunk gap *is* the heartbeat (no separate comms infra) |
| 7 | [Master GPU](docs/7-master-gpu.md) | Whether to add a GTX 1070 Ti for RAG/CUDA | **Open** — confirming the PSU's PCIe aux connector comes first |
| 8 | [git authority](docs/8-git-authority.md) | The permission boundary between human sessions and the pipeline | Humans: no destructive git. Pipeline: autonomous on `task/` branches only |
| 9 | [gajae-code (gjc)](docs/9-gajae-code.md) | Where `gjc` runs, and why 14b blocked it | `gjc` runs on Windows; L2 gets a fail-closed VERDICT contract |
| 9.5 | [task_queue port](docs/9_5-task-queue.md) | Port stage 1 and service registration | Ported, `ax-task-queue` live, 8101 LAN-only |
| — | [Settled decisions](docs/settled-decisions.md) | Closed calls, gathered in one place | Don't relitigate without new measurements |
| 10 | [References](docs/10-references.md) | Original design, reports, external repos | — |

---

## Currently running (2026-08-08)

| Service | Port | Unit | Defence |
|---|---|---|---|
| task_queue | 8101 | `ax-task-queue.service` | 🔴 no auth — ufw LAN-only is all there is |
| Inference broker | 8102 | `ax-broker.service` | 🔴 no auth — ufw LAN-only is all there is |
| Project registry (MCP) | 8103 | `ax-projects.service` | 🔴 no auth — ufw LAN-only is all there is |

**Two inference endpoints:** BC-250 #1 (35B pinned) and the RTX 3060 Windows PC (14b pinned).
**Never widen any of these to `Anywhere`** — none of the three services has an auth layer.

Per-machine operating guides: [`machines/`](machines/README.md). Session work reports:
`~/claude-workspace/reports/` and `sim@192.168.0.43:~/bc250-backup-staging/reports/`.
