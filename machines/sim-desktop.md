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

[중요] **This box is infrastructure — the workshop is `.33`** (사용자 2026-08-20). Unreal work
**enters through `.33`**: the user opens `claude` in `C:\Users\USER\Documents\ModularStage`, and the
delivered `ax-request` skill registers it. What is handled **here** is the cluster itself — queue ·
broker · index/ontology · integration · the cluster's own code in `~/ax-cluster`. **A session here
does not start a game-source task; it serves one.**
→ [`win-main-33.md`](win-main-33.md) § 요청자 콘솔

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

[중요] **"one writer" was never my invention; that writer is the server** (the origin's
`cluster_coordinator.py` said *"durable 단일 writer 보존"* while our repo cited it 0 times —
report 14). [주의] **The origin's second half — workers pushing ephemeral `attempt/` branches —
is no longer ours**: `#327` tore that tier down 2026-08-27 (`#317` 미결 ⑦). `carry.publish` now
pushes straight to the durable `task/<work>/<task>` **after** the gate passes (verify-then-commit),
and isolation is the **worktree** (`#321` forces it), not a branch. The evidence a failed attempt
used to carry lives in the spool and the Redmine note instead.

This project is an **OS/environment port** (Windows+UE5
daemon → Linux+Gitea) and Linux forces exactly **one** change: the UE5 build step *inside*
`verify_and_merge` moves to `.2`. Not even Gitea was forced — the origin's doc listed GitHub/Gitea/
bare as a choice. **소 1.1 (read the origin's design docs) is upstream of everything.**

[중요] **Workers may not delete branches** — a branch is removed only when its tip is reachable from
`origin/main`, and workers return to **`main`**.

The pipeline (M3, four deterministic gates — detail in `3-work-pipeline.md`):

    요청(`.33`) → **`.33` 이 골조를 만들어** `task/<work>/base` 에 실물 한 커밋 (UHT 게이트) → 등재
         → [마스터] 파견 → 워커는 **추론만**(ax-infer) → 스풀
         → 통합자 `.2`: 층1 → 층2 → 적용 → **조각별 UE5 빌드** → 통과분만 커밋 → work 단위 RunTests
         → [사람 승인] `finalize`: `main` 머지 + Redmine 기재 + **도달 가능 브랜치 정리** (한 호출)

[중요] **마스터는 골조를 만들지 않는다** (`#339`, 2026-08-30 — 그 경로를 코드에서 지웠다).
`#317` ①·`#319` 가 골조 제작을 요청자로 옮겼는데 `#319` 는 「나르기」만 없애고 「만들기」를
남겨 뒀고, 첫 실전 등재가 마스터에서 `claude:opus` 를 동시 2프로세스로 돌렸다. 등재가 하는
것은 **큐 등록과 매니페스트 수집**이다.
[완료] **파견은 자동이다** (`#340` `c33316e`·`9cc73d9`, 라이브 2026-09-01 — 4/4 · 10분 4초 ·
사람 개입 0). 요청자가 `task/<work_id>/base` 를 push 하면 그 이벤트가 `ax-dispatch.path` 를
깨우고, **파견이 끝나면 통합까지 이어진다.** [중요] **사람 게이트는 finalize(`main` 머지)
한 곳뿐이다** — 통합 앞에 게이트를 만들지 않는다(내가 근거 없이 하나 만들었다가 정정받았다).
[주의] **세션 한도로 멈추면 재개만 사람 지시다** (사용자 결정 2026-09-01): 보류가
`~/.cache/ax-dispatch/hold.json` 에 남아 **재부팅을 넘고**, 시각이 지나도 자동으로 풀리지 않는다.
`.33` 세션 시작 훅이 「재개 대기」를 고지하고, 푸는 것은
`python -m master.work.autodispatch --resume <프로젝트> <work_id>` 뿐이다.
[주의] **골조를 올렸는데 `[dispatch]` 줄이 하나도 없으면 배선이 죽은 것이다** — 파견은 걸었는지와
왜 안 걸었는지를 **둘 다** 찍는다. 그 침묵이 2026-08-29~31 이틀을 태웠다(리포트 44).

[중요] **서버로 가는 모든 「쓰는」 요청은 프로젝트 태그를 실어야 한다** (`#257`, 2026-08-22).
태그가 없거나 마운트와 다르면 **200 + `ok:false`** 로 거절되고 사유가 셋이다 — `no_project_tag`
(발신자 배선) · `not_mounted`(마운트 전환) · `project_mismatch`(work 스탬프 불일치 — `#210` 축이라
마운트와 비교하지 않는다). [주의] **발신자 배달이 서버 조임보다 먼저다** — 순서를 어겨 `.43`
상주가 20분간 폭주했다. 계약·표·순서 규칙: `~/ax-cluster/docs/13-request-tagging.md`

[중요] **승인 뒤는 손으로 정리하지 않는다** (2026-08-21, 원전 `finalize_work` 6단계 동등):
`finalize_work(confirm=True)` 가 머지·기재·정리를 이어서 한다. 기본값은 `confirm=False`(통합만 하고
멈춤)이므로 **승인이 곧 트리거**다. [주의] 자동 삭제는 **`main` 에서 도달 가능한 것만** — 미병합은
사람 몫이고, 그 판정을 pre-push 훅(`#125`)이 한 번 더 한다.

The status screen and the ported web UI are served on the LAN at `http://192.168.0.57:8103` —
[중요] **no login — and that includes `/api/v1` on that port** (measured 2026-08-25: 200 with no
token, on loopback *and* the LAN address; `webui/app.py PREFIXES` lists `/api/v1` and that tuple is
passed as `public_prefixes`, because the web UI calls its own API). **The remaining defence is the
one ufw LAN-only layer** — reversible with `AX_VIEW_REQUIRE_TOKEN=1`. [주의] So never put a
sensitive body on this port: `api_history` deliberately withholds `user_quote`, bodies and absolute
paths, and full reads live on token-locked 8101 (`find_history`) — the same call the repo already
made for Redmine reads. Its palette is **dark-only on
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

> [중요] **아래 셋은 조건이 「관측 가능한 사건」이다 — 내가 「해당 없음」을 판정할 자리가 없다.**
> 종전 규칙(위 「애매하면 묻는다」·「만들기 전에 원전을 읽는다」)은 **내가 「지금은 애매하지
> 않다」·「지금은 만드는 게 아니다」로 스스로 판정**할 수 있어서, 2026-08-25 세션에서 넷 다
> 어겨졌다(무단 `carry.py` 수정 · 손으로 브랜치 생성 · 오진 보고 · 원전 미확인). 사용자
> 지적: *"그 판단이 심지어 문제를 만들잖아"* — 실제로 없던 문제를 만들었다.

[중요] **실패는 고치는 자리가 아니라 보고하는 자리다.** 명령·게이트·빌드가 실패하면
(rc≠0 · 차단 · 예외) 원인은 조사해도 **코드·설정을 고치지 않는다.** 그 자리에서 사유와
갈래를 내고 멈춘다. [주의] 「이건 설계 결정이 아니라 단순 수정이다」를 내가 판정하지 않는다 —
**실패했다는 사실만으로 보고 조건이 성립한다.**

[중요] **지시받은 대상 밖의 파일은 건드리지 않는다.** 대상 목록에 없는 파일을 고치려는
순간 멈추고 보고한다. 경로가 목록에 있는지는 판정이 필요 없다.

[중요] **사용자가 세션에 있는 동안 추측을 적립하지 않는다 — 대화로 묻는다.** 골조의
`questions` 가 이미 그 방식이다(모델의 제안을 답으로 적립하지 않는다). 사람이 컴퓨터 앞에
있는데 추측으로 진행하는 것이 가장 비싸다.

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
| **.2** | Windows + **RTX 3060**, UE5 installed<br>host `DESKTOP-HV0I6DL` | **`janus`**<br>(admin) |  **Worker** *and* inference endpoint #2 (14b pinned). **The only machine that can run the layer-3 verdict unattended** (UE5 5.8). [중요] **No resident claimer — torn down 2026-08-27** (`#320`, user decision; `#317` 미결 ⑤). The master drives this box over SSH: `run_build_on_workshop` calls `Build.bat` directly, so **no Python payload is needed here** to build. Nothing on this box polls the queue. Revival condition: `#320` notes | **`ssh janus@192.168.0.2`** [완료] passwordless · RDP 3389 · Ollama 11434 |
| **.33** | Windows 10.0.26200, **the user's main work PC**<br>host `DESKTOP-FU2GNGL` | **`user`** | [중요] **`requester`, not a worker — and the entry point for all Unreal work** (사용자 2026-08-20): the user works in `ModularStage` here, opens `claude`, and the **already delivered requester console** registers it (home skills `ax-request`·`ax-ontology`·`ax-review` · `ax-client` MCP in the checkout's `.mcp.json` · `.ax/token`). Registration from the master is only ever standing in for this. Verifies (it has UE5), gives feedback. **Never dispatched to** (`drivable_hosts` excludes it) — [중요] the `dispatch` field (`#321`) does **not** change this: it is **narrowing-only**, meaning it can pull a *worker* out of rotation (maintenance, low resources) but cannot switch a requester on. `role` is the *right* to be sent work; `dispatch` is *availability right now*. Not an inference endpoint | **`ssh user@192.168.0.33`** [완료] passwordless (2026-08-08) · RDP 3389 · Ollama 11434 |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` |  **Worker** *and* inference endpoint #1. **35B residency was REMOVED 2026-08-17 (user decision ⓐ, measured #105)** — plain sequential inference grew GPU(GTT) allocations ~120MB/cycle and collapsed the node in 4 minutes; idle did not release it; only `systemctl restart ollama` did (NOPASSWD exists for it). Now pins **gemma4:e4b (~5GB, ~10GB headroom)** — the synth model, which also kills the old fallback-OOM hazard. The 35B stays on disk, unpinned. **e4b also fills the agentic-driver seat (#106 closed 2026-08-17)** — tool-calling gates 4/4 ×3 runs + Korean 3/3, 30-cycle sustained 30/30 with no #105-style accumulation (~-5MB/cycle vs 35B's -120). Fallback: `qwen3:8b` (4/4, lives on `.2`). Has the project clone at `~/trunk/ModularStage` — no longer stateless. [중요] **No resident claimer — the cron watchdog was removed 2026-08-27** (`#320`). Master-driven SSH push only. Caps still come measured from `.ax/config.json` | `ssh sim@192.168.0.43` [완료] passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
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

