# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

> 🔴 **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- 🔴 **Read which milestone you are in before planning anything.**
  **M1·M2 closed; 🔴 M3 is `locked` (halted 2026-08-13); M4 (origin reconciliation) is open.**
  → [`docs/milestones/4-origin-reconciliation.md`](docs/milestones/4-origin-reconciliation.md)
  🔴 **M4 is not a feature milestone — it is consistency.** An origin-citation census (report 14)
  measured **74 files / 23,710 lines of `~/AgentTest` never once mentioned in this repo**, and the
  worst hit is the topology: `cluster_coordinator.py`'s `verify_and_merge` already said
  *"durable 단일 writer 보존"* — **that writer is the server, and workers push ephemeral
  `attempt/` branches.** Linux forces exactly **one** change: the UE5 build step inside
  `verify_and_merge` moves to `.2`. Everything I redesigned beyond that was redesign, not a port.
  🔴 **Do not argue the topology from M3's docs** — its label *"사용자 확정 2026-08-11"* is wrong
  (it was *"그래 해"* after I pushed it), and `settled-decisions.md` §214 carries the same bad label.
  🔴 **Before building anything, read the origin and leave a citation.** Never-cited must-reads:
  `local_llm_distributed_workers_plan_v5.0.md` (463, user-confirmed C.1–C.7/κ.0),
  `.agents/AGENTS.md` (21 — its rule 3 *is* 애매하면 묻는다), `.claude/reviews/_silent_failure/
  audit_matrix.md` (99 — the σ audit method), `plan_completed_v4.5.md` (2397 — what already exists).
  **Read only the open milestone** — closed ones are reference; don't load them. Progress
  lives in the milestone doc, never in the design docs (`docs/1`–`docs/10`, always current).
  🔴 **Neither the numerator nor the denominator is written in any document** — read both from
  Redmine (version *마일스톤 3*). Hand-kept numerators drifted twice in M2, and the *denominator*
  moved on 2026-08-10 (32 → 36) when reading the predecessor's design doc uncovered missing work.
  M3 structure: 대 3 / 중 10 — **소분류가 작업 단위다**, main is 대 1 (decompose →
  skeleton + **frozen interface** → parallel generate → **sequential apply**). 대 2 is the
  3-layer verdict; 대 3 is the operator surface. Never size a task by line count:
  `class_graph`'s 1,341 lines turn out to be *"delete the file → full rescan on restart"*.
  🔴 **Two M2 rules that still bind here**: never bulk-regenerate the 1,055 snapshot docs (our
  local model measured *worse* than the received snapshot), and never hand-tune search weights
  before there is an answer set. M2's **「여기서 배운 것」** section is the short list of traps
  not to re-enter — read it once before starting a new area.
  🔴 **Do not pick the next task yourself** — M1 failed that way (I chose an order, dug into one
  piece, declared it "complete", repeated). The order is the user's call.
- 🔴 **애매하면 묻는다 — 임의 판단으로 좁히지 않는다** (사용자 지시 2026-08-13, 세 번 반복된 실패).
  설계에 갈림길이 있으면 **멈추고 사용자에게 묻는다.** "내 판단으로는 이게 맞다" 로 진행하지 않는다.
  🔴 **그리고 만들기 전에 기존 자산을 읽는다** — 이 저장소에는 원전(`~/AgentTest`)이 있고
  대부분의 요구에는 **이미 만들어진 것**이 있다. 안 읽고 만들면 요구를 좁혀 버린다.
  **실제로 그렇게 잃은 것 셋** (2026-08-12~13, 전부 사용자가 지적해서 알았다):

    웹 UI 를 로컬 파일로 만들었다        → 다른 머신에서 못 본다. **웹 UI 의 목적이 그것인데**
    읽기 전용 화면에 로그인을 붙였다      → 1인 4대 개인 인프라에 침입자 모델. 쓰이지 않는 화면이 된다
    온톨로지 뷰어를 229줄로 새로 썼다     → 원전에 3,700줄(트리·Cytoscape 그래프·태그·검색)이 **있었다**

  🔴 **제약 하나를 지키려고 요구 자체를 희생하면 결과물은 못 쓴다.** 판단이 갈리면 **묻는 쪽이
  싸다** — 되돌리는 비용이 묻는 비용보다 늘 크다.
- 🔴 **The GitHub remote is private. Keep it that way** — it contains LAN addresses and firewall rules.
- 🔴 **The master is infrastructure, not a workshop.** It assembles context and hands it over;
  the Windows PC applies, builds, tests, registers. **Files never leave Windows.** No file I/O or
  tool-calling on the master. → [`docs/2-architecture.md`](docs/2-architecture.md)
- 🔴 **All three services require a bearer token** (`task_queue` 8101, broker 8102, projects 8103).
  Token: `~/.config/ax-cluster/token`, 0600, **fail-closed — a service will not start without it**.
  Send `Authorization: Bearer <token>`; only `/livez` is open. They are *also* ufw LAN-only —
  **never widen those rules to `Anywhere`.** Two layers, not one instead of the other.
  → `master/auth.py`, PLAN §9.5.6
