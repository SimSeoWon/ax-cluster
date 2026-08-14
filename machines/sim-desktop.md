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

**M1·M2 closed. 🔴 M3 is `locked` — halted 2026-08-13. M4 (원전 대조·재이식) is open.**

| | |
|---|---|
| Current milestone — **read only this one** | `~/ax-cluster/docs/milestones/4-origin-reconciliation.md` |
| 🔴 Halted, do **not** work there | `3-work-pipeline.md` — its 9 open issues carry a *"M4 재검토 대기"* note |
| Closed, kept as reference | `2-twin-restoration.md` (🔴 its 「여기서 배운 것」 is the trap list) · `1-infrastructure.md` |

🔴 **Why M3 was halted (report 14, an origin-citation census).** Measured: **74 files / 23,710
lines of `~/AgentTest` are never once mentioned in our repo.** The three losses in report 13 §18
were not three mistakes but **a pattern** — they only surfaced because the user *saw* those screens.
The worst hit is the topology: `cluster_coordinator.py` (200 lines, **cited 0 times**) already had
`assign_attempt` / `push_attempt` / `verify_and_merge` / `cleanup_attempts` / `fake_worker`, and its
comment reads *"durable 단일 writer 보존"* — 🔴 **"one writer" was never my invention; that writer
is the server, and workers push ephemeral `attempt/` branches.** This project is an **OS/environment
port** (Windows+UE5 daemon → Linux+Gitea), and Linux forces exactly **one** change: the UE5 build
step *inside* `verify_and_merge` moves to `.2`. ⚠️ Even Gitea wasn't forced — the origin's doc listed
GitHub/Gitea/bare as a choice. M4 = 대 4 / 중 17 (🔴 소 count moved 62 → 75 in one session and later 75 → 80 — **the numbers live
in Redmine**, version *마일스톤 4*), and 🔴 **소 1.1 (read the origin's design docs) is upstream of everything.**

**What M2 delivered** (closed 소 43/43): the twin **grows, is indexed, and reaches code
generation** — both of its goals run end to end. Manifests carry **domain norms** *and* **header
declarations** (measured: real hallucinations 2 → 0). The **worker runner** dispatches from the
queue into a worker's Claude and submits the result (requester→worker loop measured 1m29s), and the
master **cleans up worker debris** — 🔴 workers may not delete branches, a branch is removed only
when its tip is reachable from `origin/main`, and workers return to **`main`**.

> ⚠️ **The block from here to 「Deliberately outside M3」 is M3's record, not a current
> instruction.** M3 is `locked`. It stays because its **traps** are still live (the gates, the
> grounding measurement, the zero-automation-test hole) — read them as *"what we learned"*, and read
> **current** scope from M4's milestone doc and Redmine (version *마일스톤 4*).

**M3 goals** (user, 2026-08-10): ① ✅ **decompose one big request** ② ✅ **judge with the 3-layer
deterministic gate** ③ 🔵 **build the operator surface** — status screen ✅, upper-layer commands and
robustness remained when it was halted. Structure was 대 3 / 중 10. 🔴 **Numbers never live in a
hand-edited doc** — the numerator drifted twice in M2, and the *denominator* moved on 2026-08-10
(32 → 36) when reading the predecessor's design doc uncovered four missing sub-tasks. M4 moved
**62 → 75 in one session, then 75 → 80** for the same reason.

🔴 **대 1 and 대 2 are closed (2026-08-12). 대 3 is the only one open.** The pipeline runs end
to end and **four deterministic gates** sit in it:

    요청 → 골조(claude:opus, 등재 전 빌드) → 분해 → 워커는 **추론만**(ax-infer) → 스풀
         → 통합자 `.2`: 층1 → 층2 → 적용 → **조각별 UE5 빌드** → 통과분만 커밋 → work 단위 RunTests

Live: dispatch 45s/$0.27 · two workers in parallel 36s/$0.47 · integrator build 142s + commit ·
unattended RunTests 74s. ✅ **중 3.2 status screen** is up (`python -m master.status html`) and
**served on the LAN at `http://192.168.0.57:8103`** — 🔴 **no login** (API paths on that port
stay token-locked). 🔴 **The predecessor's web UI was ported back verbatim** (`master/webui/`,
2026-08-13): `/` Context Server (status cards + Search/Documents/Tags/Domains + the domain board
with LLM create/chat/activate), `/ontology` the domain viewer (tree nav + **Cytoscape object
graph** + layer-sized nodes), `/cluster` the cluster status snapshot. ⚠️ `/cluster` serves the **last
generated** snapshot — a browser refresh never triggers SSH polling (that would defeat the 120s
guard). 🔴 **`ax-status.timer` refreshes it every 5 min**; a stale page still gets a red age banner,
and because 5 min < the 15-min staleness threshold, **that banner appearing means the timer is
actually broken.** 🔴 Its palette is copied from the ported pages and is **dark-only on purpose** —
one screen flipping to light on its own reads as a different app.
🕓 Remaining in 대 3: upper-layer commands (중 3.1) and operational robustness (중 3.3).

