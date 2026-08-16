# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

> [중요] **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- [중요] **Read which milestone you are in before planning anything.**
  **M1·M2·M4 closed ([중요] M4 closed 2026-08-17, user decision); M3 is `locked` (halted
  2026-08-13); [중요] M5 (두 버전 대조·머지) is open.**
  → [`docs/milestones/5-version-reconcile.md`](docs/milestones/5-version-reconcile.md) —
  numbers live in Redmine (version *마일스톤 5*; 3 items at open). M5 = 판정: M4 이식 중
  「우리 방식 vs 원전 방식」으로 갈린 자리들을 **둘 다 읽고 실측해서** 고른다. 진 쪽은
  부활 조건과 함께 닫는다 (「미정」 금지 — 사용자 2026-08-16).
  [주의] **The M4 paragraph below is a closed milestone's record, not a current instruction** —
  its traps (citation-first, census limits, topology) still bind; its scope/counts do not.
  M4's own 「여기서 배운 것」 (왕복이 계약 · 원전 기본값 확인 · 확정 결정 > 원전 코드) is in
  its milestone doc.
  [중요] **M4 is not a feature milestone — it is consistency.** An origin-citation census (report 14)
  measured **74 files / 23,710 lines of `~/AgentTest` never once mentioned in this repo**, and the
  worst hit is the topology: `cluster_coordinator.py`'s `verify_and_merge` already said
  *"durable 단일 writer 보존"* — **that writer is the server, and workers push ephemeral
  `attempt/` branches.** Linux forces exactly **one** change: the UE5 build step inside
  `verify_and_merge` moves to `.2`. Everything I redesigned beyond that was redesign, not a port.
  [중요] **Do not argue the topology from M3's docs** — its label *"사용자 확정 2026-08-11"* is wrong
  (it was *"그래 해"* after I pushed it), and `settled-decisions.md` §214 carries the same bad label.
  [중요] **Before building anything, read the origin and leave a citation.** Never-cited must-reads:
  `local_llm_distributed_workers_plan_v5.0.md` (463, user-confirmed C.1–C.7/κ.0),
  `.agents/AGENTS.md` (21 — its rule 3 *is* 애매하면 묻는다), `.claude/reviews/_silent_failure/
  audit_matrix.md` (99 — the σ audit method), `plan_completed_v4.5.md` (2397 — what already exists).
  **Read only the open milestone** — closed ones are reference; don't load them. Progress
  lives in the milestone doc, never in the design docs (`docs/1`–`docs/10`, always current).
  [중요] **Neither the numerator nor the denominator is written in any document** — read both from
  Redmine (version *마일스톤 4*). Hand-kept numerators drifted twice in M2, and the denominator
  moves whenever reading the origin uncovers work: M3 went 32 → 36, and M4 has moved **four times**
  (62 → 75 → 80 → 81) as later ports kept surfacing their own missing halves. That movement is
  normal — record it. [주의] **Those figures are history, not the current count** — this very line went
  stale inside one session (2026-08-16), which is why the rule above exists. Never quote them as state.
  M4 structure: 대 4 / 중 17 — **소분류가 작업 단위다**. 대 1 topology restore · 대 2 turn the
  four open M3 items into ports · 대 3 un-ported assets · 대 4 recover the method/norms.
  Never size a task by line count: `class_graph`'s 1,341 lines turn out to be
  *"delete the file → full rescan on restart"*.
  [중요] **Two M2 rules that still bind here**: never bulk-regenerate the 1,055 snapshot docs (our
  local model measured *worse* than the received snapshot), and never hand-tune search weights
  before there is an answer set. M2's **「여기서 배운 것」** section is the short list of traps
  not to re-enter — read it once before starting a new area.
  [중요] **Do not pick the next task yourself** — M1 failed that way (I chose an order, dug into one
  piece, declared it "complete", repeated). The order is the user's call.
- [중요] **애매하면 묻는다 — 임의 판단으로 좁히지 않는다** (사용자 2026-08-13, 세 번 반복된 실패 ·
  원전 3조). 애매함은 둘이다: **설계의 갈림길**, 그리고 [중요] **「작업 지시인지 단순 질문인지」**.
  [주의] **짧은 수긍(`응`·`그래`)이 가장 위험하다 — 앞에 물음이 없었으면 승인이 아니라 수긍일 수 있다**
  (실측: 한 세션에서 `응` 이 두 번, 하나만 승인이었다). **내가 방금 무엇을 물었는지 확인하고 답과
  맞물리는지 본다.**
