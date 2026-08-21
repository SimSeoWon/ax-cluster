# AX Cluster — plan (index)

**Goal (AX, AI Transformation):** fundamentally raise AI usage across an entire Unreal Engine 5
game production pipeline — beyond coding assistance, unifying an ontology-based digital twin,
Unreal MCP (UE 5.8.1+), and code-writing agents into one pipeline.

**Started:** 2026-08-05 · **Split into sections:** 2026-08-08 (one 1,839-line file → 13 in `docs/`)

## Milestones

| | Document | State |
|---|---|---|
| **1 — Infrastructure** | [`docs/milestones/1-infrastructure.md`](docs/milestones/1-infrastructure.md) | [완료] **closed** 2026-08-08. Its section documents (`docs/1`–`docs/10`) **stay valid** — kept, not discarded |
| **2 — Digital twin restoration** | [`docs/milestones/2-twin-restoration.md`](docs/milestones/2-twin-restoration.md) | [완료] **closed** 2026-08-10 · 소 43/43. [중요] Read its **「여기서 배운 것」** section before repeating its mistakes |
| **3 — Work pipeline** | [`docs/milestones/3-work-pipeline.md`](docs/milestones/3-work-pipeline.md) | [중요] **`locked` — halted** 2026-08-13. 42/51 closed; its 9 open issues carry a *"M4 재검토 대기"* note. **Do not work there** |
| **4 — 원전 대조·재이식** | [`docs/milestones/4-origin-reconciliation.md`](docs/milestones/4-origin-reconciliation.md) | [진행] **open** 2026-08-13 — **read only this one.** Not a feature milestone: **consistency** |

[중요] **Milestone 1 wired the pipe. Milestone 2 made what flows through it.** The twin grows, is
indexed, and feeds code generation — both of M2's goals run end to end.

**Milestone 3 built the production pipeline** — decompose → skeleton + **frozen interface** →
generate across workers → apply sequentially → **3-layer deterministic gate** (L1 self-check /
L2 commercial model / L3 UE5 build + RunTests) — and then **it was halted.**

[중요] **Milestone 4 is why.** An origin-citation census (report 14) measured **74 files / 23,710 lines
of `~/AgentTest` never once mentioned in this repo**, and what was lost was not three mistakes but
a **pattern** — the three losses in report 13 §18 only surfaced because the user *saw* those screens.
The worst hit: `cluster_coordinator.verify_and_merge` already said *"durable 단일 writer 보존"* and
**that writer is the server** — workers push ephemeral `attempt/` branches. This project is an
**OS/environment port** (Windows+UE5 daemon → Linux+Gitea) and Linux forces exactly **one** change:
the UE5 build step inside `verify_and_merge`. Everything redesigned beyond that was redesign.
→ M4 restores the origin's shape, turns M3's four open items into **ports**, recovers un-ported
assets, and reclaims the origin's **method and norms**.

