# CLAUDE.md — sim-desktop (master)

> [중요] **This file is an index.** It is auto-loaded into every session, so its length is a tax on
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

## Where the project stands — read this before planning

**M1–M5 all closed (M3·M4·M5 closed 2026-08-17, user decisions). M6 (개선·확장)
is open — numbers live in Redmine (version *마일스톤 6*). A separate dateless bucket
*아이디어 — 추후 검토 수집* holds not-yet-decided ideas (wiki [[아이디어수집]]) — items there
are NOT work.**

| | |
|---|---|
| Current milestone — **read only this one** | `~/ax-cluster/docs/milestones/6-improvements.md` |
| Closed, kept as reference | `5-version-reconcile.md` (「여기서 배운 것」 — 전제가 죽은 선택 · 허위 인용 · 중앙화의 새 좌표) · `4-origin-reconciliation.md` (왕복이 계약 · 원전 기본값 · census 한계) · `3-work-pipeline.md` (gates/grounding 실측) · `2-twin-restoration.md` · `1-infrastructure.md` |

> [주의] **Below are the traps that still bind, not the closed milestones' records.** Progress and
> counts live in Redmine; the narrative (census numbers, M2/M3/M4 scope and timings, the ported web
> UI's feature list) lives in the closed milestone docs listed above — this file does not repeat them.

[중요] **"one writer" was never my invention; that writer is the server, and workers push ephemeral
`attempt/` branches** (the origin's `cluster_coordinator.py` said *"durable 단일 writer 보존"* while
our repo cited it 0 times — report 14). This project is an **OS/environment port** (Windows+UE5
daemon → Linux+Gitea) and Linux forces exactly **one** change: the UE5 build step *inside*
`verify_and_merge` moves to `.2`. Not even Gitea was forced — the origin's doc listed GitHub/Gitea/
bare as a choice. **소 1.1 (read the origin's design docs) is upstream of everything.**

[중요] **Workers may not delete branches** — a branch is removed only when its tip is reachable from
`origin/main`, and workers return to **`main`**.

The pipeline (M3, four deterministic gates — detail in `3-work-pipeline.md`):

    요청 → 골조(claude:opus, 등재 전 빌드) → 분해 → 워커는 **추론만**(ax-infer) → 스풀
         → 통합자 `.2`: 층1 → 층2 → 적용 → **조각별 UE5 빌드** → 통과분만 커밋 → work 단위 RunTests

The status screen and the ported web UI are served on the LAN at `http://192.168.0.57:8103` —
[중요] **no login** (API paths on that port stay token-locked), and its palette is **dark-only on
purpose** (one screen flipping to light on its own reads as a different app). `/cluster` serves the
**last generated** hardware snapshot — a browser refresh never triggers SSH polling (that would
defeat the 120s guard). [중요] **`ax-status.timer` refreshes it every 5 min**; because 5 min < the
15-min staleness threshold, **the red age banner appearing means the timer is actually broken.**

[중요] **The gates paid for themselves — and the live runs, not the unit tests, found the defects.**
Five real ones this session-and-the-last, each behind an injected seam while 63–96 unit checks
passed: layer 3's decoder on Korean UBT output · the skeleton contract hole (`[PSEUDO]` alone
doesn't compile for non-void) · an invented enum value · `decode()` returning `Decoded` not `str` ·
the integrator dying where the graph was absent. **Put one live run behind every gate.**

[중요] **Grounding, not the model, is what makes 층2 work** (measured 2026-08-12): 4 of 5 candidates
missed an invented enum member with no declarations in the prompt; all caught it with them. And
**local models are unusable for 층2** — 35B blocked two *correct* files. `agy`→`claude` is the
chain, and that default is now measured rather than assumed.

[중요] **This project has ZERO automation tests** (measured: no `AUTOMATION_TEST`/`FunctionalTest`
anywhere in `Source/`). §4.3's *"hallucinations that compile"* are catchable **only by tests**, so
층3's `RunTests` is deliberately **fail-open with a loud warning**. That hole cannot be closed by
code — writing tests is a project decision, parked in the milestone's 「예정」.

[중요] **What distribution buys is incremental progress, not throughput** (user-reframed 2026-08-11).
Measured: two workers were 12% faster and **90% more expensive**; the 3.2× saving came from
batching, not parallelism; layer 3 was serial on `.2` all along. The value is that work accumulates
**in a state that always compiles** — which makes verification a premise, not an option.

[중요] **Skeletons are not fully automatic either** (user, 2026-08-11). The skeleton reports where it
had to guess, **only the human's answers are stored**, and each answer carries a scope
(`project` / `domain:<D>` / `once`) — without it one work's decision pollutes every later one.

[중요] **Deliberately outside M3**: asset/blueprint twins (the twin's scope is **source-only**),
BC-250 #2 conversion (that is giving up a gaming machine, not a setup task), master GPU expansion,
and team-distribution packaging. Not-yet-done ≠ forgotten.

[중요] **Never size a task by line count** — `class_graph`'s 1,341 lines are *"delete the file → full
rescan on restart"*, while one 829-line file holds the domain index, norm search and the thesaurus
builder together.

[중요] **Say "done" only for a whole area**; otherwise give the denominator. And **don't pick the
next task yourself** — milestone 1 failed exactly that way.

[중요] **애매하면 묻는다 — 임의 판단으로 좁히지 않는다** (사용자 2026-08-13 · 원전 3조). 애매함은
둘: **설계의 갈림길**과 [중요] **「작업 지시인지 단순 질문인지」**. **짧은 수긍(`응`)이 가장
위험하다** — 앞에 물음이 없었으면 승인이 아니라 수긍일 수 있다(실측: 한 세션에서 `응` 두 번,
하나만 승인).

[중요] **이 파일과 게임 소스는 고치기 전에 계획을 말하고 동의를 받는다** (원전 1조, 범위는 사용자
결정 2026-08-14) — **이 파일은 매 세션 자동 로드되므로 한 줄이 모든 다음 세션을 바꾼다.**

[중요] **만들기 전에 원전(`~/AgentTest`)과 기존 자산을 읽는다** — 안 읽고 만들면 요구를 좁힌다
(그렇게 잃은 것 셋: 로컬 파일 웹 UI · 읽기 전용 화면의 로그인 · 원전 3,700줄을 안 읽고 새로 쓴
229줄 뷰어). **제약 하나를 지키려고 요구를 희생하면 결과물은 못 쓴다. 묻는 쪽이 늘 싸다.**

→ 위 셋의 근거·실측·범위와 원전 5조 대조표: `~/ax-cluster/docs/11-agent-conduct.md`

## Role in the AX cluster — this box is the **master**

The project repo is cloned **here** at `~/ax-cluster` (`PLAN.md` is the index, content in `docs/`),
with copies on BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`) and GitHub (`SimSeoWon/ax-cluster`,
**private — keep it that way**, it holds LAN addresses and firewall rules). Keep all three in sync.
The board has `main` checked out so pushing there is rejected — **`git pull` on that side instead.**
`~/AgentTest` is the predecessor clone — **reference only. Never modify or push to it.**

### Machine inventory (probed 2026-08-08)

| IP | Machine | Login | Role | Reachable from here |
|---|---|---|---|---|
| **.57** | **sim-desktop** — this box | `sim` | **Master**: orchestration, RAG index, ontology/graph, task queue, broker, project registry | — |
| **.2** | Windows + **RTX 3060**, UE5 installed<br>host `DESKTOP-HV0I6DL` | **`janus`**<br>(admin) |  **Worker** *and* inference endpoint #2 (14b pinned). **The only machine that can run the layer-3 verdict unattended** (UE5 5.8). **Resident claimer `AxClaimer`** (#204, 2026-08-18) — schtasks 5-min watchdog, pulls **build+code** jobs from the queue (logon-session only; ops in `win-worker-2.md` § AxClaimer) | **`ssh janus@192.168.0.2`** [완료] passwordless · RDP 3389 · Ollama 11434 |
| **.33** | Windows 10.0.26200, **the user's main work PC**<br>host `DESKTOP-FU2GNGL` | **`user`** | [중요] **`requester`, not a worker** — registers work, verifies (it has UE5), gives feedback. **Never dispatched to** (`drivable_hosts` excludes it). Not an inference endpoint | **`ssh user@192.168.0.33`** [완료] passwordless (2026-08-08) · RDP 3389 · Ollama 11434 |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` |  **Worker** *and* inference endpoint #1. **35B residency was REMOVED 2026-08-17 (user decision ⓐ, measured #105)** — plain sequential inference grew GPU(GTT) allocations ~120MB/cycle and collapsed the node in 4 minutes; idle did not release it; only `systemctl restart ollama` did (NOPASSWD exists for it). Now pins **gemma4:e4b (~5GB, ~10GB headroom)** — the synth model, which also kills the old fallback-OOM hazard. The 35B stays on disk, unpinned. **e4b also fills the agentic-driver seat (#106 closed 2026-08-17)** — tool-calling gates 4/4 ×3 runs + Korean 3/3, 30-cycle sustained 30/30 with no #105-style accumulation (~-5MB/cycle vs 35B's -120). Fallback: `qwen3:8b` (4/4, lives on `.2`). Has the project clone at `~/trunk/ModularStage` — no longer stateless. **Resident claimer via cron watchdog** (#204, 2026-08-18) — pulls **code(infer)** jobs only (no UE5; caps come measured from `.ax/config.json`; ops in `bc250-1.md` § AX claimer) | `ssh sim@192.168.0.43` [완료] passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
| — | BC-250 #2 | — |  **Bazzite gaming machine — NOT an inference node.** Converting it means giving up that machine. **Never assume a 2nd board exists.** | n/a |

### `.33` — the main work PC has its own guide

SSH and Ollama came up 2026-08-08; **the account is `user`**. But **it is not an inference
endpoint** — measured free VRAM **7651 MiB** is smaller than its own only model (8.95 GiB) and
than the coder model (9.0 GB), and opening UE5 takes more (`resident=False`).

**Its role is `requester`** (2026-08-09): it registers work, verifies (UE5 is here, so compile
errors surface fastest), and writes `[FEEDBACK]` blocks. It is **excluded from `drivable_hosts`** —
never dispatched to. [주의] When it verifies, use **`git worktree`**, never a branch switch in the
human's main tree: uncommitted `.uasset` work cannot be recovered.

[중요] **This is the human's machine** — the master is a guest here: read-only by preference, dirty
check before anything that writes. Everything else — session-0 boundary, UE5 checkout path,
the Store-stub Python trap, local + commercial LLMs — lives in
**[`win-main-33.md`](win-main-33.md)**.

### `.2` — the Windows worker has its own guide

[중요] **The account is `janus`, not `sim`** — `ssh sim@192.168.0.2` fails with
`Permission denied (publickey,...)`. Everything else about that box — OS, session-0 boundary
(what the master can and cannot drive there), UE5 project path, local + commercial LLMs, the
SSH PATH trap — lives in **[`win-worker-2.md`](win-worker-2.md)**, which is also copied to
`C:\Users\janus\CLAUDE.md` so sessions on that machine load it.

[완료] The master's services are reachable from `.2` — 8101, 8102, 8103 all verified (2026-08-08).

### Roles — `driven` (can we reach it) ≠ `role` (may we dispatch to it)

    worker      claims from the queue and implements   .2 · .43
    requester   registers, verifies, gives feedback    .33  [중요] never dispatched to

**Every worker holds the project clone and judges from source** — that is the point, and all
workers are equal in it. UE5 only decides *who can run the layer-3 verdict*. The per-machine
`<checkout>/.ax/config.json` is the single source of truth for paths/capabilities; it is
**generated by the master** (`python -m master.client deliver`), never hand-copied — a worker's
config was once found pointing at *another machine's* path.
→ [`../docs/8-git-authority.md`](../docs/8-git-authority.md) §8.4

### Design rules (inherited from the AgentTest 2026-07-07 architecture)

- **Ollama inference calls** are text-only — context/code fragments/diffs cross the wire, never
  files. [주의] That is about the **model**, not the machine: `.43` now also runs a worker agent that
  *does* read its own clone. The two roles coexist on one box.
- Master→node calls are **stateless** (Ollama `/api/generate`, with the `context` field
  deliberately not reused).
- **Deterministic gates (tests / type checkers / linters) outrank LLM judgment** for verification.
- [중요] **Never shard a model across BC-250 boards** — each board is an independent endpoint and the
  master load-balances *requests*. The boards have 1GbE and no PCIe slots, so tensor/pipeline
  parallelism starves on bandwidth.

## Detail documents

| What you need | File |
|---|---|
| Self-hosted services · ports · **firewall rules for the 3 auth-less AX services** | [`sim-desktop.d/services.md`](sim-desktop.d/services.md) |
| BC-250 access — SSH · **the no-TTY sudo trap** · mandatory reading before hardware work | [`sim-desktop.d/bc250-access.md`](sim-desktop.d/bc250-access.md) |
| Windows main work PC `.33` — **guest rules**, UE5 path, Python trap | [`win-main-33.md`](win-main-33.md) |
| PATH · **`pkexec` for privileged work** · Python · GPU | [`sim-desktop.d/environment.md`](sim-desktop.d/environment.md) |
| **Which LLM is good at what · where hallucination was measured** | [`llm-fitness.md`](llm-fitness.md) |
| Cluster design — settled vs open | `~/ax-cluster/PLAN.md` → `docs/` |
| Working *in* the repo | `~/ax-cluster/CLAUDE.md` |

## Work journal

Numbered work reports accumulate in `~/claude-workspace/reports/` (mirroring the BC-250's
`~/bc250-backup-staging/reports/` convention). Reports are written in Korean — the user reads them.

- **Read the reports in full at session start** — grep is not a substitute. There is an incident
  where near-miss wording was filtered out and already-recorded work got re-investigated.
- **For infra work that needs a reboot or risks losing access, write the intended commands to a
  report file *before* running them and update it *during* the work** — if the connection drops,
  the file is the only surviving record of what was attempted.
- Afterwards, also update the preceding report's "remaining" list with what got done.
- [중요] **Reports are not the task list.** Work items live in **Redmine** (`:8080`, project
  `ModularStage` — the AX cluster is *the same project*, never make a new one) and progress lives
  in the open milestone doc. Three places, three jobs — see `~/ax-cluster/CLAUDE.md` § Work flow.