🔴 **The gates paid for themselves — and the live runs, not the unit tests, found the defects.**
Five real ones this session-and-the-last, each behind an injected seam while 63–96 unit checks
passed: layer 3's decoder on Korean UBT output · the skeleton contract hole (`[PSEUDO]` alone
doesn't compile for non-void) · an invented enum value · `decode()` returning `Decoded` not `str` ·
the integrator dying where the graph was absent. **Put one live run behind every gate.**

🔴 **Grounding, not the model, is what makes 층2 work** (measured 2026-08-12): 4 of 5 candidates
missed an invented enum member with no declarations in the prompt; all caught it with them. And
**local models are unusable for 층2** — 35B blocked two *correct* files. `agy`→`claude` is the
chain, and that default is now measured rather than assumed.

🔴 **This project has ZERO automation tests** (measured: no `AUTOMATION_TEST`/`FunctionalTest`
anywhere in `Source/`). §4.3's *"hallucinations that compile"* are catchable **only by tests**, so
층3's `RunTests` is deliberately **fail-open with a loud warning**. That hole cannot be closed by
code — writing tests is a project decision, parked in the milestone's 「예정」.

🔴 **What distribution buys is incremental progress, not throughput** (user-reframed 2026-08-11).
Measured: two workers were 12% faster and **90% more expensive**; the 3.2× saving came from
batching, not parallelism; layer 3 was serial on `.2` all along. The value is that work accumulates
**in a state that always compiles** — which makes verification a premise, not an option.

🔴 **Skeletons are not fully automatic either** (user, 2026-08-11). The skeleton reports where it
had to guess, **only the human's answers are stored**, and each answer carries a scope
(`project` / `domain:<D>` / `once`) — without it one work's decision pollutes every later one.

🔴 **Deliberately outside M3**: asset/blueprint twins (the twin's scope is **source-only**),
BC-250 #2 conversion (that is giving up a gaming machine, not a setup task), master GPU expansion,
and team-distribution packaging. Not-yet-done ≠ forgotten.

🔴 **Never size a task by line count** — `class_graph`'s 1,341 lines are *"delete the file → full
rescan on restart"*, while one 829-line file holds the domain index, norm search and the thesaurus
builder together.

🔴 **Say "done" only for a whole area**; otherwise give the denominator. And **don't pick the
next task yourself** — milestone 1 failed exactly that way.

🔴 **애매하면 묻는다 — 임의 판단으로 좁히지 않는다** (사용자 2026-08-13 · 원전 3조). 애매함은
둘: **설계의 갈림길**과 🔴 **「작업 지시인지 단순 질문인지」**. ⚠️ **짧은 수긍(`응`)이 가장
위험하다** — 앞에 물음이 없었으면 승인이 아니라 수긍일 수 있다(실측: 한 세션에서 `응` 두 번,
하나만 승인).

🔴 **이 파일과 게임 소스는 고치기 전에 계획을 말하고 동의를 받는다** (원전 1조, 범위는 사용자
결정 2026-08-14) — **이 파일은 매 세션 자동 로드되므로 한 줄이 모든 다음 세션을 바꾼다.**

🔴 **만들기 전에 원전(`~/AgentTest`)과 기존 자산을 읽는다** — 안 읽고 만들면 요구를 좁힌다
(그렇게 잃은 것 셋: 로컬 파일 웹 UI · 읽기 전용 화면의 로그인 · 원전 3,700줄을 안 읽고 새로 쓴
229줄 뷰어). 🔴 **제약 하나를 지키려고 요구를 희생하면 결과물은 못 쓴다. 묻는 쪽이 늘 싸다.**

→ 위 셋의 근거·실측·범위와 원전 5조 대조표: `~/ax-cluster/docs/11-agent-conduct.md`

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
| **.43** | **BC-250 #1** — Fedora, headless | `sim` | 🔧 **Worker** *and* inference endpoint #1 (35B pinned). Has the project clone at `~/trunk/ModularStage` since 2026-08-09 — **no longer stateless**. 🔴 **With the 35B resident it runs on 138–300 MB of headroom and ordinary batch load is at the edge** — it died mid-batch on 2026-08-15 (OOM → self-reboot). Whether it should keep hosting the 35B is **open, and it is the user's call**; check `machines/bc250-1.md` before pointing new batch work at it | `ssh sim@192.168.0.43` ✅ passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
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
