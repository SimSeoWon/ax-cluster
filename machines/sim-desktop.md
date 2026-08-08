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
| **.33** | Windows, **the user's main work PC** | — | Workshop — UE5 work happens here | RDP 3389 only. **No SSH, no Ollama** — the master cannot drive it remotely |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` | Inference endpoint #1 (35B pinned), stateless | `ssh sim@192.168.0.43` ✅ passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
| — | BC-250 #2 | — | 🎮 **Bazzite gaming machine — NOT an inference node.** Converting it means giving up that machine. **Never assume a 2nd board exists.** | n/a |

### `.2` — SSH access notes (verified 2026-08-08)

🔴 **The account is `janus`, not `sim`.** `ssh sim@192.168.0.2` fails with
`Permission denied (publickey,...)` — an easy 10 minutes to lose. The master's public key is in
`C:\ProgramData\ssh\administrators_authorized_keys` (the admin-account path, not `~/.ssh/`).

🔴 **The SSH session's PATH is minimal — installed tools are invisible to `where`.**
`claude`, `node`, and `npm` are all installed but resolve only by absolute path over SSH:

```bash
ssh janus@192.168.0.2 'C:\Users\janus\.local\bin\claude.exe --version'   # Claude Code 2.1.225
```

`git` *is* on PATH (`C:\Program Files\Git\cmd\git.exe`). Same trap as this box's `~/.local/bin`
needing an explicit `.bashrc` entry — a tool missing from `where` output is not absent.

✅ **The master's services are reachable from `.2`** — 8101, 8102, and 8103 all test open
(`Test-NetConnection`, 2026-08-08). A Claude Code session there can talk to the task queue,
broker, and project registry directly.

**The two Windows PCs work on the SAME UE5 project** — they own files, run the engine, do
build/RunTests, and register code. That is why claim/lease/fencing is a correctness requirement,
not team bloat.

🔴 **`.2` is the asymmetric one — it is both a workshop and an inference endpoint.** It is also
the only Windows box the master can reach non-interactively (SSH). `.33` is RDP-only, so anything
needing automation on the main work PC has to be driven from that PC, not from here.

🔴 **Two inference endpoints, and only one is a board:** BC-250 #1 (35B pinned) and the RTX 3060
PC (14b pinned). Each runs `MAX_LOADED_MODELS=1`, so a model swap costs ~64s (35B) / ~36s (14b) —
a round trip is ~100s. **Any design premised on parallel inference or multiple resident models
*within one endpoint* does not hold.**

🔴 **Claude Code is installed on `.2`.** It is an *orchestrator* there (§2.3 — the workshop owns
files and drives tools), **not** a model backend. Ollama cannot serve Claude, and the Claude Code
CLI is not an inference server — don't try to put it behind the broker as a model.

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