- [중요] **만들기 전에 원전(`~/AgentTest`)과 기존 자산을 읽는다** — 대부분의 요구에는 이미 만들어진
  것이 있다. 안 읽고 만들면 요구를 좁힌다(그렇게 잃은 것 셋: 로컬 파일 웹 UI · 읽기 전용 화면의
  로그인 · 원전 3,700줄을 안 읽고 새로 쓴 229줄 뷰어). [중요] **제약 하나를 지키려고 요구를 희생하면
  결과물은 못 쓴다.**
- [중요] **이식이 우리 자산을 덮지 않는지 먼저 본다 — `verified_by_user` *와* `protected` 는 함께
  본다.** 원전에 없는 **우리 개념**(받아온 스냅샷 보호)이 이식의 **안전 조건**이다. 실측
  2026-08-15 에 같은 부류가 두 번 — 원전 무효화를 그대로 옮겼으면 스냅샷 **37건**이 선삭제됐고,
  레이어 서술 이식은 트윈에 이미 있던 **원전 산출물 7건**(미잠금)을 덮을 뻔했다. [중요] **둘 다
  착수 전 실측이 잡았다 — 코드를 돌리기 전에 그 자리에 무엇이 있는지 보라.**
  → `reports/17-*.md` §4·§14
- [중요] **자동 로드 문서(`CLAUDE.md` 전부)와 게임 소스는 고치기 전에 계획을 말하고 동의를 받는다**
  (원전 1조, **범위는 사용자 결정 2026-08-14**). 도구 코드는 커밋 승인 게이트가 그 역할을 한다.
- [중요] **승인을 구할 때 검토 비용을 사용자에게 넘기지 않는다** (원전 4조) — **무엇을·어디를·왜**와
  **측정 결과**를 함께 낸다. *"커밋할까요?"* 만 던지면 그건 승인이 아니라 전가다.

  → 위 네 규칙의 근거·실측·범위와 **원전 5조 대조표**(무엇을 안 옮겼나 포함):
  [`docs/11-agent-conduct.md`](docs/11-agent-conduct.md)
- [중요] **The GitHub remote is private. Keep it that way** — it contains LAN addresses and firewall rules.
- [중요] **The master is infrastructure, not a workshop** — [주의] **narrowed 2026-08-14, don't read the
  old absolute.** It assembles context and hands it over; the Windows PC builds and tests.
  [중요] **Flow Y (user-confirmed 2026-08-14) gives the master exactly one write capability**: it
  commits inferred diffs to `attempt/<task>/<workshop>/<ts>` and merges verified ones into
  `task/<id>` — nothing else. So *"files never leave Windows"* and *"no file I/O on the master"*
  are **no longer true as written**; what holds is **the master never touches `main`** and never
  builds. Mechanism: `master/work/attempt.py`, a push-only second remote `gitea-write`, and a
  `pre-push` hook that rejects every ref outside `attempt/*`·`task/*` (deletions only when the tip
  is reachable from `<remote>/main`). The 정본 clone's `origin` push stays sealed as a loud guard.
  → [`docs/2-architecture.md`](docs/2-architecture.md) §2.2-1 · `reports/16-master-write-surface.md`
- [중요] **All three services require a bearer token** (`task_queue` 8101, broker 8102, projects 8103).
  Token: `~/.config/ax-cluster/token`, 0600, **fail-closed — a service will not start without it**.
  Send `Authorization: Bearer <token>`; only `/livez` is open. They are *also* ufw LAN-only —
  **never widen those rules to `Anywhere`.** Two layers, not one instead of the other.
  → `master/auth.py`, PLAN §9.5.6