[중요] **「안 옮기는 판단」에도 근거가 필요하다** — 4 items were re-scoped, not ported, because the
**condition the origin's fix targeted does not exist here**: console-UTF8 (our master is already
utf-8), lone-surrogate replacement (**porting it would be a regression** — we already fail loudly),
`worker/safety` (no resident daemon), and the DB ontology tables (**not porting them removed the
origin's whole DB↔YAML drift problem**). κ.8 marks the same kind with *"리눅스로 옮기는 대상 아님,
혼동 주의"*. Re-scoped items stay **open**, not closed — the premise can change.

[중요] **What distribution buys is incremental progress, not throughput** (user-reframed 2026-08-11):
measured, two workers were 12% faster and **90% more expensive**, and the 3.2× saving came from
batching, not parallelism. See `docs/4-work-loop.md` §4.5.
[중요] **Neither the numerator nor the denominator is written in any document** — read both from Redmine
(version *마일스톤 4*). Hand-kept numerators drifted twice in M2, and the **denominator moves whenever
reading the origin uncovers work**: M3 went 32 → 36, and **M4 went 62 → 75 in one session** (three
separate reads each found real gaps), then **75 → 80** as later ports kept surfacing their own
missing halves. That movement is normal — record it, don't hide it.

> [중요] **This file is an index. The content lives in `docs/`.**
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
| 5.5 | [Project isolation](docs/5_5-project-isolation.md) | Multi-project directory layout and the mount contract | Many directories, **one mount** — [주의] the 409/fail-closed enforcement was **never wired** (`resolve_mounted_only` has zero production callers); see [`docs/12`](docs/12-multi-project.md) §12.4 |
| 6 | [Node failover](docs/6-node-failover.md) | Liveness detection and remote power recovery | Streaming chunk gap *is* the heartbeat (no separate comms infra) |
| 7 | [Master GPU](docs/7-master-gpu.md) | Whether to add a GTX 1070 Ti for RAG/CUDA | **Open** — confirming the PSU's PCIe aux connector comes first |
| 8 | [git authority](docs/8-git-authority.md) | The permission boundary between human sessions and the pipeline | Humans: no destructive git. Pipeline: autonomous on `task/` branches only. Also the **branch lifecycle** (durable `task/<id>` → attempt → `main` return) and [중요] **who may delete branches** — workers may not; the master cleans, and only when the tip is reachable from `origin/<base>` |
| 9 | [gajae-code (gjc)](docs/9-gajae-code.md) | Where `gjc` runs, and why 14b blocked it | `gjc` runs on Windows; L2 gets a fail-closed VERDICT contract |
| 9.5 | [task_queue port](docs/9_5-task-queue.md) | Port stage 1 and service registration | Ported, `ax-task-queue` live, 8101 LAN-only |
| — | [Settled decisions](docs/settled-decisions.md) | Closed calls, gathered in one place | Don't relitigate without new measurements |
| 10 | [References](docs/10-references.md) | Original design, reports, external repos | — |
| 11 | [Agent conduct](docs/11-agent-conduct.md) | [중요] **행동 수칙** — 묻기(설계 갈림길 *및* 「지시인지 질문인지」) · 만들기 전에 읽기 · 수정 권한 · 승인과 검토 비용 · 실행 권한. 원전 `.agents/AGENTS.md` 5조 이식분이 여기 모여 있다 | 1조는 **범위 좁혀** 이식(자동 로드 문서 + 게임 소스) · 3·4조 이식 · 5조는 빌드 조항만 · [중요] **2조는 안 옮긴다**(Claude Code 는 툴 호출을 전부 띄운다 — 「몰래 호출」이 구조적으로 불가능) |
| 12 | [Multi-project](docs/12-multi-project.md) | 다중 프로젝트 운영 — 갈린 축과 안 갈린 축, 네 부모 일감의 지도 | [중요] **항목·진행은 레드마인만** (사용자 2026-08-22) · 마운트 강제는 **배선된 적이 없다**(§12.4 가 같은 거짓 서술 네 곳을 정정) |

---

## Currently running (updated 2026-08-14)

[주의] **This table was stale for six days** — it listed only the three HTTP services while five more
units had been added. Same recurrence as report 14 §26.4 (*"README 둘이 또 낡아 있었다"*).

| Service | Port | Unit | Defence |
|---|---|---|---|
| task_queue | 8101 | `ax-task-queue.service` | [완료] Bearer token + ufw LAN-only |
| Inference broker | 8102 | `ax-broker.service` | [완료] Bearer token + ufw LAN-only |
| Project registry (MCP) + web UI | 8103 | `ax-projects.service` | [완료] Bearer token on API paths + ufw LAN-only. [중요] The **status/ontology screens are login-free on purpose** (one person, four machines) |

**Event-driven and periodic units** (no polling daemons — PLAN §5.4.2·§5.4.3):

| Unit | Wakes on | What it does |
|---|---|---|
| `ax-indexer.path` | inotify on the event spool | push → mirror fetch → context synthesis → reindex |
| `ax-indexer.timer` | every 10 min | [중요] catch-up for what the pause gate deferred — **a guard without a waker never runs** |
| `ax-status.timer` | every 5 min | cluster status snapshot for `/cluster` (a browser refresh never triggers SSH polling) |
| `ax-batch.timer` | every 1 h | [중요] **checks** whether an idle batch is due; the ported **time gates** decide (원전 `watch_state`). Currently one batch: RAG channel analysis (stdlib, LLM 0) |

[중요] **Exit code 4 means "paused by the in-progress gate", not a failure** — both `ax-indexer` and
`ax-batch` use it with `SuccessExitStatus=4`. *"늘 빨간 유닛은 유닛이 아니다."*

**Two inference endpoints:** BC-250 #1 (35B pinned) and the RTX 3060 Windows PC (14b pinned).
All three now require `Authorization: Bearer <token>` (`~/.config/ax-cluster/token`, 0600);
only `/livez` is open. **Still never widen the ufw rules to `Anywhere`** — the token is a
second layer, not a replacement for the first.

Per-machine operating guides: [`machines/`](machines/README.md). Session work reports:
**저장소 작업분은 [`reports/`](reports/) — 동기 대상이다.** 하드웨어·인프라 로그는
`~/claude-workspace/reports/` 와 `sim@192.168.0.43:~/bc250-backup-staging/reports/`.
