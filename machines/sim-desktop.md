# CLAUDE.md — sim-desktop (master)

> 🔴 **This file is an index.** It is auto-loaded into every session, so its length is a tax on
> every task. **Only rules that must never be missed stay inline** — everything else moved to
> [`sim-desktop.d/`](sim-desktop.d/). When you need to add depth, add it there, not here.
>
> The canonical copy is `~/ax-cluster/machines/sim-desktop.md`; `/home/sim/CLAUDE.md` is a
> **symlink** to it — never replace it with a regular file. Structure: [`README.md`](README.md).

## About this directory

`/home/sim` is the home directory on **sim-desktop**, a personal Linux home server — **not a
software repository.** There is no build, lint, or test tooling. **Don't assume a codebase exists.**

- Host `sim-desktop`, LAN **192.168.0.57** (plus Docker bridges 172.17–19.0.1)
- Ubuntu 22.04.2 LTS (jammy) · also reachable via xrdp (3389)
- Locale `ko_KR.UTF-8` — **the user communicates in Korean; reply in Korean.**
  (These guidance files are English on purpose: only Claude reads them, and Korean costs ~2.7×
  the tokens for the same content.)

## Role in the AX cluster — this box is the **master**

The project repo is cloned **here** at `~/ax-cluster` (`PLAN.md` is the index, content in `docs/`),
with copies on BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`) and GitHub (`SimSeoWon/ax-cluster`,
**private — keep it that way**, it holds LAN addresses and firewall rules). Keep all three in sync.
The board has `main` checked out so pushing there is rejected — **`git pull` on that side instead.**
🔴 `~/AgentTest` is the predecessor clone — **reference only. Never modify or push to it.**

### Machine inventory (probed 2026-08-08)

| IP | Machine | Login | Role | Reachable from here |
|---|---|---|---|---|
| **.57** | **sim-desktop** — this box | `sim` | **Master**: orchestration, RAG index, ontology/graph, task queue, broker, project registry | — |
| **.2** | Windows + **RTX 3060**, UE5 installed<br>host `DESKTOP-HV0I6DL` | **`janus`**<br>(admin) | 🔧 **Worker-capable workshop** *and* inference endpoint #2 (14b pinned) | **`ssh janus@192.168.0.2`** ✅ passwordless · RDP 3389 · Ollama 11434 |
| **.33** | Windows 10.0.26200, **the user's main work PC**<br>host `DESKTOP-FU2GNGL` | **`user`** | Workshop — UE5 work happens here. 🔴 **Not an inference endpoint** — see below | **`ssh user@192.168.0.33`** ✅ passwordless (2026-08-08) · RDP 3389 · Ollama 11434 |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` | Inference endpoint #1 (35B pinned), stateless | `ssh sim@192.168.0.43` ✅ passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
| — | BC-250 #2 | — | 🎮 **Bazzite gaming machine — NOT an inference node.** Converting it means giving up that machine. **Never assume a 2nd board exists.** | n/a |

### `.33` — reachable now, but 🔴 **not an inference endpoint**

SSH and Ollama went up on 2026-08-08. **The account is `user`** (not `janus`, not `sim`).
That changes what the master can do there — but **it does not make `.33` a node.**

Measured the same day, with only the Windows desktop running (no UE5 open):

| | |
|---|---|
| GPU | RTX 3080, **10240 MiB** |
| In use / free | 2401 MiB / **7651 MiB** |
| Its only model | `gemma4:e4b` = **8.9 GiB** — 🔴 **does not fit its own free VRAM** |
| `qwen2.5-coder:14b` | 9.0 GB — does not fit either |
| `/api/ps` | empty — nothing resident |

Opening the UE5 editor takes more. Pinning a model here would spill Ollama onto CPU **and**
fight the user for VRAM on the machine they actually work on. The §4.4 model-switch cost is
~100 s round trip, so "load when they step away, unload when they return" thrashes.

**→ Use it for checks and remote installs only** (user's call, 2026-08-08):
`master/provision.py` marks it `resident=False` and flags it if a model *is* loaded.
Model pulls go over plain HTTP (`POST /api/pull`) — no SSH, no file access, so the
"only text crosses the wire" rule holds.

🔴 **Python is installed but shadowed.** `python` resolves to the Microsoft Store stub
(`WindowsApps\python.exe`) and prints no version; the real one is
`C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe`.
**Use `py`, or the full path** — same trap as `.2`. (git 2.53.0 is fine.)

### `.2` — the Windows worker has its own guide

🔴 **The account is `janus`, not `sim`** — `ssh sim@192.168.0.2` fails with
`Permission denied (publickey,...)`. Everything else about that box — OS, session-0 boundary
(what the master can and cannot drive there), UE5 project path, local + commercial LLMs, the
SSH PATH trap — lives in **[`win-worker-2.md`](win-worker-2.md)**, which is also copied to
`C:\Users\janus\CLAUDE.md` so sessions on that machine load it.

✅ The master's services are reachable from `.2` — 8101, 8102, 8103 all verified (2026-08-08).

### Design rules (inherited from the AgentTest 2026-07-07 architecture)

- Inference nodes **never touch files** — only text (context / code fragments / diffs) crosses the
  wire. File I/O and builds happen on whichever machine owns the files.
- Master→node calls are **stateless** (Ollama `/api/generate`, with the `context` field
  deliberately not reused).
- **Deterministic gates (tests / type checkers / linters) outrank LLM judgment** for verification.
- 🔴 **Never shard a model across BC-250 boards** — each board is an independent endpoint and the
  master load-balances *requests*. The boards have 1GbE and no PCIe slots, so tensor/pipeline
  parallelism starves on bandwidth.

## Detail documents

| What you need | File |
|---|---|
| Self-hosted services · ports · **🔴 firewall rules for the 3 auth-less AX services** | [`sim-desktop.d/services.md`](sim-desktop.d/services.md) |
| BC-250 access — SSH · **the no-TTY sudo trap** · mandatory reading before hardware work | [`sim-desktop.d/bc250-access.md`](sim-desktop.d/bc250-access.md) |
| PATH · **`pkexec` for privileged work** · Python · GPU | [`sim-desktop.d/environment.md`](sim-desktop.d/environment.md) |
| Cluster design — settled vs open | `~/ax-cluster/PLAN.md` → `docs/` |
| Working *in* the repo | `~/ax-cluster/CLAUDE.md` |

## 🔴 Work journal

Numbered work reports accumulate in `~/claude-workspace/reports/` (mirroring the BC-250's
`~/bc250-backup-staging/reports/` convention). Reports are written in Korean — the user reads them.

- **Read the reports in full at session start** — grep is not a substitute. There is an incident
  where near-miss wording was filtered out and already-recorded work got re-investigated.
- **For infra work that needs a reboot or risks losing access, write the intended commands to a
  report file *before* running them and update it *during* the work** — if the connection drops,
  the file is the only surviving record of what was attempted.
- Afterwards, also update the preceding report's "remaining" list with what got done.
