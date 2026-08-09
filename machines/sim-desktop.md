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

## 🔴 Where the project stands — read this before planning

**Milestone 1 (infrastructure) is closed. Milestone 2 (digital twin restoration) is open.**

| | |
|---|---|
| Current milestone — **read only this one** | `~/ax-cluster/docs/milestones/2-twin-restoration.md` |
| Previous (kept, still valid) | `~/ax-cluster/docs/milestones/1-infrastructure.md` |

**Goals** (user, 2026-08-08): ① **author the ontology documents automatically** — context doc per
commit → relation graph → BM25 → then the ontology doc itself, which is **manual + conversational
with heuristics, not fully automatic** (auto-promotion was permanently disabled 2026-06-01)
② **feed the relevant slice of that twin to the code-writing agent.**

🔴 **24 of 43 sub-tasks done (2026-08-09).** The twin now **grows, is indexed, and reaches code
generation** — goal ② ran end to end for the first time. Relation graphs, context-MD synthesis and
**ontology LLM re-synthesis** are wired; the 247 domain yaml are **indexed** (separate DB +
collection, triple noise gate); manifests carry **domain norms**.
The **worker runner** dispatches from the queue into a worker's Claude and submits the result
(중 2.5, **4/5** — e2e measured 71s), and the master **cleans up worker debris**
(`master.work.cleanup`) — 🔴 workers may not delete branches, and a branch is removed only when
its tip is reachable from `origin/main`. Workers return to **`main`** when done, otherwise the
branch they sit on can never be cleaned. Still missing: **decomposition + skeleton generation**
(§4.5's empty first step), **requester `.33` wiring**, and **thesaurus alias data (0 registered)** — measured cause: the tags channel
(weight 3.0) has **zero Korean**, so Korean queries miss the highest-weight channel entirely.
Breakdown 대 2 / 중 9 / 소 43; **main = 대 1**.

🔴 **Never size a task by line count** — `class_graph`'s 1,341 lines are *"delete the file → full
rescan on restart"*, while one 829-line file holds the domain index, norm search and the thesaurus
builder together.

🔴 **Say "done" only for a whole area**; otherwise give the denominator. And **don't pick the
next task yourself** — milestone 1 failed exactly that way.

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
| **.2** | Windows + **RTX 3060**, UE5 installed<br>host `DESKTOP-HV0I6DL` | **`janus`**<br>(admin) | 🔧 **Worker** *and* inference endpoint #2 (14b pinned). 🔴 **The only machine that can run the layer-3 verdict unattended** (UE5 5.8) | **`ssh janus@192.168.0.2`** ✅ passwordless · RDP 3389 · Ollama 11434 |
| **.33** | Windows 10.0.26200, **the user's main work PC**<br>host `DESKTOP-FU2GNGL` | **`user`** | 🔴 **`requester`, not a worker** — registers work, verifies (it has UE5), gives feedback. **Never dispatched to** (`drivable_hosts` excludes it). Not an inference endpoint | **`ssh user@192.168.0.33`** ✅ passwordless (2026-08-08) · RDP 3389 · Ollama 11434 |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` | 🔧 **Worker** *and* inference endpoint #1 (35B pinned). Has the project clone at `~/trunk/ModularStage` since 2026-08-09 — **no longer stateless** | `ssh sim@192.168.0.43` ✅ passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
| — | BC-250 #2 | — | 🎮 **Bazzite gaming machine — NOT an inference node.** Converting it means giving up that machine. **Never assume a 2nd board exists.** | n/a |

### `.33` — the main work PC has its own guide

SSH and Ollama came up 2026-08-08; **the account is `user`**. But 🔴 **it is not an inference
endpoint** — measured free VRAM **7651 MiB** is smaller than its own only model (8.95 GiB) and
than the coder model (9.0 GB), and opening UE5 takes more (`resident=False`).

🔴 **Its role is `requester`** (2026-08-09): it registers work, verifies (UE5 is here, so compile
errors surface fastest), and writes `[FEEDBACK]` blocks. It is **excluded from `drivable_hosts`** —
never dispatched to. ⚠️ When it verifies, use **`git worktree`**, never a branch switch in the
human's main tree: uncommitted `.uasset` work cannot be recovered.

🔴 **This is the human's machine** — the master is a guest here: read-only by preference, dirty
check before anything that writes. Everything else — session-0 boundary, UE5 checkout path,
the Store-stub Python trap, local + commercial LLMs — lives in
**[`win-main-33.md`](win-main-33.md)**.

### `.2` — the Windows worker has its own guide

🔴 **The account is `janus`, not `sim`** — `ssh sim@192.168.0.2` fails with
`Permission denied (publickey,...)`. Everything else about that box — OS, session-0 boundary
(what the master can and cannot drive there), UE5 project path, local + commercial LLMs, the
SSH PATH trap — lives in **[`win-worker-2.md`](win-worker-2.md)**, which is also copied to
`C:\Users\janus\CLAUDE.md` so sessions on that machine load it.

✅ The master's services are reachable from `.2` — 8101, 8102, 8103 all verified (2026-08-08).

### Roles — `driven` (can we reach it) ≠ `role` (may we dispatch to it)

    worker      claims from the queue and implements   .2 · .43
    requester   registers, verifies, gives feedback    .33  🔴 never dispatched to

**Every worker holds the project clone and judges from source** — that is the point, and all
workers are equal in it. UE5 only decides *who can run the layer-3 verdict*. The per-machine
`<checkout>/.ax/config.json` is the single source of truth for paths/capabilities; it is
**generated by the master** (`python -m master.client deliver`), never hand-copied — a worker's
config was once found pointing at *another machine's* path.
→ [`../docs/8-git-authority.md`](../docs/8-git-authority.md) §8.4

### Design rules (inherited from the AgentTest 2026-07-07 architecture)

- **Ollama inference calls** are text-only — context/code fragments/diffs cross the wire, never
  files. ⚠️ That is about the **model**, not the machine: `.43` now also runs a worker agent that
  *does* read its own clone. The two roles coexist on one box.
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
| Windows main work PC `.33` — **guest rules**, UE5 path, Python trap | [`win-main-33.md`](win-main-33.md) |
| PATH · **`pkexec` for privileged work** · Python · GPU | [`sim-desktop.d/environment.md`](sim-desktop.d/environment.md) |
| **🔴 Which LLM is good at what · where hallucination was measured** | [`llm-fitness.md`](llm-fitness.md) |
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
- 🔴 **Reports are not the task list.** Work items live in **Redmine** (`:8080`, project
  `ModularStage` — the AX cluster is *the same project*, never make a new one) and progress lives
  in the open milestone doc. Three places, three jobs — see `~/ax-cluster/CLAUDE.md` § Work flow.