- [중요] **`/home/sim/AgentTest` is reference-only — never modify or push to it.** Port code *out* of it.
- [중요] **Never commit or push without asking first** (user, 2026-08-14: *"커밋은 나에게 허락을
  요구해줄래?"*). Prepare the message, **ask**, run only after approval. [중요] **The origin's rule is
  stricter (*"forbidden even when told"*) and ours is looser because the *user* chose it** — no
  SourceTree on Linux. Keep that label straight. [중요] **빌드·배포·데몬 재기동도 같다** — 대화형
  세션이 `.2` 의 UE5 빌드나 서비스 재기동을 **임의로 돌리지 않는다**(원전 5조; 목적은 위험 분리).
  [주의] **파이프라인이 커밋하거나 빌드하는 것은 무관하다** — 설계된 동작이다.
  → [`docs/11-agent-conduct.md`](docs/11-agent-conduct.md) §11.5
- [중요] **Human sessions: never run** `push --force`, `reset --hard`, branch/tag deletion, `rebase`, or
  history rewriting — **not even with approval**; describe the command instead. Don't read a
  first-person statement ("I'll commit and come back") as an instruction to you — that exact
  misreading caused an incident in AgentTest (*"다 지워진 줄 알고 깜짝 놀랐다"*).
  [주의] **Pipeline code committing is a different thing** — the integrator/worker writing to
  `attempt`/`durable` branches is designed behavior; these rules bind the *interactive session*.
  → [`docs/8-git-authority.md`](docs/8-git-authority.md)
- [중요] **Never trust a delegated backend's "done".** Measured 2026-08-07: `agy` returned
  `status:"SUCCESS"` while writing no file. Verify the artifact, not the status.
- [중요] **`worker` means three different things.** This repo's `worker/` = BC-250 inference node;
  AgentTest's `worker/` = the Windows harness (it stays there); this repo calls that layer `client/`.
  → [`docs/settled-decisions.md`](docs/settled-decisions.md)

There is no linter or CI config — **don't invent tooling commands.**

## Work flow — three places, three jobs (user-confirmed 2026-08-09)

[중요] **Don't collapse these.** Each answers a different question, and mixing them is how the
milestone doc grew stale numbers before.

| | Answers | Rule |
|---|---|---|
| **Milestone doc** `docs/milestones/2-*.md` | *Why this order?* — chains, traps, measured evidence | [중요] **No numerators here.** They drifted twice (중 1.3 counted 7/10 against a 13-item list; 대 1 stayed at 15 after 중 1.3 went 5→8). Keep the reasoning an issue cannot hold |
| **Redmine** `http://192.168.0.57:8080` | *Where are we, and what is open?* — **the milestone itself** | [중요] **Version = 마일스톤 · parent issue = 중분류 · subtask = 소분류** (user-confirmed 2026-08-09). Progress is **computed**, never typed. [중요] Only **완료(4)** is a closing status — 해결(3) still counts as open. Put the commit hash in the note |
| **`reports/`** | *Why did we decide that?* — decisions, measurements, traps | One report per session, Korean. Not a task list |

**At session start**: read the open milestone, then `GET /issues.json?status_id=open` for `[AX]`
items. **At session end**: update the issues you moved, then write the report.

[중요] **Redmine is the *same* project as the game — `ModularStage` (id 1), tracker `코드리뷰`
(user-confirmed: *"동일한 프로젝트네"*).** The AX cluster is tooling **for** that R&D, not a
separate deliverable. **Never create a new project or tracker**; distinguish with an `[AX]` subject
prefix only. Read is public; writing needs the admin API key, which is **not on disk** — pull it
from the master's own container DB. [중요] **Never write the key value into a doc or commit.**
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

[중요] **표는 여기 두지 않는다** — 하루에도 네 행이 늘었고, 이 파일은 매 세션에 로드되는 **색인**이다.
모듈별 설명·함정·실측은 [`master/README.md`](master/README.md) 에 있다. 여기엔 **놓치면 안 되는 것만** 남긴다.

`worker/` is still a README-only stub. **`client/` is live** — see the table row above.
[중요] **Say "done" only for a whole area.** M2 closed 2026-08-10. **대 1 of M3 is closed
(2026-08-12)** — 중 1.1 skeleton+freeze, 중 1.2 decompose, 중 1.3 inference dispatch, 중 1.4
integrator. The pipeline runs end to end: request → skeleton (`claude:opus`, built on `.2` before
registration) → decompose → workers **infer only** (`work/infer.py`, skill `ax-infer`) → responses
spooled in apply order → **integrator applies, builds with UE5, and commits only what passes**
(`work/integrate.py`, live: build 142s, commit). [중요] **The pipeline builds per piece, not once at
the end** — §4.5's "apply everything then build once" was overturned by the measured 35–65s
incremental build, because a single build can't say *which* piece broke it.
**대 2 (3-layer gate) closed the same day** — the pipeline now has **four gates**: skeleton build,
층1 (deterministic, run at *both* response-acceptance and apply time), 층2 (commercial model with
**declaration grounding**), 층3 (per-piece UE5 build + one work-level RunTests).
[중요] **One hole remains and code cannot close it: this project has ZERO automation tests** (measured
2026-08-12 — no `AUTOMATION_TEST`/`FunctionalTest`/spec anywhere in `Source/`). §4.3's measured
*"hallucinations that compile"* (`Cast<IInteractable>`, `IsValid()` logic errors) are catchable
**only by tests**, so `RunTests` is deliberately **fail-open + loud warning** until tests exist.
[대기] Untouched: 대 3 (operator surface). When reporting status, give the denominator (read it from
Redmine), never a scope narrowed to what got built.
[중요] **Grounding, not the model, is what makes 층2 work** (measured: 4 of 5 candidates missed an
invented enum member without declarations, all caught it with them). Never call 층2 without
declarations and then read a pass as meaningful — the code reports `l2_grounded=False` for exactly
that reason. Local models are **not usable** for 층2: 35B blocked two correct files (false alarms).
[중요] **Injection tests contracts, not reality.** Four separate real defects this session lived behind
an injected seam while 63–96 unit checks passed. Put one live run behind every gate.
[중요] **Two framings that changed on 2026-08-11 — don't argue from the old ones**: the pipeline has
**one writer** (the integrator `.2` builds, then commits), and distribution buys **incremental
progress, not throughput** (measured: 2 workers = 12% faster, 90% dearer).
[중요] **Two skills go to a worker and the dispatch names which one applies**: `ax-infer` (current —
infer only, never commit) and `ax-work` (old N-writer topology). `runner.py` and `ax-work` are
**deliberately not deleted** — settled: keep the N-writer machinery reversible until measurement
overturns it (§8.4). Do not "clean up" either one.
[중요] **Content travels as files in both directions, never on the command line or stdout.** `.2`'s
console is CP949: the master→worker rule ("instructions ASCII, content by file") applies to
worker→master too — responses land in `.ax/work/<task>/response.txt` and come back by `scp`.
[중요] **The integrator's worktree is pipeline-owned; a human's tree never is.** `ax-wt-<work_id>` sits
**beside** the checkout (never inside it) and `ensure_worktree` resets it to the base commit on
reuse. That reset is safe *only* because nobody edits that tree by hand — never apply the same
reasoning to `.33`'s or a worker's main checkout.
[중요] **Never `push --force` from the integrator.** If a push is rejected, the commits stay in the
isolated tree (nothing is lost) and a human decides — the pipeline does not rewrite history.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

## Tests — [중요] **수를 여기 적지 않는다**

하루에 여섯 번 고쳤다. 마일스톤 분자를 레드마인으로 옮긴 것과 **같은 이유**로, 수치가 아니라
**세는 법**을 적는다. pytest 는 없다 — 각 파일이 그대로 실행된다.

```bash
# 전부 돌리고 합계를 센다 — [중요] **판정은 종료코드로, 수치는 두 형식 모두 읽는다**
# (옛 `| tail -1` 은 틀렸다: ① 마지막 줄이 구분선인 파일 13개를 못 셌고 ② 크래시한 파일은
#  수치를 안 찍어 **합계가 그대로 보였다** — 2026-08-14 에 import 실수로 3개가 죽었는데
#  합계가 안 변해서 못 봤다. 실패는 rc 로, 수치는 두 형식으로.)
fail=0; pass=0; total=0
for f in master/test_*.py; do
  out=$(.venv/bin/python "$f" 2>&1); rc=$?
  n=$(echo "$out" | grep -oE '[0-9]+/[0-9]+ 통과' | tail -1 | grep -oE '[0-9]+/[0-9]+')   # 형식 A
  if [ -n "$n" ]; then pass=$((pass+${n%%/*})); total=$((total+${n##*/}))
  else                                                                                    # 형식 B
    a=$(echo "$out" | grep -oE '통과 [0-9]+' | tail -1 | grep -oE '[0-9]+')
    b=$(echo "$out" | grep -oE '실패 [0-9]+' | tail -1 | grep -oE '[0-9]+')
    [ -n "$a" ] && { pass=$((pass+a)); total=$((total+a+${b:-0})); } || echo "수치 못 읽음: $f"
  fi
  [ $rc -ne 0 ] && { echo "[중요] rc=$rc $f"; fail=$((fail+1)); }
done
echo "$pass/$total 통과 · 실패 파일 $fail개"

# 한 건만
.venv/bin/python master/test_runner.py       # 워커 파견 — fail-closed 마커·계측
.venv/bin/python master/test_batching.py     # [중요] 파일 불가분 (충돌 방지)
.venv/bin/python master/test_ontology.py     # YAML 왕복·잠금 보존·사실 게이트
python3 master/test_verdict.py               # venv 없이 도는 순수 로직
```

[중요] **venv 가 필요한 것과 아닌 것이 섞여 있다** — `python3` 로 도는 것은 순수 로직뿐이고,
나머지는 `.venv/bin/python` 이다(pydantic·pyyaml·fastembed).

## 운영 명령

```bash
curl -s localhost:8102/health | python3 -m json.tool   # 노드별 상주 모델
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager              # push → 트윈 성장 이력
.venv/bin/python -m master.work.runner once            # 큐에서 한 건 파견
.venv/bin/python -m master.work.cleanup plan           # 찌꺼기 (기본은 안 지움)
.venv/bin/python -m master.ontology plan|dry|refresh   # [중요] 이 순서로
```

## Three clones — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`), BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), and GitHub.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
