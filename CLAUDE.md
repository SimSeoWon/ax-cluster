# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

Windows remote Codex: use the `/IT /RL LIMITED` conductor in the logged-in user's session,
with `workspace-write`, `windows.sandbox="unelevated"`, and
`sandbox_workspace_write.network_access=true`. “Session 1” is a launcher name, not a fixed
SessionId. Verify shell reads, **apply_patch writes**, and recovered results separately.
For AXCluster, `.33` is also a worker in `C:\trunk\AXCluster` (user 2026-10-03); game requester
roles stay project-specific. Shared operational memory: [`docs/windows-codex-remote.md`](docs/windows-codex-remote.md).
Readiness validates the scheduled launcher's registration, account and delivered paths; it does
not prove login, authentication or a completed Codex run. Verify those with actual source reads,
apply_patch writes and result recovery. A Windows `.ax` write failure alone does not establish
failure to edit source; compare paths and retain the evidence ([report 89](reports/89-codex-worker-readiness-and-write-probes.md)).

> [중요] **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- **Infrastructure changes start with RAG** (user 2026-10-03, #716): query
  `ax-projects.search_context_tool`, cross-check current source, then show scope, evidence and
  decomposition and ask for **local subagents or AX worker distribution**. Reuse the user's
  choice for the same task. Delegate accordingly; verify actual outputs and record results.
  Explain missing prerequisites before offering dispatch; an unready path needs preparation.
  Select skeletons, source boundaries and checks from registered `kind` (`unreal`/`code`/`index_only`).
  Details: [`master/skills/distribute/SKILL.md`](master/skills/distribute/SKILL.md).

- 🔴 [중요] **AX 마스터 지휘는 Claude·Codex만 맡는다** (사용자 2026-11-11, #829).
  Gemini 4 Argon/Antigravity는 지휘자가 범위를 지정한 서브 작업만 수행한다. 전역 설정·공용 지침·
  MCP 운영·일감 시작·마감·배포를 독자적으로 변경하거나 실행하지 않는다(공용 규칙 §1.10).
  세션 시작에 **[`ax-handoff`](master/skills/ax-handoff/SKILL.md) 스킬**을 읽고 실행한다.
  인수인계·공용 규칙과 실제 상태를 대조하고, 마스터 담당과 워커 지휘자 모드를 각각 확인한다.
  모드 변경은 사용자 선택에 따른다. 마스터의 세션 시작 훅은 없으므로 이 지침이 진입점이다.
  워커 조회·전환은 [`ax-mode`](master/skills/ax-mode/SKILL.md)의 기존 호출을 따른다.
  변경은 준비 검사를 거치는 `conductor.set_worker()`이며 전역값은 새 work 등재의 기본값이다.
  기존 `work.worker_mode` 스탬프는 진행 조각·후속 라운드에도 유지된다. 현재 모드·출처는
  도구로 재조회하고 최근 전환 근거는 [`인수인계서`](docs/orchestrator-handoff.md)를 확인한다.
  `claude` 워커 인증 readiness는 `claude auth status` 24시간 캐시(워커 홈
  `.cache/ax-dispatch/claude-auth.json`, `#721`)다. 실행 중 OAuth 실패는 재시도 없이 즉시 보고되며
  재로그인은 사람 몫이다 → [`docs/14-onboarding-runbook.md`](docs/14-onboarding-runbook.md).

      AX-ENTRY-MARK: repo

- [중요] **세션 시작에 이 둘을 먼저 읽는다 — 조건부가 아니다** (사용자 2026-08-22):
  **① 열린 마일스톤** [`docs/milestones/7-improvements.md`](docs/milestones/7-improvements.md)
  · **② 지금 열린 축의 지도** [`docs/12-multi-project.md`](docs/12-multi-project.md).
  둘 다 읽지 않고 코드부터 grep 하면 규칙을 코드에서 알아내려 하게 된다 — 2026-08-21 세션이
  그렇게 §11.5(데몬 재기동)를 어겼다. [주의] **항목·진행은 레드마인만** 본다.
  **M1–M6 all closed (M6 closed 2026-10-18, user decision — one milestone ran too long);
  M7 (개선·확장, continues M6) is open.**
  → [`docs/milestones/7-improvements.md`](docs/milestones/7-improvements.md) —
  numbers live in Redmine (version *마일스톤 7*; bugs → *마일스톤 7 - 버그/개선*). 개선은 실측이 앞선다 — 검색 관련은
  **정답 집합 없이 손대지 않는다** (M2 규칙). M5 의 판정들(git-carried·한글 베이스 머지·
  중앙화 가드)은 부활 조건과 함께 닫혔다 — `5-version-reconcile.md` 「여기서 배운 것」.
  M6 「여기서 배운 것」 → `6-improvements.md`.
  [주의] **What follows are the traps that still bind — not the closed milestones' scope or counts**
  (those are in Redmine and the closed milestone docs; M4's own 「여기서 배운 것」 too).
  🔴 **The topology is the user's 정본 7단계 (사용자 확정 2026-09-02)** — memory
  `distributed-pipeline-intended-shape`. **The worker commits to its own sub-branch; the master
  assigns the next piece** (user 2026-10-31, `#860`). Linux forces exactly **one** change: the UE5 build step inside
  `verify_and_merge` moves to `.2`. 🔴 **The port is finished (user 2026-10-18)** — design now
  stands on our own structure (정본 7단계 + current code, goal in `PLAN.md`); the origin is
  reference material, not the yardstick.
  🔴 [중요] **And the citation I redesigned it with was a misquote** (found 2026-09-02):
  `cluster_coordinator.verify_and_merge`'s docstring is *"**검증 워커**: … durable 단일 writer
  보존"* — the writer is the **verifying worker**, not the server (Plan v5 C.3: *"verify 를 서버
  단독에서 **워커 역할로 풀었다**"*), and *"단일 writer"* is an **epoch-fencing invariant**, not a
  claim that the pipeline has one writer. **No origin mode leaves git untouched by the worker**:
  pull mode pushes `worker/<host>/<task_id>` → server squash-merges into feature; push mode
  pushes ephemeral `attempt/…` → verifying worker merges into durable.
  [중요] **Do not argue the topology from M3's docs** — its label *"사용자 확정 2026-08-11"* is wrong
  (it was *"그래 해"* after I pushed it), and `settled-decisions.md:251` carries the same bad label.
  [중요] **Before building anything, read the existing assets** (this repo, its tests, reports) —
  most requests are already partly built. The origin (`~/AgentTest`) is consulted only when a
  feature came from there; `master/census.py` stays for that (limits: `docs/11` §11.2.1).
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
- [중요] **만들기 전에 기존 자산(이 저장소·테스트·리포트)을 읽는다** — 원전(`~/AgentTest`)은
  그 기능이 원전에서 왔을 때 참고한다(포팅 종료 2026-10-18). 대부분의 요구에는 이미 만들어진
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
- [중요] **Codex 스킬·MCP의 프로젝트 정본도 초기화 산출물이다** (`#699`, 2026-10-01).
  `<checkout>/.agents/skills`와 `<checkout>/.codex/config.toml`이 없으면 홈 자산이 있더라도
  정상으로 보지 않는다. `master.client update`가 마운트된 프로젝트의 작업장에(`--all` 이면 등록 전체에) 배달하고 `check`가
  해시와 `ax-client` 등록을 대조한다. Windows 신규 워커는 부트스트랩이 체크아웃 ACL에
  `CodexSandboxUsers` 수정 권한을 함께 부여해야 한다(`#698`).
- [주의] **워커 실패의 판정과 요청자 통보·상위 work 종결은 별개다.** 2026-10-01 첫 `kind: code`
  실증에서 스킬 실패가 `.33`에 통보되지 않았고 `ready_for_review` work가 남았다(`#700`·`#701`).
  통보를 확인하지 못한 work를 성공으로 해석하지 말고, terminal 여부를 큐에서 직접 대조한다.
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
  qualification: **the master never touches `main`**, and it never builds **locally** — builds run on
  the worker, driven by the master over SSH (`run_build_on_workshop`; 사용자 확정 2026-10-31, `#860`).
  [완료] **⑷⑸⑹ are live** (measured 2026-09-04 01:28→01:30: **4/4 · 0 failed · 1m38s**).
  Sub-branch per piece, the worker commits its pair (`.h`+`.cpp`) to it, the piece closes at that
  commit, and when all pieces are terminal the queue posts a Redmine `[리뷰 요청]` issue to the
  requester. **The 「통합자」 is gone** — `integrate.py` (≈1,000 lines) and its 131 tests are
  deleted; `master/test_no_integrator.py` fails if any of it comes back.
  [완료] **⑺ ran live 2026-09-05** (`#355`): `.33` merged the round's sub-branches into the work
  branch, the integration build caught **four real defects in worker output**, `.33` fixed them in
  that tree, rebuilt, and advanced `8db9826 → 7c3e472`. The decision it was asked for
  ("bug or structural change?") is recorded as a note on the work's Redmine issue.
  🔴 [중요] **A work runs many rounds** (user-confirmed 2026-09-05). After ⑺ advances the branch,
  more work goes into the **same** work — the requester calls **`improve_work(work_id,
  round=current+1, specs)`**, a *separate* call from registration (user-confirmed 2026-09-05:
  *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로"*): `round +1`, sub-branches become
  `task/<work>/r<N>/<piece>`, and ⑺ merges **only that round's** pieces. [중요] **The round value
  is a check, not a command** — the queue already knows it (current+1) and **refuses** a mismatch
  rather than adjusting. [주의] `register_work` with a `work_id` is now **rejected**: one entrance
  with two meanings is what made the round get *inferred from state*, and when the state was
  unexpected it was silently wrong (pieces stamped with the previous round, or stuck pending on a
  closed work). The Redmine issue is opened **at registration** and every event
  (round done · advance · the human's decision) lands on it as a note; `finalize` closes it as
  **완료** with the `main` merge. Dispatch now has **two** triggers — skeleton push *and*
  registration (with only push, "push first, register second" waited for the 10-min catchup).
  [주의] Workers keep nothing: after commit+push the cycle deletes the piece branch, prunes
  remote-tracking refs and removes `.ax/work/<task>`.
  [완료] ⑺ mechanics: `review.advance_work()` + the `ax-advance` skill
  merge every sub-branch into the **work branch** (not `main`), build once on `.33`, ask *"bug or
  structural change?"*, and push the advance only on `confirm=True`. Flow Y
  (2026-08-14, *"master commits inferred diffs to the durable branch"*) and the `#327` teardown of
  the `attempt/` tier are **the redesign, superseded by the 7 steps** — `#327` argued from *"0
  production callers"*, which is circular for a path nobody wired. Mechanism as built today:
  `master/work/subbranch.py` + `wcommit.py` (the worker's commit cycle), a
  push-only second remote `gitea-write`, and a `pre-push` hook that rejects every ref outside
  `attempt/*`·`task/*` (deletions only when the tip is reachable from `<remote>/main`).
  [주의] **`carry.py` is gone** (torn down 2026-09-02 with the manifest) — if a doc still names it
  as current mechanism, that doc is stale. The instructions travel as `[DOC]`/`[PSEUDO]` comments
  in the skeleton and git carries them.
  [주의] `attempt/*` stays in that allowlist only for **legacy debris cleanup**
  (`attempt.plan_remote_cleanup`). The 정본 clone's `origin` push stays sealed as a loud guard.
  → [`docs/2-architecture.md`](docs/2-architecture.md) §2.2-1 · `reports/16-master-write-surface.md`
- [중요] **Services use a bearer token** (`task_queue` 8101, broker 8102, projects 8103).
  Token: `~/.config/ax-cluster/token`, 0600, **fail-closed — a service will not start without it**.
  Send `Authorization: Bearer <token>`. [주의] **8103's web UI and `/api/v1` are public** (the
  `PREFIXES` in `master/webui/app.py`; revert with `AX_VIEW_REQUIRE_TOKEN=1`) — never put a
  sensitive body there; its write surface `/control/*` needs the requester token. All are *also* ufw LAN-only —
  **never widen those rules to `Anywhere`.** Two layers, not one instead of the other.
  → `master/auth.py`, PLAN §9.5.6
- [중요] **`/home/sim/AgentTest` is reference-only — never modify or push to it.** Reference only — the port finished 2026-10-18.
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
  [주의] **Pipeline code committing is a different thing** — workers committing to their
  `task/<work>/…` sub-branches and the ⑺ advance pushing the work branch are designed behavior; these rules bind the *interactive session*.
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
| **Milestone doc** `docs/milestones/7-improvements.md` (open) | *Why this order?* — chains, traps, measured evidence | [중요] **No numerators here.** They drifted twice (중 1.3 counted 7/10 against a 13-item list; 대 1 stayed at 15 after 중 1.3 went 5→8). Keep the reasoning an issue cannot hold |
| **Redmine** `http://192.168.0.57:8080` | *Where are we, and what is open?* — **the milestone itself** | [중요] **Version = 마일스톤 · parent issue = 중분류 · subtask = 소분류** (user-confirmed 2026-08-09). Progress is **computed**, never typed. Only **완료(4)** is a closing status — 해결(3) still counts as open. Put the commit hash in the note |
| **`reports/`** | *Why did we decide that?* — decisions, measurements, traps | One report per session, Korean. Not a task list |
| **Redmine 버전 「아이디어 — 추후 검토 수집」** | *What might we build someday?* — 미정 아이디어 | [중요] **일감이 아니다** (사용자 개설 2026-08-17). 내용은 **그 이슈의 본문·코멘트**에만 쓴다 — 위키는 쓰지 않는다(사용자 2026-10-21). 진행·집계 금지, 착수 결정 시 실 마일스톤으로 이동 |

**At session start**: read the open milestone, then `GET /issues.json?project_id=ax-cluster&status_id=open`. **At session end**: update the issues you moved, then write the report.

[중요] **AX infra issues live in their own Redmine project `ax-cluster` (id 3)** (user decision
2026-09-28 — supersedes 2026-08-09's "same project as `ModularStage`", since the non-UE `kimodo`
made AX no longer one game's tooling). Game/tool issues go where `<twin>/config.yaml`
`redmine.project` says (`modularstage` · `ns` · `kimodo`); unset means refuse (`#293`).
AX issues **and their milestone versions** belong to `ax-cluster` (user decision 2026-10-05: 107
closed `[AX]` issues moved from `modularstage`; versions 마일스톤 6 · 버그·개선 · 아이디어 recreated in
`ax-cluster` as ids 17·19·18, the old `modularstage` copies un-shared so name lookups resolve once).
2026-10-18: M6(17) and its bug version (19, renamed *마일스톤 6 - 버그/개선*) closed; open now
마일스톤 7 — 개선·확장(21) · 마일스톤 7 - 버그/개선(22) · 아이디어(18).
Tracker `코드리뷰` only — **never create a project or tracker without the user.** Read is public; writing needs the admin API key, which is **not on disk** — pull it
from the master's own container DB. [중요] **Never write the key value into a doc or commit.**
→ [`docs/10-references.md`](docs/10-references.md) §10.1

## Where things are

| Need | Go to |
|---|---|
| What's decided vs open | [`PLAN.md`](PLAN.md) — index of `docs/` |
| [중요] **지금 열린 축 — 다중 프로젝트** | [`docs/12-multi-project.md`](docs/12-multi-project.md) — 갈린 축과 안 갈린 축 · 네 부모 일감의 지도. [완료] **마운트 강제는 2026-08-22 배선됐다**(3단계 전부) · [주의] §12.4 는 그 전의 「안 된 것을 됐다고 적은」 거짓 서술 네 곳을 정정한 기록이다 |
| [중요] **요청 태그 계약** (기능 정본) | [`docs/13-request-tagging.md`](docs/13-request-tagging.md) — 네 정책 · 필수 표면 · 거절 사유 셋 · 발신자 · [주의] **발신자 배달이 서버 조임보다 먼저다**(§13.6) |
| [중요] **신규 프로젝트 온보딩** (실행용) | [`docs/14-onboarding-runbook.md`](docs/14-onboarding-runbook.md) — 명령 단위 절차 + 단계별 **「안 됐으면 무엇이 안 보이나」** |
| [중요] **스킬 작성 규약** — 만들거나 고칠 때마다 | [`docs/skill-authoring.md`](docs/skill-authoring.md) — 맨 앞 목차·구획·`서버:도구`·scripts·500줄·번들. `master/test_skill_conventions.py` 가 강제한다 (#890) |
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
The pipeline runs end to end with **four gates**: skeleton (written by the requester, UHT-gated before
registration — the master never builds skeletons, `#339`) → 층1 (deterministic, at *both* response-acceptance and apply time) → 층2 (commercial
model with **declaration grounding**) → 층3 (per-piece UE5 build + one work-level RunTests).
**It builds per piece, not once at the end** — §4.5's "apply everything then build once" was
overturned by the measured 35–65s incremental build, because a single build can't say *which*
piece broke it. [주의] The gates are **not** what 정본 7단계 changes; they stay.
[완료] **Bodies are written through a lane chain, not a hardcoded `claude -p`** (`#346`,
2026-09-04 · user's order: *"agy, 그다음 로컬로 배선하고, 클로드는 나중에 사용해"*).
`work/lanes.py` `DEFAULT_LANES` tries **`codex` → `agy` → local `qwen2.5-coder:14b`**
(reordered 2026-09-06 to spend Codex quota first), fail-forward; `claude` is off the
default chain because its session limit is a **shared** resource — one 429 killed 3 of 4 pieces
(measured 00:16). The lane convention is **not new**: `ontology/synth.generate` already picks the
backend from the model string. Measured on one skeleton, same prompt, same 층1 verdict:
agy **58.5s** 2/2 files · local **117.6s** 2/2 · claude 90–154s then 429.
[중요] **"Local models can't write bodies" was a claim I made with no measurement behind it** —
the evidence I cited (35B blocking two correct files) was **층2 = judgement**, a different task.
With `[DOC]`+`[PSEUDO]`+frozen headers spelling out the design, a 14B writes bodies that pass 층1.
[주의] 층2 stays commercial — that measurement does hold for judgement.
[주의] The lanes run **on the master** and hand back text, so the result is written into the
worker's files (`bundle._remote_write`, scp + sha256) and `wcommit` then **re-reads from disk**
before 층1 — **no gate was removed.**
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
(**the 정본 direction** — worker commits to its sub-branch) and `ax-infer` (infer only, never
commit). Neither may be "cleaned up" — both are live paths.
[주의] **The requester now gets four skills** — `ax-request` · `ax-ontology` · **`ax-advance`** ·
`ax-review`. The last two are **different stages** and I confused them once (2026-09-04): a round
that just finished goes to **`ax-advance`** (merge subs into the work branch, build once, ask
*"bug or structure?"*, advance it); `main` only comes later, via `ax-review` → `finalize_work`.
Each SKILL.md now points at the other so that utterance never lands in the wrong place.
[중요] **Content travels as files in both directions, never on the command line or stdout.** `.2`'s
console is CP949: the master→worker rule ("instructions ASCII, content by file") applies to
worker→master too — responses land in `.ax/work/<task>/response.txt` and come back by `scp`.
[중요] **The integration worktree is pipeline-owned; a human's tree never is.** `ax-review-<work_id>` sits
**beside** the checkout (never inside it) and `review.py` removes and re-adds it (detached) on
reuse. That reset is safe *only* because nobody edits that tree by hand — never apply the same
reasoning to `.33`'s or a worker's main checkout.
[중요] **Never `push --force` from the integration step.** If a push is rejected, the commits stay in the
isolated tree (nothing is lost) and a human decides — the pipeline does not rewrite history.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

## Tests — [중요] **수를 여기 적지 않는다**

하루에 여섯 번 고쳤다. 마일스톤 분자를 레드마인으로 옮긴 것과 **같은 이유**로, 수치가 아니라
**세는 법**을 적는다. pytest는 쓰지 않으며 스크립트형 검사와 unittest 검사가 함께 있다.

AXCluster의 통합 검사 정본 목록은 `tests/integration/checks.json`이다. 각 검사를 별도
프로세스·임시 프로젝트 루트에서 실행하고 종료코드·수치·완료 신호를 함께 확인한다.
신규 단위 검사는 `checks.json` 등록 여부를 `master/test_integration_coverage.py`로, 마스터 스킬은 `~/.claude/skills` 링크 일치를 `master-local --check`로 확인한다 (`#929`).

```bash
.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v
```

`test_indexer.py`의 합성 성공 케이스는 가짜 합성기를 명시적으로 주입한다. 브로커·LLM·네트워크
성공을 단위 검사 전제로 두지 않는다. R5와 해당 격리·배포 근거는
[리포트 90](reports/90-r5-indexer-test-isolation-and-deployment.md).
샌드박스에서 `sg gitea`·audit 권한이 차단되면 검사 결함으로 단정하지 않는다. 실패 원문을
보고하고 같은 검사만 담은 좁은 스크립트의 샌드박스 해제 승인을 요청한다.
아래 전수 집계는 조사용이다. 작업의 필수 검사는 위 명시 목록과 변경 대상의 회귀 검사로 고른다.

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
# 전진·finalize: 요청자의 ax-advance 스킬과 ax-projects MCP; 사람 승인 게이트를 따른다
.venv/bin/python -m master.work.cleanup plan|apply     # 찌꺼기 (plan 은 안 지움 · verified·cancelled 만)
.venv/bin/python -m master.work.cleanup remote --apply # 병합 확인된 원격 attempt/task 삭제 (#219)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client probe|plan|deliver|check <프로젝트>
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client update
                                                       # 마운트된 프로젝트만 배달→대조 (`--all` = 등록 전체, #655);
                                                       # 비마운트는 set_active 전환 때 뒤처진 기계만 맞춘다
                                                       # [중요] 커밋마다 실행 — 배달 출처 커밋이 HEAD 보다
                                                       # 뒤처지면 해시가 같아도 check 가 실패한다
.venv/bin/python -m master.ontology plan|dry|refresh   # 이 순서로
.venv/bin/python -m master.ontology log-candidates     # 태깅 권장 리포트 (#169, LLM 0)
```

[중요] **승인 뒤는 한 호출이다** (원전 6단계 동등, 2026-08-21): `review.finalize_work(confirm=True)` 가 ①`main` `--no-ff` 머지+push ②Redmine 기재 + **이슈를 「완료」로 닫는다**(머지 커밋 해시 · 사용자 2026-09-04 *"레드마인 닫고 메인에 머지해야지"* — 이 호출 자체가 승인으로만 도는 자리라 자동으로 닫히는 것이 아니다) ③**도달 가능한 브랜치 삭제** ⑤`merge_status`→`merged` 를 이어서 한다. `confirm=False`(기본)는 **통합만 하고 멈추고** 사람이 실행할 명령을 돌려준다. [주의] 순서가 계약이다 — 정리는 **머지 뒤**여야 도달 가능 판정이 참이 된다.

🔴 [중요] **워커·요청자에 상주 데몬은 없다 — 서버(.57)가 SSH 로 총괄한다** (사용자 확정 2026-10-31,
`#860`). 정본 ⑤ 는 「서버가 다음 조각을 배정한다」. `#320`(08-27)이 걷은 상주를 `#404`(09-12)가
`.2` 빌드 전용으로 되살렸지만 **철회됐다** — 그 복원을 「기존 자산」으로 다시 쓰지 않는다(2026-10-31
`#857` T4 가 그렇게 되돌아갔다). 로그인 세션이 필요한 일은 서버가 SSH 로 `schtasks /run`(/IT 런처)을
그때만 건다. [완료] 철거 완료(`#861` `bbd0110`·`9a195e0`) — 배달은 어떤 kind 에도 상주를 등록하지
않고 잔재를 해제하며, `check` 는 잔재·조회 실패를 FAIL 로 본다. 데몬 소스는 지웠고
`master/test_no_worker_daemon.py` 가 부활을 막는다.
[완료] **파견은 마스터 유닛이 잇는다** (`#340`, `c33316e`·`9cc73d9`): 골조 push 이벤트·등재 →
`ax-dispatch.path` → 파견 → 조각 종결 → `.33` 공지.
🔴 [중요] **사람 게이트는 둘이다 — ⑺ 통합 앞과 finalize(`main` 머지)** (정본 7단계, 사용자 확정
2026-09-02). [주의] **종전 서술 「finalize 한 곳뿐 · 통합 앞에 만들지 않는다」는 폐기됐다** —
2026-09-01 에 내가 만든 게이트를 정정받은 것은 맞지만, 그것을 「통합 승인은 없다」로 넓혀 적은
것이 틀렸다. ⑺ 게이트는 `review.advance_work(confirm=False)` 기본값으로 코드에 있다.
[주의] **세션 한도만 예외다** — 멈추고 보류하며, 시각이 지나도 자동 재개하지 않는다
(사용자 결정). 재개는 `--resume`, 고지는 `.33` 세션 시작 훅.

## Clones and remotes — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`) and BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`) both use
Gitea (`gitea@192.168.0.57:Sim/ax-cluster.git`, private) as `origin` — that is the canonical remote.
GitHub (`SimSeoWon/ax-cluster`, private) is a **push mirror driven by Gitea** — never push to GitHub
directly: the mirror overwrites it and prunes anything Gitea does not have.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