[중요] **Restart an AX service with `sudo -n /usr/bin/systemctl restart <unit>`** (NOPASSWD is
registered for `ax-task-queue`·`ax-broker`·`ax-projects`·`ax-indexer.service`·`ax-status.timer`).
Plain `systemctl restart` as `sim` intermittently hangs on polkit/D-Bus and reports *"Method call
timed out"* — measured 3× in a row 2026-08-19 while the service itself was healthy, and `--no-block`
timed out the same way. [주의] **Judge success by `ExecMainStartTimestamp`, not the exit code** —
the failing command left the old process running, so `is-active` still said `active`.

[중요] **훅 설치도 NOPASSWD 다** — `sudo -n /usr/local/bin/ax-install-hook --apply`. 온보딩의
`hook` 단계가 무인으로 돌아야 하기 때문이다(사용자 2026-08-22: *"자동화를 전재로 프로젝트
구성중"*). [주의] 그 규칙은 실질적으로 `sim`→root 경로다 — 근거·완화는
`sim-desktop.d/environment.md` § Registered NOPASSWD commands.

## Detail documents

| What you need | File |
|---|---|
| Self-hosted services · ports · **firewall rules for the 3 auth-less AX services** | [`sim-desktop.d/services.md`](sim-desktop.d/services.md) |
| BC-250 access — SSH · **the no-TTY sudo trap** · mandatory reading before hardware work | [`sim-desktop.d/bc250-access.md`](sim-desktop.d/bc250-access.md) |
| Windows main work PC `.33` — **guest rules**, UE5 path, Python trap | [`win-main-33.md`](win-main-33.md) |
| PATH · **`pkexec` for privileged work** · Python · GPU | [`sim-desktop.d/environment.md`](sim-desktop.d/environment.md) |
| **Which LLM is good at what · where hallucination was measured** | [`llm-fitness.md`](llm-fitness.md) |
| Cluster design — settled vs open | `~/ax-cluster/PLAN.md` → `docs/` |
| [중요] **요청 태그 계약** — 네 정책 · 필수 표면 · 거절 사유 셋 · 발신자 · **순서 규칙** | `~/ax-cluster/docs/13-request-tagging.md` |
| [중요] **신규 프로젝트 온보딩 런북** — 명령 단위 · 단계별 「안 됐으면 무엇이 안 보이나」 | `~/ax-cluster/docs/14-onboarding-runbook.md` |
| [중요] **세션 시작에 먼저 읽을 둘** | `~/ax-cluster/docs/milestones/6-improvements.md`(열린 마일스톤) · `~/ax-cluster/docs/12-multi-project.md`(지금 열린 축). [주의] 항목·진행은 **레드마인만** |
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
- [중요] **Reports are not the task list.** Work items live in **Redmine** (`:8080`).
  [중요] **AX 인프라 일감은 `ModularStage` 에 둔다** — the AX cluster is *the same project*
  (user decision 2026-08-09); use the `[AX]` title prefix to tell them apart. [주의] That is
  **not** "one Redmine project only" — a game project's own issues go where its
  `<twin>/config.yaml` `redmine.project` says (`ModularStage`→`modularstage` · `NS`→`ns`).
  No fallback: unset means refuse (`#293`). Progress lives in the open milestone doc.
  Three places, three jobs — see `~/ax-cluster/CLAUDE.md` § Work flow.
