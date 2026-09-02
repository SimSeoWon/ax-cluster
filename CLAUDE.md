# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

> [중요] **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- [중요] **세션 시작에 이 둘을 먼저 읽는다 — 조건부가 아니다** (사용자 2026-08-22):
  **① 열린 마일스톤** [`docs/milestones/6-improvements.md`](docs/milestones/6-improvements.md)
  · **② 지금 열린 축의 지도** [`docs/12-multi-project.md`](docs/12-multi-project.md).
  둘 다 읽지 않고 코드부터 grep 하면 규칙을 코드에서 알아내려 하게 된다 — 2026-08-21 세션이
  그렇게 §11.5(데몬 재기동)를 어겼다. [주의] **항목·진행은 레드마인만** 본다.
  **M1–M5 all closed (M3·M4·M5 closed 2026-08-17, user decisions); M6
  (개선·확장) is open.**
  → [`docs/milestones/6-improvements.md`](docs/milestones/6-improvements.md) —
  numbers live in Redmine (version *마일스톤 6*). 개선은 실측이 앞선다 — 검색 관련은
  **정답 집합 없이 손대지 않는다** (M2 규칙). M5 의 판정들(git-carried·한글 베이스 머지·
  중앙화 가드)은 부활 조건과 함께 닫혔다 — `5-version-reconcile.md` 「여기서 배운 것」.
  [주의] **What follows are the traps that still bind — not the closed milestones' scope or counts**
  (those are in Redmine and the closed milestone docs; M4's own 「여기서 배운 것」 too).
  🔴 **The topology is the user's 정본 7단계 (사용자 확정 2026-09-02)** — memory
  `distributed-pipeline-intended-shape`. **The worker commits to its own sub-branch and asks for
  the next task.** Linux forces exactly **one** change: the UE5 build step inside
  `verify_and_merge` moves to `.2`. Everything I redesigned beyond that was redesign, not a port.
  🔴 [중요] **And the citation I redesigned it with was a misquote** (found 2026-09-02):
  `cluster_coordinator.verify_and_merge`'s docstring is *"**검증 워커**: … durable 단일 writer
  보존"* — the writer is the **verifying worker**, not the server (Plan v5 C.3: *"verify 를 서버
  단독에서 **워커 역할로 풀었다**"*), and *"단일 writer"* is an **epoch-fencing invariant**, not a
  claim that the pipeline has one writer. **No origin mode leaves git untouched by the worker**:
  pull mode pushes `worker/<host>/<task_id>` → server squash-merges into feature; push mode
  pushes ephemeral `attempt/…` → verifying worker merges into durable.
  [중요] **Do not argue the topology from M3's docs** — its label *"사용자 확정 2026-08-11"* is wrong
  (it was *"그래 해"* after I pushed it), and `settled-decisions.md` §214 carries the same bad label.
  [중요] **Before building anything, read the origin and leave a citation.** Must-reads (M4 때
  인용 0이었던 넷 — 2026-08-17 census 로 전부 인용 확인):
  `local_llm_distributed_workers_plan_v5.0.md` (463, user-confirmed C.1–C.7/κ.0),
  `.agents/AGENTS.md` (21 — its rule 3 *is* 애매하면 묻는다), `.claude/reviews/_silent_failure/
  audit_matrix.md` (99 — the σ audit method), `plan_completed_v4.5.md` (2397 — what already exists).
  [중요] **만들기 전에 census**: `python3 master/census.py <원전파일>` — 인용 0이면 실물부터
  연다. 절차와 census 의 양방향 한계(인용됨≠읽음 · 인용0≠미이식):
  `docs/11-agent-conduct.md` §11.2.1.
  **Read only the open milestone** — closed ones are reference; don't load them. Progress
  lives in the milestone doc, never in the design docs (`docs/1`–`docs/10`, always current).
  [중요] **Neither the numerator nor the denominator is written in any document** — read both from
  Redmine. Hand-kept numerators drifted twice in M2, and the denominator moves whenever reading the
  origin uncovers work (M3 32 → 36; M4 four times). That movement is normal — record it in Redmine,
  and **never quote a figure from a document as state**: this very line went stale inside one
  session (2026-08-16). **소분류가 작업 단위다.**
  Never size a task by line count: `class_graph`'s 1,341 lines turn out to be
  *"delete the file → full rescan on restart"*.
  [중요] **Two M2 rules that still bind here**: never bulk-regenerate the 1,055 snapshot docs (our
  local model measured *worse* than the received snapshot), and never hand-tune search weights
  before there is an answer set. M2's **「여기서 배운 것」** section is the short list of traps
  not to re-enter — read it once before starting a new area.
  [중요] **Do not pick the next task yourself** — M1 failed that way (I chose an order, dug into one
  piece, declared it "complete", repeated). The order is the user's call.
- [중요] **애매하면 묻는다 — 임의 판단으로 좁히지 않는다** (사용자 2026-08-13, 세 번 반복된 실패 ·
  원전 3조). 애매함은 둘이다: **설계의 갈림길**, 그리고 **「작업 지시인지 단순 질문인지」**.
  [주의] **짧은 수긍(`응`·`그래`)이 가장 위험하다 — 앞에 물음이 없었으면 승인이 아니라 수긍일 수 있다**
  (실측: 한 세션에서 `응` 이 두 번, 하나만 승인이었다). **내가 방금 무엇을 물었는지 확인하고 답과
  맞물리는지 본다.**
- [중요] **만들기 전에 원전(`~/AgentTest`)과 기존 자산을 읽는다** — 대부분의 요구에는 이미 만들어진
  것이 있다. 안 읽고 만들면 요구를 좁힌다(그렇게 잃은 것 셋: 로컬 파일 웹 UI · 읽기 전용 화면의
  로그인 · 원전 3,700줄을 안 읽고 새로 쓴 229줄 뷰어). **제약 하나를 지키려고 요구를 희생하면
  결과물은 못 쓴다.**
- [중요] **이식이 우리 자산을 덮지 않는지 먼저 본다 — `verified_by_user` *와* `protected` 는 함께
  본다.** 원전에 없는 **우리 개념**(받아온 스냅샷 보호)이 이식의 **안전 조건**이다. 실측
  2026-08-15 에 같은 부류가 두 번 — 원전 무효화를 그대로 옮겼으면 스냅샷 **37건**이 선삭제됐고,
  레이어 서술 이식은 트윈에 이미 있던 **원전 산출물 7건**(미잠금)을 덮을 뻔했다. **둘 다
  착수 전 실측이 잡았다 — 코드를 돌리기 전에 그 자리에 무엇이 있는지 보라.**
  → `reports/17-*.md` §4·§14
- [중요] **자동 로드 문서(`CLAUDE.md` 전부)와 게임 소스는 고치기 전에 계획을 말하고 동의를 받는다**
  (원전 1조, **범위는 사용자 결정 2026-08-14**). 도구 코드는 커밋 승인 게이트가 그 역할을 한다.
- [중요] **승인을 구할 때 검토 비용을 사용자에게 넘기지 않는다** (원전 4조) — **무엇을·어디를·왜**와
  **측정 결과**를 함께 낸다. *"커밋할까요?"* 만 던지면 그건 승인이 아니라 전가다.

  → 위 네 규칙의 근거·실측·범위와 **원전 5조 대조표**(무엇을 안 옮겼나 포함):
  [`docs/11-agent-conduct.md`](docs/11-agent-conduct.md)
- [중요] **The GitHub remote is private. Keep it that way** — it contains LAN addresses and firewall rules.
- **The master is infrastructure, not a workshop** — **narrowed 2026-08-14, don't read the
  old absolute.** It assembles context and hands it over; the Windows PC builds and tests.
  🔴 [중요] **Write authority under 정본 7단계**: the **requester** owns `task/<work>/base`
  (골조), the **worker** commits its piece to its own sub-branch off that base (⑸), and the
  master creates those sub-branches and integrates on approval (⑷·⑺). What still holds without
  qualification: **the master never touches `main`** and never builds.
  [주의] **Today's code does none of ⑸** — workers infer, the invented 「통합자」 is the sole writer, and
  passing pieces pile onto `task/<work>/base` (`e3a318f` left no sub-branch at all). Flow Y
  (2026-08-14, *"master commits inferred diffs to the durable branch"*) and the `#327` teardown of
  the `attempt/` tier are **the redesign, superseded by the 7 steps** — `#327` argued from *"0
  production callers"*, which is circular for a path nobody wired. Mechanism as built today:
  `master/work/carry.py`, a
  push-only second remote `gitea-write`, and a `pre-push` hook that rejects every ref outside
  `attempt/*`·`task/*` (deletions only when the tip is reachable from `<remote>/main`).
  [주의] `attempt/*` stays in that allowlist only for **legacy debris cleanup**
  (`attempt.plan_remote_cleanup`). The 정본 clone's `origin` push stays sealed as a loud guard.
  → [`docs/2-architecture.md`](docs/2-architecture.md) §2.2-1 · `reports/16-master-write-surface.md`
- [중요] **All three services require a bearer token** (`task_queue` 8101, broker 8102, projects 8103).
  Token: `~/.config/ax-cluster/token`, 0600, **fail-closed — a service will not start without it**.
  Send `Authorization: Bearer <token>`; only `/livez` is open. They are *also* ufw LAN-only —
  **never widen those rules to `Anywhere`.** Two layers, not one instead of the other.
  → `master/auth.py`, PLAN §9.5.6
- [중요] **`/home/sim/AgentTest` is reference-only — never modify or push to it.** Port code *out* of it.
- [중요] **Never commit or push without asking first** (user, 2026-08-14: *"커밋은 나에게 허락을
  요구해줄래?"*). Prepare the message, **ask**, run only after approval. **The origin's rule is
  stricter (*"forbidden even when told"*) and ours is looser because the *user* chose it** — no
  SourceTree on Linux. Keep that label straight. [중요] **빌드·배포·데몬 재기동도 같다** — 대화형
  세션이 `.2` 의 UE5 빌드나 서비스 재기동을 **임의로 돌리지 않는다**(원전 5조; 목적은 위험 분리).
  [주의] **파이프라인이 커밋하거나 빌드하는 것은 무관하다** — 설계된 동작이다.
  → [`docs/11-agent-conduct.md`](docs/11-agent-conduct.md) §11.5
- [중요] **파괴적 git 연산은 「물어보고 → 승인받고 → 실행」이다** (사용자 결정 2026-08-30 —
  종전의 「승인이 있어도 금지, 명령을 대신 적어 준다」를 **한 단계 낮춰 대체한다**):
  `push --force`, `reset --hard`, 브랜치/태그 삭제, `rebase`, 히스토리 재작성.
  종전 규칙은 실증 중 엉킨 상태를 정리해야 하는 자리에서 **매번 사람에게 명령을 떠넘겨** 흐름을
  끊었다. 문제였던 것은 *실행 자체*가 아니라 **내 멋대로 지우는 것**이므로, 막는 대신 **매번
  묻는다.**
  [중요] **묻는 자리에 지울 목록을 함께 보여 준다.** 되살릴 수 없는 것(그 기계에만 있는
  커밋·에셋)은 그 자리에서 표시한다 — 사람이 모르고 지우게 두지 않는다.
  [주의] **일인칭 서술("커밋하고 올게")을 지시로 읽지 않는다.** 그 오독이 AgentTest 에서 사고를
  냈다(*"다 지워진 줄 알고 깜짝 놀랐다"*). 앞선 지시가 있어도 **삭제 직전에 한 번 더 확인한다.**
  [주의] **Pipeline code committing is a different thing** — the integration step writing to the durable
  `task/<work>/<task>` branch is designed behavior; these rules bind the *interactive session*.
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
| **Redmine** `http://192.168.0.57:8080` | *Where are we, and what is open?* — **the milestone itself** | [중요] **Version = 마일스톤 · parent issue = 중분류 · subtask = 소분류** (user-confirmed 2026-08-09). Progress is **computed**, never typed. Only **완료(4)** is a closing status — 해결(3) still counts as open. Put the commit hash in the note |
| **`reports/`** | *Why did we decide that?* — decisions, measurements, traps | One report per session, Korean. Not a task list |
| **Redmine 위키 [[아이디어수집]]** | *What might we build someday?* — 미정 아이디어의 본문 | [중요] **일감이 아니다** (사용자 개설 2026-08-17). 항목 = 위키 절 + 버전 「아이디어 — 추후 검토 수집」의 이슈. 진행·집계 금지, 착수 결정 시 실 마일스톤으로 이동 |

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
| [중요] **지금 열린 축 — 다중 프로젝트** | [`docs/12-multi-project.md`](docs/12-multi-project.md) — 갈린 축과 안 갈린 축 · 네 부모 일감의 지도. [완료] **마운트 강제는 2026-08-22 배선됐다**(3단계 전부) · [주의] §12.4 는 그 전의 「안 된 것을 됐다고 적은」 거짓 서술 네 곳을 정정한 기록이다 |
| [중요] **요청 태그 계약** (기능 정본) | [`docs/13-request-tagging.md`](docs/13-request-tagging.md) — 네 정책 · 필수 표면 · 거절 사유 셋 · 발신자 · [주의] **발신자 배달이 서버 조임보다 먼저다**(§13.6) |
| [중요] **신규 프로젝트 온보딩** (실행용) | [`docs/14-onboarding-runbook.md`](docs/14-onboarding-runbook.md) — 명령 단위 절차 + 단계별 **「안 됐으면 무엇이 안 보이나」** |
| Closed decisions, don't relitigate | [`docs/settled-decisions.md`](docs/settled-decisions.md) |
| Still open | [`docs/3-open-items.md`](docs/3-open-items.md) |
| Per-machine operating guide | [`machines/`](machines/README.md) |
| **Machine inventory** — IPs, roles, what's reachable from where | [`machines/sim-desktop.md`](machines/sim-desktop.md) § Machine inventory |
| External projects, reports | [`docs/10-references.md`](docs/10-references.md) |

## What exists in code

[중요] **표는 여기 두지 않는다** — 하루에도 네 행이 늘었고, 이 파일은 매 세션에 로드되는 **색인**이다.
모듈별 설명·함정·실측은 [`master/README.md`](master/README.md) 에 있다. 여기엔 **놓치면 안 되는 것만** 남긴다.

`worker/` is still a README-only stub. [중요] **`client/` (repo root) = what runs on the client;
`master/client/` = the deliverer. The criterion is *where it runs* — `master/` is this infra server**
(#263). [주의] **Delivered paths did NOT move** — clients still get `.ax/lib/axmaster/clientside/`;
source vs delivered are two fields now (#262). Detail: [`client/README.md`](client/README.md).
[중요] **Say "done" only for a whole area** — and when reporting status, give the denominator (read it
from Redmine), never a scope narrowed to what got built.
The pipeline runs end to end with **four gates**: skeleton build (`claude:opus`, built on `.2` before
registration) → 층1 (deterministic, at *both* response-acceptance and apply time) → 층2 (commercial
model with **declaration grounding**) → 층3 (per-piece UE5 build + one work-level RunTests).
**It builds per piece, not once at the end** — §4.5's "apply everything then build once" was
overturned by the measured 35–65s incremental build, because a single build can't say *which*
piece broke it. [주의] The gates are **not** what 정본 7단계 changes; they stay.
🔴 [주의] **What is wrong today: workers `infer only` (`work/infer.py`, skill `ax-infer`) and the
「통합자」 is the sole writer.** 정본 ⑸ has the worker commit to its own sub-branch. The
`ax-work` skill and `work/runner.py` hold that path and are **deliberately not deleted** — they
are the restoration material, not dead code.
[중요] **One hole remains and code cannot close it: this project has ZERO automation tests** (measured
2026-08-12 — no `AUTOMATION_TEST`/`FunctionalTest`/spec anywhere in `Source/`). §4.3's measured
*"hallucinations that compile"* (`Cast<IInteractable>`, `IsValid()` logic errors) are catchable
**only by tests**, so `RunTests` is deliberately **fail-open + loud warning** until tests exist.
[중요] **Grounding, not the model, is what makes 층2 work** (measured: 4 of 5 candidates missed an
invented enum member without declarations, all caught it with them). Never call 층2 without
declarations and then read a pass as meaningful — the code reports `l2_grounded=False` for exactly
that reason. Local models are **not usable** for 층2: 35B blocked two correct files (false alarms).
[중요] **Injection tests contracts, not reality.** Four separate real defects this session lived behind
an injected seam while 63–96 unit checks passed. Put one live run behind every gate.
🔴 [중요] **The "one writer" framing is dead — superseded by 정본 7단계 (2026-09-02).** Its label
*"user-confirmed 2026-08-11"* was already known to be wrong (`settled-decisions.md:251` strikes it
through as mislabeled — it was *"그래 해"* after I pushed it). Do not argue from it.
What **does** still hold from that date: distribution buys **incremental progress, not
throughput** (measured: 2 workers = 12% faster, 90% dearer) — user-reframed, and unrelated to who
writes.
[중요] **Two skills go to a worker and the dispatch names which one applies**: `ax-work`
(**the 정본 direction** — worker commits to its sub-branch) and `ax-infer` (what runs today —
infer only, never commit). Neither may be "cleaned up": `ax-work`+`runner.py` are the restoration
material for ⑸, and `ax-infer` is what the live pipeline still calls.
[중요] **Content travels as files in both directions, never on the command line or stdout.** `.2`'s
console is CP949: the master→worker rule ("instructions ASCII, content by file") applies to
worker→master too — responses land in `.ax/work/<task>/response.txt` and come back by `scp`.
[중요] **The integration worktree is pipeline-owned; a human's tree never is.** `ax-wt-<work_id>` sits
**beside** the checkout (never inside it) and `ensure_worktree` resets it to the base commit on
reuse. That reset is safe *only* because nobody edits that tree by hand — never apply the same
reasoning to `.33`'s or a worker's main checkout.
[중요] **Never `push --force` from the integration step.** If a push is rejected, the commits stay in the
isolated tree (nothing is lost) and a human decides — the pipeline does not rewrite history.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

## Tests — [중요] **수를 여기 적지 않는다**

하루에 여섯 번 고쳤다. 마일스톤 분자를 레드마인으로 옮긴 것과 **같은 이유**로, 수치가 아니라
**세는 법**을 적는다. pytest 는 없다 — 각 파일이 그대로 실행된다.

```bash
# 전부 돌리고 합계를 센다 — **판정은 종료코드로, 수치는 두 형식 모두 읽는다**
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
.venv/bin/python master/test_batching.py     # 파일 불가분 (충돌 방지)
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
.venv/bin/python -m master.work.infer collect          # pull 데몬 응답 회수 → 스풀 (#204)
.venv/bin/python -m master.work.integrate plan|run     # 통합 (조각별 빌드 → 커밋 → durable push)
.venv/bin/python -m master.work.cleanup plan|apply     # 찌꺼기 (plan 은 안 지움 · verified·cancelled 만)
.venv/bin/python -m master.work.cleanup remote --apply # 병합 확인된 원격 attempt/task 삭제 (#219)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client probe|plan|deliver|check
                                                       # 배달 — check 가 스킬·payload·작업장 자산 31개를 해시로 잰다
.venv/bin/python -m master.ontology plan|dry|refresh   # 이 순서로
.venv/bin/python -m master.ontology log-candidates     # 태깅 권장 리포트 (#169, LLM 0)
```

[중요] **승인 뒤는 한 호출이다** (원전 6단계 동등, 2026-08-21): `review.finalize_work(confirm=True)` 가 ①`main` `--no-ff` 머지+push ②Redmine 완료 기재(머지 커밋 해시 · 상태는 **「해결」** — 「완료」로 닫는 것은 사람이다) ③**도달 가능한 브랜치 삭제** ⑤`merge_status`→`merged` 를 이어서 한다. `confirm=False`(기본)는 **통합만 하고 멈추고** 사람이 실행할 명령을 돌려준다. [주의] 순서가 계약이다 — 정리는 **머지 뒤**여야 도달 가능 판정이 참이 된다.

🔴 [주의] **아래는 「지금 도는 것」이고 정본이 아니다.** 정본 ⑸ 는 **워커가 끝내고 다음 작업을
요청**하는 것(= 상주 폴링)이므로, `#320` 의 상주 철거는 **되돌릴 목록**에 있다. 원전도 워커
데몬이 `poll → claim → LLM → commit·push → submit → 다시 claim` 을 돈다.

[중요] **상주 데몬은 없다 — 마스터가 SSH 로 민다** (`#320` 철거 2026-08-27, `#317` 미결 ⑤).
`.2` 의 `AxClaimer_NS` schtasks 와 `.43` 의 cron 감시자를 **둘 다 걷었다.** 지금 큐를 폴링하는
프로세스는 어느 워커에도 없다 — 파견은 전부 마스터가 건다(`run_build_on_workshop` 이
`Build.bat` 를 직접 부르므로 **빌드에는 워커에 파이썬 페이로드가 필요 없다**).
[완료] **그러나 「등재해도 아무도 집지 않는다」는 2026-09-01 부터 틀리다** (`#340`,
`c33316e`·`9cc73d9`). 상주가 없는 것은 그대로이고, 그 자리를 **마스터의 유닛이 잇는다**:
골조 push 이벤트 → `ax-dispatch.path` → 파견 → **통합까지 연속**.
🔴 [중요] **사람 게이트는 둘이다 — ⑺ 통합 앞과 finalize(`main` 머지)** (정본 7단계, 사용자 확정
2026-09-02). [주의] **종전 서술 「finalize 한 곳뿐 · 통합 앞에 만들지 않는다」는 폐기됐다** —
2026-09-01 에 내가 만든 게이트를 정정받은 것은 맞지만, 그것을 「통합 승인은 없다」로 넓혀 적은
것이 틀렸다. **지금 코드에 ⑺ 게이트가 없는 것은 미구현이다.**
[주의] **세션 한도만 예외다** — 멈추고 보류하며, 시각이 지나도 자동 재개하지 않는다
(사용자 결정). 재개는 `--resume`, 고지는 `.33` 세션 시작 훅.
[주의] `#320` 의 부활 조건은 그 노트에 그대로 있다 — 지금 없는 것은 **상주 claimer** 뿐이다.

## Three clones — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`), BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), and GitHub.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
