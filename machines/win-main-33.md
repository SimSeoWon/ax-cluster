# CLAUDE.md — Windows main work PC `.33`

Guidance for Claude Code sessions **on this machine**, and for the master when it drives it.
Cluster-wide rules live in [`sim-desktop.md`](sim-desktop.md); repo rules in
[`../CLAUDE.md`](../CLAUDE.md).

> 🔴 **This is the human's machine.** Everything below follows from that one fact. `.2` is a
> workshop the master may drive freely; `.33` is where the user actually works, so the master
> is a **guest** here — it checks before acting and never takes resources the user needs.
> Probed 2026-08-08.

## Identity

| | |
|---|---|
| **OS** | **Microsoft Windows 11 Pro**, build 10.0.26200.8875 |
| **Host / IP** | `DESKTOP-FU2GNGL` / **192.168.0.33** |
| **Account** | **`user`** — 🔴 *not* `janus` (that's `.2`), *not* `sim`. Both fail with `Permission denied` |
| **SSH** | `ssh user@192.168.0.33` — passwordless since 2026-08-08. Master's key is in `C:\ProgramData\ssh\administrators_authorized_keys` (admin path, same as `.2`) |
| **GPU** | **NVIDIA GeForce RTX 3080 (10 GB)**, driver 610.47 |
| **UE5** | **5.8.1** at `C:\Program Files\Epic Games\UE_5.8` — same version as `.2` |
| **UE5 project** | **`C:\Users\USER\Documents\ModularStage`** — see § Unreal projects |
| **git** | 2.53.0.windows.1 |

## 🔴 Not an inference endpoint — the VRAM does not allow it

Measured with **only the Windows desktop running** (UE5 editor not open):

| | |
|---|---|
| VRAM total / in use / free | 10240 MiB / 2401 MiB / **7651 MiB** |
| `gemma4:e4b` (its only model) | **8.95 GiB** — 🔴 does not fit the free VRAM |
| `qwen2.5-coder:14b` (the coder model) | 9.0 GB — does not fit either |
| `/api/ps` | empty — nothing resident |

Opening the editor takes more still. Pinning a model here would spill Ollama onto CPU **and**
compete with the user for VRAM on the machine they are using. The §4.4 model-switch cost is
~100 s round trip, so "load while they're away, unload when they return" thrashes.

**→ Checks and remote installs only** (user's decision, 2026-08-08). `master/provision.py`
lists this host with `resident=False` and **flags it if a model is ever loaded**. Pulls go over
plain HTTP (`POST /api/pull`) — no SSH, no file access, so *only text crosses the wire* holds.

Inference stays on **`.43`** (BC-250, 35B pinned) and **`.2`** (RTX 3060, 14b pinned).

## 🔴 Can / cannot — same session-0 boundary as `.2`

SSH lands in **session 0**, which has no desktop. The user's interactive login is a different
session. This is a Windows boundary, not a permissions one — no flag works around it.

### ✅ The master CAN do these over SSH

| | Notes |
|---|---|
| `git` in the checkout (incl. `status --porcelain`) | On PATH. **The dirty check now covers this host** — see below |
| `UnrealEditor-Cmd` — commandlets, build, `RunTests` | Headless; session 0 is fine. ⚠️ **Not yet run here** — proven on `.2`, not on `.33` |
| Read/write files, inspect state | |
| `claude`, `agy`, `node` | All present, see § LLMs |
| Ollama check / `pull` | Over HTTP, no SSH needed |

### ❌ The master CANNOT do these

| | Why |
|---|---|
| **Start the UE5 GUI editor** | Session 0 has no desktop |
| **Start / stop Unreal MCP** | Its lifetime *is* the editor's → the interactive session owns it. **Don't design a remote procedure — there isn't one** |
| Anything needing a visible window | Same boundary |

### 🔴 Extra rule that applies here and not to `.2`

**The user may be working right now.** Long GPU jobs, editor launches, branch switches, and
resets are not just technically risky — they interrupt a person. Prefer read-only probes;
for anything that writes, go through the dirty check first and let it say no.

## Unreal projects

`.uproject` files under `C:\Users\USER\Documents` (targeted search, 2026-08-08):

| Project | Path | |
|---|---|---|
| **ModularStage** | `C:\Users\USER\Documents\ModularStage` | 🔴 **the mounted project** — see below |
| Project_Alpha | `C:\Users\USER\Documents\Project_Alpha` | The predecessor; its docs survive as `_archive/project_alpha_md/` in the twin's context |
| ServerTest | `C:\Users\USER\Documents\ServerTest` | |
| ListViewTest | `C:\Users\USER\Documents\Unreal Projects\ListViewTest` | |

### 🔴 Both workshops track the same repository — the competition is real

```
.33  C:\Users\USER\Documents\ModularStage  →  origin http://192.168.0.57:3000/Sim/ModularStage.git
.2   E:\trunk\ModularStage                 →  same origin
```

`.33` was on `main` at `bc4b38f` when probed. **This is the measured basis for §4.2's premise**
that two workshops contend for the same `task/<id>` branches and the same task queue —
so claim / lease / fencing are a **correctness requirement**, not an optimization.

### The workshop registry entry was stale — fixed 2026-08-08

It read `driven: interactive` with the note *"SSH 없음(RDP 뿐)"* and carried no path. Now:

```yaml
192.168.0.33:
  driven: ssh
  user: user
  path: C:\Users\USER\Documents\ModularStage
```

**Consequence: the dirty check reaches this machine.** First run found one uncommitted change —
`Content/Blueprints/BP_MissionPrefab_C_0/BP_MissionPrefab_C_0.uasset`, i.e. the user's own
in-progress work — and correctly refused to dispatch. That is the behaviour we want here.

## LLMs available on this machine

### Local — Ollama `:11434`

| Model | Size | Quant | Params |
|---|---|---|---|
| `gemma4:e4b` | 8.95 GiB | Q4_K_M | 8.0B |

**One model, and it does not fit the free VRAM** (see above). Nothing is pinned and nothing
should be. Reachable from the master; used for **checks and installs only**.

### Commercial CLIs

| | Status | Notes |
|---|---|---|
| **Claude Code** | ✅ **2.1.226** | `C:\Users\USER\.local\bin\claude.exe` |
| **`agy` (Antigravity)** | ✅ **1.0.16** | `C:\Users\USER\AppData\Local\agy\bin\agy.EXE`. ⚠️ **Older than the master's 1.1.10** — the Windows-era pitfalls (PTY, ANSI, argv order) that 1.1.10 fixed on Linux are **not verified fixed here**. Don't assume the master's experience transfers |
| `node` | ✅ | `C:\Program Files\nodejs\node.exe` |
| `bun` | ❌ not installed | Same gap as `.2`; prerequisite for PLAN §9 (gajae-code) |

🔴 **Never let `agy` run autonomously in a working directory here.** It uses
`--dangerously-skip-permissions`; AgentTest recorded it editing files without consent. Text in,
text out only — and on *this* machine those would be the user's files.

## 🔴 The Python PATH trap — same shape as `.2`, different cause

```
where python
  C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python.exe        ← Store stub, wins
  C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe    ← the real one

py -0p
  -V:3.12 *   C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe
```

`python --version` prints **`Python`** with no version — the stub swallows it. That output looks
like a truncated answer rather than a failure, which is exactly how it misleads.

**Use `py`, or the full path.** Never bare `python` in anything the master runs here.

## When something here changes

This file is a **copy**, like `win-worker-2.md` — `ax-cluster` is not cloned on this machine, so
there is nothing for a symlink to point at. Refresh it deliberately after measuring; see
[`README.md`](README.md) for the reasoning and the copy procedure.