- 🔴 **`/home/sim/AgentTest` is reference-only — never modify or push to it.** Port code *out* of it.
- 🔴 **Never commit or push without asking first** (user, 2026-08-14: *"커밋은 나에게 허락을
  요구해줄래?"*). Prepare the message, **ask**, and run it only after approval. The origin's rule is
  stricter — `AgentTest/CLAUDE.md` and `.agents/AGENTS.md` rule 5 forbid Claude from committing
  *even when told*, and forbid asking too. 🔴 **Ours is deliberately looser and the user chose it**:
  the origin's Windows box has SourceTree, sim-desktop (Linux) has none, so "never" would force the
  user into a terminal every time. Keep that label straight — the *user* relaxed it, not me.
- 🔴 **Human sessions: never run** `push --force`, `reset --hard`, branch/tag deletion, `rebase`, or
  history rewriting — **not even with approval**; describe the command instead. Don't read a
  first-person statement ("I'll commit and come back") as an instruction to you — that exact
  misreading caused an incident in AgentTest (*"다 지워진 줄 알고 깜짝 놀랐다"*).
  ⚠️ **Pipeline code committing is a different thing** — the integrator/worker writing to
  `attempt`/`durable` branches is designed behavior; these rules bind the *interactive session*.
  → [`docs/8-git-authority.md`](docs/8-git-authority.md)
- 🔴 **Never trust a delegated backend's "done".** Measured 2026-08-07: `agy` returned
  `status:"SUCCESS"` while writing no file. Verify the artifact, not the status.
- 🔴 **`worker` means three different things.** This repo's `worker/` = BC-250 inference node;
  AgentTest's `worker/` = the Windows harness (it stays there); this repo calls that layer `client/`.
  → [`docs/settled-decisions.md`](docs/settled-decisions.md)

There is no linter or CI config — **don't invent tooling commands.**

## Work flow — three places, three jobs (user-confirmed 2026-08-09)

🔴 **Don't collapse these.** Each answers a different question, and mixing them is how the
milestone doc grew stale numbers before.

| | Answers | Rule |
|---|---|---|
| **Milestone doc** `docs/milestones/2-*.md` | *Why this order?* — chains, traps, measured evidence | 🔴 **No numerators here.** They drifted twice (중 1.3 counted 7/10 against a 13-item list; 대 1 stayed at 15 after 중 1.3 went 5→8). Keep the reasoning an issue cannot hold |
| **Redmine** `http://192.168.0.57:8080` | *Where are we, and what is open?* — **the milestone itself** | 🔴 **Version = 마일스톤 · parent issue = 중분류 · subtask = 소분류** (user-confirmed 2026-08-09). Progress is **computed**, never typed. 🔴 Only **완료(4)** is a closing status — 해결(3) still counts as open. Put the commit hash in the note |
| **`reports/`** | *Why did we decide that?* — decisions, measurements, traps | One report per session, Korean. Not a task list |

**At session start**: read the open milestone, then `GET /issues.json?status_id=open` for `[AX]`
items. **At session end**: update the issues you moved, then write the report.

🔴 **Redmine is the *same* project as the game — `ModularStage` (id 1), tracker `코드리뷰`
(user-confirmed: *"동일한 프로젝트네"*).** The AX cluster is tooling **for** that R&D, not a
separate deliverable. **Never create a new project or tracker**; distinguish with an `[AX]` subject
prefix only. Read is public; writing needs the admin API key, which is **not on disk** — pull it
from the master's own container DB. 🔴 **Never write the key value into a doc or commit.**
→ [`docs/10-references.md`](docs/10-references.md) §10.1

## Where things are

| Need | Go to |
|---|---|
| What's decided vs open | [`PLAN.md`](PLAN.md) — index of `docs/` |
| Closed decisions, don't relitigate | [`docs/settled-decisions.md`](docs/settled-decisions.md) |
| Still open | [`docs/3-open-items.md`](docs/3-open-items.md) |
| Per-machine operating guide | [`machines/`](machines/README.md) |
| **Machine inventory** — IPs, roles, what's reachable from where | [`machines/sim-desktop.md`](machines/sim-desktop.md) § Machine inventory |
| External projects, reports | [`docs/10-references.md`](docs/10-references.md) |

## What exists in code

🔴 **표는 여기 두지 않는다** — 하루에도 네 행이 늘었고, 이 파일은 매 세션에 로드되는 **색인**이다.
모듈별 설명·함정·실측은 [`master/README.md`](master/README.md) 에 있다. 여기엔 **놓치면 안 되는 것만** 남긴다.

`worker/` is still a README-only stub. **`client/` is live** — see the table row above.
🔴 **Say "done" only for a whole area.** M2 closed 2026-08-10. **대 1 of M3 is closed
(2026-08-12)** — 중 1.1 skeleton+freeze, 중 1.2 decompose, 중 1.3 inference dispatch, 중 1.4
integrator. The pipeline runs end to end: request → skeleton (`claude:opus`, built on `.2` before
registration) → decompose → workers **infer only** (`work/infer.py`, skill `ax-infer`) → responses
spooled in apply order → **integrator applies, builds with UE5, and commits only what passes**
(`work/integrate.py`, live: build 142s, commit). 🔴 **The pipeline builds per piece, not once at
the end** — §4.5's "apply everything then build once" was overturned by the measured 35–65s
incremental build, because a single build can't say *which* piece broke it.
**대 2 (3-layer gate) closed the same day** — the pipeline now has **four gates**: skeleton build,
층1 (deterministic, run at *both* response-acceptance and apply time), 층2 (commercial model with
**declaration grounding**), 층3 (per-piece UE5 build + one work-level RunTests).
🔴 **One hole remains and code cannot close it: this project has ZERO automation tests** (measured
2026-08-12 — no `AUTOMATION_TEST`/`FunctionalTest`/spec anywhere in `Source/`). §4.3's measured
*"hallucinations that compile"* (`Cast<IInteractable>`, `IsValid()` logic errors) are catchable
**only by tests**, so `RunTests` is deliberately **fail-open + loud warning** until tests exist.
🕓 Untouched: 대 3 (operator surface). When reporting status, give the denominator (read it from
Redmine), never a scope narrowed to what got built.
🔴 **Grounding, not the model, is what makes 층2 work** (measured: 4 of 5 candidates missed an
invented enum member without declarations, all caught it with them). Never call 층2 without
declarations and then read a pass as meaningful — the code reports `l2_grounded=False` for exactly
that reason. Local models are **not usable** for 층2: 35B blocked two correct files (false alarms).
🔴 **Injection tests contracts, not reality.** Four separate real defects this session lived behind
an injected seam while 63–96 unit checks passed. Put one live run behind every gate.
🔴 **Two framings that changed on 2026-08-11 — don't argue from the old ones**: the pipeline has
**one writer** (the integrator `.2` builds, then commits), and distribution buys **incremental
progress, not throughput** (measured: 2 workers = 12% faster, 90% dearer).
🔴 **Two skills go to a worker and the dispatch names which one applies**: `ax-infer` (current —
infer only, never commit) and `ax-work` (old N-writer topology). `runner.py` and `ax-work` are
**deliberately not deleted** — settled: keep the N-writer machinery reversible until measurement
overturns it (§8.4). Do not "clean up" either one.
🔴 **Content travels as files in both directions, never on the command line or stdout.** `.2`'s
console is CP949: the master→worker rule ("instructions ASCII, content by file") applies to
worker→master too — responses land in `.ax/work/<task>/response.txt` and come back by `scp`.
🔴 **The integrator's worktree is pipeline-owned; a human's tree never is.** `ax-wt-<work_id>` sits
**beside** the checkout (never inside it) and `ensure_worktree` resets it to the base commit on
reuse. That reset is safe *only* because nobody edits that tree by hand — never apply the same
reasoning to `.33`'s or a worker's main checkout.
🔴 **Never `push --force` from the integrator.** If a push is rejected, the commits stay in the
isolated tree (nothing is lost) and a human decides — the pipeline does not rewrite history.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

## Tests — 🔴 **수를 여기 적지 않는다**

하루에 여섯 번 고쳤다. 마일스톤 분자를 레드마인으로 옮긴 것과 **같은 이유**로, 수치가 아니라
**세는 법**을 적는다. pytest 는 없다 — 각 파일이 그대로 실행된다.

```bash
# 전부 돌리고 합계를 센다 (실패가 있으면 파일명이 뜬다)
for f in master/test_*.py; do .venv/bin/python "$f" 2>&1 | tail -1; done

# 한 건만
.venv/bin/python master/test_runner.py       # 워커 파견 — fail-closed 마커·계측
.venv/bin/python master/test_batching.py     # 🔴 파일 불가분 (충돌 방지)
.venv/bin/python master/test_ontology.py     # YAML 왕복·잠금 보존·사실 게이트
python3 master/test_verdict.py               # venv 없이 도는 순수 로직
```

🔴 **venv 가 필요한 것과 아닌 것이 섞여 있다** — `python3` 로 도는 것은 순수 로직뿐이고,
나머지는 `.venv/bin/python` 이다(pydantic·pyyaml·fastembed).

## 운영 명령

```bash
curl -s localhost:8102/health | python3 -m json.tool   # 노드별 상주 모델
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager              # push → 트윈 성장 이력
.venv/bin/python -m master.work.runner once            # 큐에서 한 건 파견
.venv/bin/python -m master.work.cleanup plan           # 찌꺼기 (기본은 안 지움)
.venv/bin/python -m master.ontology plan|dry|refresh   # 🔴 이 순서로
```

## Three clones — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`), BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), and GitHub.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
