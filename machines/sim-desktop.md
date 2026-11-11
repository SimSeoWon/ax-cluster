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

## PC types and execution responsibility — user decision 2026-11-07

| Type | PCs | Responsibility and working baseline |
|---|---|---|
| Infrastructure master | `.57` sim-desktop | Owns AX services, queue, indexing and automatic review; develops the cluster itself. The master owns automatic review execution. `~/ax-cluster` also supplies service code: inspect its actual branch and revision during development and finish. |
| Supporting worker | `.2`, `.43` | Executes the master's assigned project and work. The project's `main` is the idle and post-task baseline; use the assigned task branch while implementing a dispatched piece. Do not independently select projects, revisions or review execution locations. |
| User work PC | `.33` | The user develops projects and submits requests here. Do not move automatic review execution here or switch branches in the user's working tree. Only while AXCluster is mounted, its separate `C:\trunk\AXCluster` checkout may perform the authorized worker role. Keep that role and directory separate from game requester work. |

- Verify PC type, per-project role, Git path and current branch separately. An inference endpoint is not thereby the review execution host.
- Before Git operations, cross-check the mounted project against the target repository and registered checkout path. Independent clones do not share branch refs; linked worktrees do. Inspect actual paths and connections before attributing state to another PC or worktree.
- Report hypothetical test conditions explicitly. Without confirming the same condition in production, do not present it as a production incident or inability to work. Ask the user when the execution owner or permitted operation is unclear.

## Orchestrator handoff — read before anything else

    AX-ENTRY-MARK: home

[중요] **Only Claude and Codex orchestrate AX master work** (user 2026-11-11, #829).
Gemini 4 Argon/Antigravity may perform scoped subagent work assigned and verified by the
conductor. It must not independently change global settings/shared instructions or operate MCP,
start/finish issues, or deploy. Before planning, use
[`ax-handoff`](../master/skills/ax-handoff/SKILL.md) to read the handoff and shared rules,
cross-check actual state, and inspect master ownership and worker conductor mode separately.
Change worker mode only when the user chooses it; a master handoff alone does not select a
worker mode. Record master ownership only after a user-directed handoff and actual takeover;
reading the handoff or querying state does not authorize a record change. Carry forward existing
approvals and distribution choices within their original scope; do not request them again merely
because the session changed. Preserve outstanding approval and `awaiting_resume` conditions.
If the documented call path differs or the procedure is unclear, ask the user before proceeding;
do not create temporary scripts or substitute calls.
The master has no session-start hook; this instruction is the entry point.
Use [`ax-mode`](../master/skills/ax-mode/SKILL.md) for worker queries and changes, including its
canonical fallback when MCP is unavailable. Changes go through `conductor.set_worker()` readiness
checks. Query the current mode and source rather than treating an old state record as live;
recent transition evidence lives in the [handoff](../docs/orchestrator-handoff.md).

## Where the project stands — read this before planning

**Infrastructure changes start with RAG** (user 2026-10-03, #716): query
`ax-projects.search_context_tool`, cross-check current source, then show scope, evidence and
decomposition and ask for **local subagents or AX worker distribution**. Reuse the user's choice
for the same task. Delegate accordingly; verify actual outputs and record results. Explain missing
prerequisites before offering dispatch; an unready path needs preparation. Select skeletons,
source boundaries and checks from registered `kind` (`unreal`/`code`/`index_only`).
Details: [`../master/skills/distribute/SKILL.md`](../master/skills/distribute/SKILL.md).

**M1–M6 all closed (M6 closed 2026-10-18, user decision). M7 (개선·확장, continues M6)
is open — numbers live in Redmine (version *마일스톤 7*; bugs → *마일스톤 7 - 버그/개선*). A separate dateless bucket
*아이디어 — 추후 검토 수집* holds not-yet-decided ideas (issue body/comments only — no wiki) — items there
are NOT work.**

| | |
|---|---|
| Current milestone — **read only this one** | `~/ax-cluster/docs/milestones/7-improvements.md` |
| Closed, kept as reference | `6-improvements.md` (「여기서 배운 것」 — 호출부 0 · 실경로 재현 · 코드가 강제) · `5-version-reconcile.md` (「여기서 배운 것」 — 전제가 죽은 선택 · 허위 인용 · 중앙화의 새 좌표) · `4-origin-reconciliation.md` (왕복이 계약 · 원전 기본값 · census 한계) · `3-work-pipeline.md` (gates/grounding 실측) · `2-twin-restoration.md` · `1-infrastructure.md` |

> [주의] **Below are the traps that still bind, not the closed milestones' records.** Progress and
> counts live in Redmine; the narrative (census numbers, M2/M3/M4 scope and timings, the ported web
> UI's feature list) lives in the closed milestone docs listed above — this file does not repeat them.

🔴 [중요] **The pipeline's canonical shape is the user's 7 steps — 사용자 확정 2026-09-02.**
Read them before planning anything in this area: memory `distributed-pipeline-intended-shape`.
**In them the worker commits to its own sub-branch; the master assigns the next piece** (user 2026-10-31, `#860`). Every record
that says otherwise lost to those 7 steps on that date.

🔴 [중요] **"one writer = the server" was a misquote of the origin, and it is what turned this
port into a redesign** (found 2026-09-02 by finally reading the file). The origin's
`cluster_coordinator.verify_and_merge` docstring reads:

    """**검증 워커**: 시도 epoch 게이트 → 통과 시 durable 에 merge·push.
       … stale assignee(zombie) → 거부(merge 안 함). durable 단일 writer 보존."""

So ⑴ that writer is the **verifying worker**, not the server — Plan v5 C.3 says in as many words
*"verify 를 **서버 단독에서 워커 역할로 풀었다**"* — and ⑵ *"단일 writer"* is an **epoch-fencing
invariant** (two assignees must never write the same durable ref), **not** a claim that the
pipeline has one writer. [중요] **The origin has no mode in which a worker leaves git alone:**
pull mode pushes `worker/<host>/<task_id>` and the server squash-merges it into the feature
branch; push mode pushes ephemeral `attempt/…` and the verifying worker merges it into durable.

[완료] **코드가 정본으로 왔다** (2026-09-04). 「통합자」는 **삭제**됐다 — `integrate.py`
약 1,000줄과 테스트 131건을 지웠고, `master/test_no_integrator.py` 가 부활을 막는다.
⑷⑸⑹ 은 라이브 완주했다(01:28→01:30 · **4/4 · 실패 0 · 1분 38초**). `#327` 이 attempt 계층을 걷은 근거(*"0 production callers"*)는 여전히
순환이었다 — 그 경로를 배선한 적이 없었으니 당연하다.

🔴 **The port is finished (user 2026-10-18).** This project began as an OS/environment port
(Windows+UE5 daemon → Linux+Gitea); from M7 on it is our own design — goal in
`~/ax-cluster/PLAN.md`. The origin is reference material, not the yardstick.

[중요] **Workers may not delete branches** — a branch is removed only when its tip is reachable from
`origin/main`, and workers return to **`main`**.

🔴 **The pipeline — 정본 7단계 (사용자 확정 2026-09-02).** This is the shape to build toward;
where today's code differs, that difference is a defect, not a variant:

    1 요청(`.33`) → 마스터에 **컨텍스트 문서 요청**
    2 `.33` 이 **모든 클래스의 동작을 계획**하고 **골조**를 만든다
          골조 = 프로퍼티·메서드의 기본 정의 + 내용물은 **주석 작업지시서**(`[DOC]`·`[PSEUDO]`)
    3 `.33` 이 골조를 **작업 브랜치 `task/<work>/base` 에 커밋**하고 마스터에 요청 (UHT 게이트)
    4 마스터가 **골조 파일 기준으로** 서브태스크를 만들고
          **작업 브랜치에서 갈라진 서브 브랜치를 조각마다 만들어**   [완료] 라이브 2026-09-03
          워커에게 **브랜치 + 작업할 클래스**를 전달 · **병렬이 기본**  [완료] `.2`+`.43` 동시
    5 워커가 🔴 **제미나이·로컬 LLM 까지 써서** 본문을 코드로 바꾸고  [완료] `work/lanes.py`
          🔴 레인 순서 **codex → agy → 로컬(qwen2.5-coder:14b)** · `claude` 는 체인 밖이다
          (사용자 결정 2026-09-06: *"클로드는 마스터 서버 수정도 병행해야 하니까 … 최대한
           코덱스를 우선 … 코덱스 모두 소진하면 안티그래비티로 … 클로드와 동급으로"*.
           [중요] **쓰는 일만 옮겼다** — 층2 검증·리뷰 체인은 `agy → claude` 그대로다,
           교차 계열 조건(리뷰어는 작성자와 다른 계열)이 걸려 있기 때문이다)
          (codex 는 2026-09-05 네 대 전부에 설치 · **마스터 로컬 우선**(`.33` 원격은 폴백) ·
           본문 A/B: agy 32.9초 · codex 98.6초 · 로컬 117.6초 — **셋 다 층1 통과**.
           [주의] 순서를 바꾼 값은 **속도 손해**다, 근거는 품질이 아니라 한도 배분이다)
          (한도가 공용 자원 — 429 하나로 4조각 중 3이 죽었다. 사용자 지시 2026-09-04)
          🔴 [중요] **누가 그 일을 지휘하는지도 고른다** — `lane`/`claude`/`codex` (`#385`)
             `lane` = 마스터가 텍스트만 만들어 워커에 써 넣는다(지금까지의 동작) ·
             `claude`/`codex` = 워커에서 그 에이전트가 돌며 체크아웃을 읽고 고친다
             표면은 `ax-mode` 스킬 · `get/set_worker_mode` · `.33` 의 요청자 MCP
             [주의] **전역 모드는 새 work 등재의 기본값**이다. 기존 `work.worker_mode`
                    스탬프가 우선하며 진행 조각·후속 라운드에 전역 변경을 소급하지 않는다.
                    스탬프 없는 옛 work은 전역을 읽을 수 있으므로 구분한다.
             [주의] **기본값 상수는 아직 사람이 안 정했다**(`_UNDECIDED_DEFAULT`, 값 `lane`).
             🔴 [중요] **현재 워커 지휘자 모드는 문서에 적지 않는다** — 바뀔 때마다 이 줄이
                    낡았다. 말하기 전에 `get_orchestration_tool`(또는 `mode.json`)로 값·출처를
                    재조회한다. `.2` 에서 Codex 데스크톱 앱 금지(`#661` 그림자 스킬).
                    `claude` 모드 readiness는 워커마다 `claude auth status` 를 24시간 캐시한다
                    (워커 홈 `.cache/ax-dispatch/claude-auth.json`, `#721`). 실행 중 OAuth 실패는
                    재시도 없이 즉시 보고된다 — 재로그인은 사람 몫, 그 뒤 강제 재검사.
                    절차: `docs/14-onboarding-runbook.md`
             🔴 [완료] **`.2` 에 `codex` 모드를 보낸다 — 세션 1 경유로 라이브 완주했다**
                    (2026-09-13). **죽는 것은 「SSH 가 직접 미는」 경로뿐이고, 파견은 더 이상
                    그 경로로 가지 않는다.** 아래는 그 경로가 왜 죽는지의 기록이다 —
                    윈도우 비대화형(SSH Session 0)에서 codex 샌드박스 runner 가 `0xC0000142` 로
                    죽는다 (upstream `openai/codex#37722` open · A-B-A 로 확정 · 원인은
                    Session 0 Window Station/Desktop 에 샌드박스 계정 ACE 가 없는 것).
                    [중요] **고장은 「SSH + 윈도우 비대화형」 교집합 하나다** — `.43`(리눅스,
                    SSH) · 마스터 로컬 레인(`call_codex_why`) · `.33` 대화형은 **멀쩡하다**.
                    완화로 `.2` 를 `sandbox = "unelevated"` 로 뒀지만 **부분 성공**이다:
                    편집·커밋은 되고 셸은 여전히 죽고 **네트워크 격리를 잃는다**(`#35940`).
                    백업 `config.toml.bak-20260911-elevated`
                    🔴 [완료] **고치는 길이 확정됐다 — 세션 1 이다** (실측 2026-09-12).
                       `/IT` 로 등록하면 SSH(세션 0)는 스케줄러에게 **부탁만** 하고 프로세스는
                       **세션 1** 에 생겨 **공식 설치본이 그대로 돈다.** 그래서
                       **패치 codex·Rust 빌드·아티팩트 배포는 불필요하다.** 리포트 63
                    🔴 [중요] **현재 readiness는 실제 파견 런처의 등록 계약을 검사한다**
                       (`00f8532`, 2026-10-04). SSH Session 0에서 `codex sandbox`를 실행하던
                       검사는 제거했다. XML의 InteractiveToken·LeastPrivilege·Enabled·계정/SID와
                       절대 Python·배달된 런처 경로를 대조한다. 등록 통과는 로그인·인증·실행
                       성공을 보증하지 않는다. 실제 셸 읽기·apply_patch·결과 회수가 별도 근거다.
                       예전 `fc23a47` probe 수정은 역사 기록이다. 파견은 `runner.uses_session1`(윈도우 AND
                       codex)이 `schtasks /run` 으로 돌리고, 마스터는 `job.json`(데이터만)을
                       쓴다. 🔴 [주의] **그래서 재부팅 뒤 `janus` 로그인이 필수다** —
                       `/IT` 과제는 대화형 로그온이 있어야 돌고 `.2` 엔 자동 로그온이 없다
                       (`AutoAdminLogon` 키 부재, 실측). 안 하면 세션 1 이 없어 `.2` 가
                       **조용히 파견에서 빠진다.** RDP(3389)로도 된다. 리포트 64
             🔴 [완료] **프로젝트 로컬 Codex 정본을 배달한다** (`#699`, `63ea616`, 2026-10-01).
                    각 체크아웃의 `.agents/skills`와 `.codex/config.toml`을 초기화·배달·검사하며,
                    홈의 동명 스킬보다 프로젝트 로컬 정본이 우선한다. Windows 신규 체크아웃은
                    부트스트랩이 `CodexSandboxUsers` 수정 ACE도 건다(`#698`, `906fe60`).
                    [주의] 첫 Kimodo 실증에서 실패 통보와 work 종결이 각각 누락됐다(`#700`·`#701`).
                    완료 훅 기록만 믿지 말고 큐의 terminal 상태를 함께 대조한다.
          **자기 서브 브랜치에 커밋**하고                            [완료] 라이브 2026-09-03
          (끝나면 `main` 복귀 — 체크아웃된 브랜치는 정리에서 빠진다)  [완료] 실측
          🔴 **서버가 끝난 것을 확인하고 다음 조각을 배정한다** (사용자 확정 2026-10-31 —
                 종전 「워커가 다음 작업을 요청」(pull)은 폐기). 워커·요청자에는 **상주 데몬이
                 없다** — 서버(.57)가 SSH 로 총괄한다(`#860`). [주의] `#404`(09-12)가 `.2` 에
                 되살린 빌드 상주는 철회됐다 — 리포트 63 은 이력이다
    6 모든 서브태스크가 끝나면 **요청한 `.33` 에 전달**               [완료] Redmine `[리뷰 요청]`
          이슈가 실제로 발행된다 (`#350`·`#352`·`#354`) · `.33` 훅이 **세션 시작과 매 턴** 고지
          🔴 [완료] **라이브 완주 2026-09-10 23:12** — `work_completion.py` 훅(`asyncRewake`)이
                 `.33` 세션을 **사람 입력 없이 깨웠고 결과가 닿았다**. 등재→완주 7분 16초 ·
                 3/3 · 재시도 0 · 개입 0. 훅이 7분간 백그라운드로 큐를 따라간다 (리포트 60)
                 알림 채널은 **이 훅 하나로 확정**(`#356` 종결, 사용자 2026-10-05 — SMTP·n8n 안 씀)
    7 🔴 **`.33` 이 서브 브랜치를 전부 「작업 브랜치」에 머지하고 한 번 검사한 뒤,
          「버그냐 구조 수정이냐」를 묻고 그 브랜치를 한 칸 전진시킨다**  [완료] 라이브 2026-09-05
          (8db9826→7c3e472 · 통합 빌드가 워커 산출물 버그 4건을 잡았다 · 결정은 이슈 노트로)
          → `ax-advance` (`review.advance_work`) · `confirm=False` 기본 · 빌드 미측정도 거절
          🔴 [중요] **요청자가 부르는 것은 셋이고, 갈래를 고르는 것은 `.33` 이다**
            (사용자 확정 2026-09-05 — 마스터는 추론하지 않고 **입력으로** 받는다):
              ① 등록      `register_work(title, specs)`             새 분산 작업 · round = 1
              ② 개선요청   `improve_work(work_id, round=현재+1, …)`   ⑺ 전진 뒤 더 고칠 때
              ③ 마감      `ax-review` → `finalize`                  작업 전체가 끝났을 때만
            [중요] **`round` 는 명령이 아니라 확인이다** — 큐가 아는 값(현재+1)과 다르면 거절한다
            [주의] 종전에는 ①에 `work_id` 를 실으면 ②였다. 한 입구에 두 뜻이라 라운드를
              **상태로 추론**했고, 상태가 예상 밖이면 조용히 틀렸다(도는 중이면 지난 라운드에
              섞이고, 마감된 work 엔 조각이 pending 으로 박힌다). 지금은 ①이 **거절**한다
            → 다음 라운드 골조는 전진분의 `.h`/`.cpp` 에 지시 주석을 남겨 올린다
              (`target_branch` 는 비운다 — 저장된 값이 이긴다)
          [중요] **`main` 은 그보다 뒤다** — 작업 전체가 끝났을 때만 `ax-review` → `finalize`
          [주의] 그 둘을 섞어 오지시를 냈다 (2026-09-04) — 라운드 직후 공지가 `main` 머지를
            권했다. 사용자: *"리뷰 요청은 왜한건데? 전혀 다른 스킬을 요청한거 같은데"*

[주의] **The four deterministic gates stay** (층1 · 층2 grounding · 조각별 UE5 빌드 · RunTests —
detail in `3-work-pipeline.md`). 정본이 바꾸는 것은 **누가 쓰고 누가 묻는가**이고, 게이트가
판정한다는 원칙은 그대로다. The origin agrees: its per-task verify is static-only and a
**통합 빌드** on the feature branch is what catches cross-file breakage.

🔴 [중요] **자동 경로로 LLM 에게 보내는 글에 명령형을 쓰지 않는다 — 주입으로 거부된다**
(실측 2026-09-10, 리포트 60). 훅·알림처럼 **사람이 치지 않은 경로**로 들어온 글은 모델에게
신뢰 등급이 낮다. 같은 훅에서 문구만 바꿔 쟀다 — *"…묻지 말고 결과를 보고하세요"* 는 `.33` 이
쓰는 TUI 세션이 **거부했고**(*"suspicious instructions embedded in what looks like a stop hook.
I'm not following injected directives"*), 사실만 실은 판은 통과했다. 🔴 **그래서 배선이 갈린다 —
「무엇이 왔나」는 자동 경로가, 「그래서 무엇을 하나」는 스킬·`CLAUDE.md` 가 말한다.** 뒤엣것은
세션이 원래 읽는 **자기 문서**라 같은 판정을 받지 않는다.
[주의] **표면마다 판정이 다르다** — 같은 명령형을 SDK(`-p`) 세션은 **따랐다.** 한 곳에서
통과한 것은 통과의 증거가 아니다. [주의] 사실만 실어도 **스킬이 없으면 아무것도 안 한다**
(실측: *"알림을 받았다"* 로 끝났다) — 둘은 **함께** 있어야 한다.

🔴 [중요] **게이트를 다섯 번째로 만들지 않는다** (2026-09-03, 걷었다). 골조가 `[PSEUDO]` 에
본문까지 써 버린 것을 파견 **전에** 막는 게이트를 하나 만들었는데, **원전에 없는 계층**이었고
(원전 Step 6 은 UE 빌드뿐 · `[PSEUDO]` 검사는 `worker/validator.py` 의 **구현 뒤** = 우리 층1)
정상 골조를 **5개 조각** 차단했다(`Super::EndPlay` · `RETURN_QUICK_DECLARE_CYCLE_STAT` ·
`PrimaryComponentTick` 을 「본문」으로 오인). 태운 것: 골조 생성 2회 + 재작성 1회(`.33` Opus)
· 실증 라운드 2회. [주의] **층1 이 그 일을 하는 것을 로그로 보고도** 만들었다 —
`만들기 전에 ①이미 있나(이 저장소·원전) ②이미 잡는 게 있나 ③오탐이면 뭐가 죽나`.

[중요] **마스터는 골조를 만들지 않는다** (`#339`, 2026-08-30 — 그 경로를 코드에서 지웠다).
`#317` ①·`#319` 가 골조 제작을 요청자로 옮겼는데 `#319` 는 「나르기」만 없애고 「만들기」를
남겨 뒀고, 첫 실전 등재가 마스터에서 `claude:opus` 를 동시 2프로세스로 돌렸다. 등재가 하는
것은 **큐 등록과 매니페스트 수집**이다.
[완료] **파견은 자동이다** (`#340` `c33316e`·`9cc73d9`, 라이브 2026-09-01 — 4/4 · 10분 4초 ·
사람 개입 0). 요청자가 `task/<work_id>/base` 를 push 하면 그 이벤트가 `ax-dispatch.path` 를
깨우고, **파견이 끝나면 조각을 종결하고 `.33` 에 공지하는 것으로 끝난다** (2026-09-04 —
「통합까지 이어진다」는 종전 서술은 통합자와 함께 폐기됐다).
🔴 [중요] **사람 게이트는 **둘**이다 — 정본 7단계 (사용자 확정 2026-09-02):
**⑺ 전진 앞**(`ax-advance` 가 「버그냐 구조냐」를 묻는다) **와 finalize(`main` 머지)**.
[완료] **둘 다 코드에 있다** (2026-09-04): `advance_work(confirm=False)` 가 기본이고
`finalize_work(confirm=False)` 도 기본이다 — 승인 발화가 곧 트리거다.
[주의] **종전 서술 「사람 게이트는 finalize 한 곳뿐」은 폐기됐다** — 2026-09-01 에 내가 만든
게이트를 정정받은 것은 맞지만, 그 정정을 「통합 승인이 없다」로 넓혀 적은 것이 틀렸다.
[주의] **세션 한도로 멈추면 재개만 사람 지시다** (사용자 결정 2026-09-01): 보류가
`~/.cache/ax-dispatch/hold.json` 에 남아 **재부팅을 넘고**, 시각이 지나도 자동으로 풀리지 않는다.
`.33` 세션 시작 훅이 「재개 대기」를 고지하고, 푸는 것은
`python -m master.work.autodispatch --resume <프로젝트> <work_id>` 뿐이다.
[주의] **골조를 올렸는데 `[dispatch]` 줄이 하나도 없으면 배선이 죽은 것이다** — 파견은 걸었는지와
왜 안 걸었는지를 **둘 다** 찍는다. 그 침묵이 2026-08-29~31 이틀을 태웠다(리포트 44).

🔴 [중요] **분산 작업(work) 하나는 여러 라운드를 돈다** (사용자 확정 2026-09-05).
⑺ 에서 작업 브랜치를 전진시킨 뒤 더 고칠 것이 있으면 **같은 work 에 조각을 더한다** —
그것이 **개선요청**이고, 등록과는 **다른 호출**이다 (사용자 확정 2026-09-05).

    개선요청       `improve_work(work_id, round=현재+1)` — round +1 · 브랜치
                  `task/<work>/r<N>/<조각>` · ⑺ 머지 대상은 **그 라운드만**
                  [중요] 라운드 값이 어긋나거나 상태가 `ready_for_review` 가 아니면 **거절**
    등록          `register_work(title, specs)` — 새 분산 작업 (round = 1 · work_id 실으면 거절)
    마감          사람이 「더 없다」 할 때만 — `finalize` 가 `main` 머지 + 이슈를 **「완료」로 닫는다**

[중요] **레드마인 이슈는 등재 때 만든다** — 라운드 완료·⑺ 전진·사람의 결정이 그 이슈에
**노트로** 쌓인다(라운드마다 새 이슈를 만들지 않는다).
[중요] **파견 트리거는 둘이다 — 골조 push 와 등재.** 종전에는 push 하나뿐이라 「push 먼저,
등재 나중」이면 catchup(10분)을 기다렸다.
[주의] **골조에 `[FEEDBACK]` 을 쓰지 않는다** — 등재 게이트가 막는다. 층1 이 소스 잔재를
위반으로 잡고, 사전 훑기는 `[PSEUDO]` 개수로만 「할 일 있음」을 세기 때문이다. 기존 코드
수정 지시도 `[PSEUDO]` 로 쓴다.
[중요] **워커는 임시 저장소다** — 커밋·push 뒤 조각 브랜치·원격추적 캐시·`.ax/work/<task>` 를
지운다. 원격이 정본이므로 그 기계에 남길 것이 없다.

[중요] **서버로 가는 모든 「쓰는」 요청은 프로젝트 태그를 실어야 한다** (`#257`, 2026-08-22).
태그가 없거나 마운트와 다르면 **200 + `ok:false`** 로 거절되고 사유가 셋이다 — `no_project_tag`
(발신자 배선) · `not_mounted`(마운트 전환) · `project_mismatch`(work 스탬프 불일치 — `#210` 축이라
마운트와 비교하지 않는다). [주의] **발신자 배달이 서버 조임보다 먼저다** — 순서를 어겨 `.43`
상주가 20분간 폭주했다. 계약·표·순서 규칙: `~/ax-cluster/docs/13-request-tagging.md`

[중요] **승인 뒤는 손으로 정리하지 않는다** (2026-08-21, 원전 `finalize_work` 6단계 동등):
`finalize_work(confirm=True)` 가 머지·기재·정리를 이어서 한다. 기본값은 `confirm=False`(통합만 하고
멈춤)이므로 **승인이 곧 트리거**다. 🔴 **마감은 레드마인 이슈를 「완료」로 닫는다** (사용자
2026-09-04) — 종전의 *"「해결」까지만, 닫는 것은 사람"* 은 폐기됐다. 그 규약이 지키려던 것은
「사람이 판단한다」인데 이 호출은 승인 발화로만 돈다. [주의] 자동 삭제는 **`main` 에서 도달 가능한 것만** — 미병합은
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

[중요] **The write surface on this port is `/control/*`, and it is NOT public** (added 2026-09-08,
`54a0669`). It sits in `REQUESTER_SCOPE` only — measured on the live service: requester token 200,
**no token 401, worker token 403**. Writes were deliberately kept out of `/api/v1`, which is the
auth-less half. `/cluster` now opens with a **지휘 상태** card. 🔴 [중요] **It shows two different
things and they must not be conflated**: **마스터 담당** (`claude`/`codex`) is *the last recorded*
conductor — **not a liveness check, not a lock, and it neither starts nor stops a session**;
**워커 실행 모드** (`lane`/`claude`/`codex`) is the global default **for newly registered works**.
Existing `work.worker_mode` stamps take precedence and remain across later rounds; global
changes do not rewrite them or running pieces. Legacy unstamped works may still read the global
mode. [주의] Never render an exception string on this page — `str(OSError)` carries an
absolute path, which is exactly what `api_history` withholds (that defect shipped and was caught by
drawing the page for real, with 8 unit tests passing).

[중요] **The gates paid for themselves — and the live runs, not the unit tests, found the defects.**
Five real ones this session-and-the-last, each behind an injected seam while 63–96 unit checks
passed: layer 3's decoder on Korean UBT output · the skeleton contract hole (`[PSEUDO]` alone
doesn't compile for non-void) · an invented enum value · `decode()` returning `Decoded` not `str` ·
the integration step dying where the graph was absent. **Put one live run behind every gate.**

[중요] **Grounding, not the model, is what makes 층2 work** (measured 2026-08-12): 4 of 5 candidates
missed an invented enum member with no declarations in the prompt; all caught it with them. And
**local models are unusable for 층2** — 35B blocked two *correct* files. `agy`→`claude` is the
chain, and that default is now measured rather than assumed.

[중요] **This project has ZERO automation tests** (measured: no `AUTOMATION_TEST`/`FunctionalTest`
anywhere in `Source/`). §4.3's *"hallucinations that compile"* are catchable **only by tests**, so
층3's `RunTests` is deliberately **fail-open with a loud warning**. That hole cannot be closed by
code — writing tests is a project decision, parked in the milestone's 「예정」.

🔴 [중요] **Parallel is the default** (사용자 확정 2026-09-03). 정본 ⑸: *"작업을 전달받은
**워커들은** … **각각** 지정된 서브 브랜치에 커밋"*(다음 조각은 서버가 배정) —
**splitting per class exists for this.** Measured live 2026-09-03: pieces went to `.2` **and**
`.43` in one round. [주의] `autodispatch` now passes `parallel=True` **explicitly** — it used to
pass nothing, so the real path was always serial and no one could see it.

[주의] The 2026-08-09 measurement still stands as **fact** — two workers were 12% faster and 90%
more expensive; the 3.2× saving came from batching, not parallelism. **But whether to accept that
cost is the user's call, not a default I get to set.** Serial only when a caller says
`parallel=False`. Incremental progress remains the other half of the value: work accumulates
**in a state that always compiles**, which makes verification a premise, not an option.

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
[주의] **예외는 하나 — 읽기 조회의 경로 부재** (사용자 2026-11-08). 읽기 전용 조회 명령
(`rg`·`ls`·`cat`·`find`·`sed -n`·`head`·`git log/show/status`)이 `No such file or directory` 로
실패하면 멈추지 않고 **확인된 경로로 다시 조회**하며, 그 실패는 마지막 보고에 한 줄로 남긴다.
그 밖의 실패(쓰기·편집·게이트·검사·빌드·MCP 쓰기·git 쓰기·경로 부재가 아닌 조회 실패)는 위대로 멈춘다.
예방: 검색 대상 경로는 이번 세션에 존재를 확인한 것만 쓴다 — 짐작으로 넣지 않는다.
(실측: 하루에 4번, 짐작한 경로 하나로 작업이 멈춰 사용자 재개를 기다렸다)

[중요] **지시받은 대상 밖의 파일은 건드리지 않는다.** 대상 목록에 없는 파일을 고치려는
순간 멈추고 보고한다. 경로가 목록에 있는지는 판정이 필요 없다.

[중요] **사용자가 세션에 있는 동안 추측을 적립하지 않는다 — 대화로 묻는다.** 골조의
`questions` 가 이미 그 방식이다(모델의 제안을 답으로 적립하지 않는다). 사람이 컴퓨터 앞에
있는데 추측으로 진행하는 것이 가장 비싸다.

[중요] **이 파일과 게임 소스는 고치기 전에 계획을 말하고 동의를 받는다** (원전 1조, 범위는 사용자
결정 2026-08-14) — **이 파일은 매 세션 자동 로드되므로 한 줄이 모든 다음 세션을 바꾼다.**

[중요] **만들기 전에 기존 자산(이 저장소·테스트·리포트)을 읽는다** — 원전(`~/AgentTest`)은 그 기능이
원전에서 왔을 때 참고한다(포팅 종료 2026-10-18). 안 읽고 만들면 요구를 좁힌다
(그렇게 잃은 것 셋: 로컬 파일 웹 UI · 읽기 전용 화면의 로그인 · 원전 3,700줄을 안 읽고 새로 쓴
229줄 뷰어). **제약 하나를 지키려고 요구를 희생하면 결과물은 못 쓴다. 묻는 쪽이 늘 싸다.**

→ 위 셋의 근거·실측·범위와 원전 5조 대조표: `~/ax-cluster/docs/11-agent-conduct.md`

## Role in the AX cluster — this box is the **master**

The project repo is cloned **here** at `~/ax-cluster` (`PLAN.md` is the index, content in `docs/`)
and on BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`). The canonical remote is Gitea
(`gitea@192.168.0.57:Sim/ax-cluster.git`, private); master and BC-250 #1 both use it as `origin`.
GitHub (`SimSeoWon/ax-cluster`, **private — keep it that way**, it holds LAN addresses and firewall
rules) is a **push mirror driven by Gitea** — never push to GitHub directly: the mirror overwrites
it and prunes anything Gitea does not have (the master's `github` remote has its push URL disabled).
The board has `main` checked out so pushing there is rejected — **`git pull` on that side instead.**
`~/AgentTest` is the predecessor clone — **reference only. Never modify or push to it.**

### Windows remote Codex — operational memory (2026-10-04)

Use `workspace-write`, `windows.sandbox="unelevated"`, and
`sandbox_workspace_write.network_access=true` through the `/IT /RL LIMITED` conductor.
SSH sends job data and starts the task; Codex runs in the logged-in user's interactive session.
“Session 1” is a launcher name, **not a fixed SessionId** (`.33`: USER SessionId 18 measured).
Verify actual shell reads, **apply_patch writes**, and result recovery; task-start success alone
is insufficient. Official CLI 0.159.3 was used on all three AXCluster workers. `.2` and `.33`
passed source reads, apply_patch writes and result recovery late on 2026-10-03; the separate `.ax`
write failures remain unexplained. Do not turn this path comparison into an ACL root-cause claim.
AXCluster source was aligned and delivered through `b53fd84`; deployment evidence and scope
are in [report 89](../reports/89-codex-worker-readiness-and-write-probes.md) and
[report 90](../reports/90-r5-indexer-test-isolation-and-deployment.md). `.43:~/ax-cluster` is a
separate management clone; AXCluster worker delivery does not align that clone or other projects.
Shared details and evidence: [`../docs/windows-codex-remote.md`](../docs/windows-codex-remote.md).

### Machine inventory (initially probed 2026-08-08; AXCluster roles updated 2026-10-03)

| IP | Machine | Login | Role | Reachable from here |
|---|---|---|---|---|
| **.57** | **sim-desktop** — this box | `sim` | **Master**: orchestration, RAG index, ontology/graph, task queue, broker, project registry | — |
| **.2** | Windows + **RTX 3060**, UE5 installed<br>host `DESKTOP-HV0I6DL` | **`janus`**<br>(admin) |  **Worker** *and* inference endpoint #2 (gemma4:e4b pinned; user 2026-10-03). **The only machine that can run the layer-3 verdict unattended** (UE5 5.8). 🔴 **정본 ⑸: this box commits its piece to its own sub-branch; the master assigns the next piece** (사용자 확정 2026-10-31). The master drives builds over SSH (`run_build_on_workshop` calls `Build.bat` directly, so **no Python payload is needed to build**). **No resident daemon** — the master drives builds and pieces over SSH; session-1 work via `schtasks /run` (`AxConductor`). `#404`'s build resident was withdrawn 2026-10-31 (`#860`) | **`ssh janus@192.168.0.2`** [완료] passwordless · RDP 3389 · Ollama 11434 |
| **.33** | Windows 10.0.26200, RTX 3080 10GB, **user main work PC**<br>host `DESKTOP-FU2GNGL` | **`user`** | **Game requester** and Unreal entry point. **AXCluster worker** in `C:\trunk\AXCluster` while mounted (user 2026-10-03); master is AXCluster requester. Roles are per project; `dispatch` only narrows availability. `gemma4:e4b` resident verified; third broker endpoint active; three concurrent inference requests verified (2026-10-03). Dirty check before writes, keep game trees separate. | **`ssh user@192.168.0.33`** passwordless · RDP 3389 · Ollama 11434 |
| **.43** | **BC-250 #1** — Fedora, headless | `sim` |  **Worker** *and* inference endpoint #1. **35B residency was REMOVED 2026-08-17 (user decision ⓐ, measured #105)** — plain sequential inference grew GPU(GTT) allocations ~120MB/cycle and collapsed the node in 4 minutes; idle did not release it; only `systemctl restart ollama` did (NOPASSWD exists for it). Now pins **gemma4:e4b (~5GB, ~10GB headroom)** — the synth model, which also kills the old fallback-OOM hazard. The 35B stays on disk, unpinned. **e4b also fills the agentic-driver seat (#106 closed 2026-08-17)** — tool-calling gates 4/4 ×3 runs + Korean 3/3, 30-cycle sustained 30/30 with no #105-style accumulation (~-5MB/cycle vs 35B's -120). Fallback: `qwen3:8b` (4/4, lives on `.2`). Has the project clone at `~/trunk/ModularStage` — no longer stateless. 🔴 [중요] **This box is a committing worker too, exactly like `.2`** (사용자 정정 2026-09-02): **the memory limit decides only *which model* it may run locally, never whether it may commit**, and **building was never the worker's job** (the origin's per-task verify is static-only; UE5 belongs to the integration gate). I had blocked its commits on the strength of the "one writer" misquote and then re-justified it with memory/UE5 — neither reason holds. Inference it cannot host locally goes through the broker (8102). No resident daemon (user 2026-10-31, `#860`) — pieces arrive by master SSH push. Caps still come measured from `.ax/config.json` | `ssh sim@192.168.0.43` [완료] passwordless · Ollama 11434 · no RDP (headless since 2026-08-05) |
| — | BC-250 #2 | — |  **Bazzite gaming machine — NOT an inference node.** Converting it means giving up that machine. **Never assume a 2nd board exists.** | n/a |

### `.33` — the main work PC has its own guide

SSH and Ollama came up 2026-08-08; **the account is `user`**. On 2026-10-03 the user authorized
AXCluster worker use and resident inference: current `gemma4:e4b` was pulled and loaded,
`AX_READY` and `/api/ps` verified. `AX_Ollama33` is S4U/Limited/AtStartup (reboot untested).
Broker node is active after restart; concurrent inference across all three nodes was verified.
The AXCluster source changes recorded for that work were subsequently committed and deployed;
check current HEAD and dirty state instead of treating this historical probe as live state.

**Its role is `requester`** (2026-08-09): it registers work, verifies (UE5 is here, so compile
errors surface fastest), and writes `[FEEDBACK]` blocks. **For AXCluster only, its role is worker**
in `C:\trunk\AXCluster` (user 2026-10-03), with the master as requester. Roles are per project;
game requester entries remain excluded from dispatch. [주의] When it verifies, use **`git worktree`**, never a branch switch in the
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

    worker      implements pieces the master assigns over SSH   .2 · .43 · .33 (AXCluster only)
    requester   registers, verifies, gives feedback    .33 (games); master (AXCluster)

**Every worker holds the project clone and judges from source** — that is the point, and all
workers are equal in it. UE5 only decides *who can run the layer-3 verdict*. The per-machine
`<checkout>/.ax/config.json` is the single source of truth for paths/capabilities; it is
**generated by the master** (`python -m master.client deliver`), never hand-copied — a worker's
config was once found pointing at *another machine's* path.
After a commit, use `python -m master.client update`: it runs deliver→check for the **mounted
project's** workshops only (user 2026-10-06, `#655`); `update --all` keeps the old every-registered-
project rollout. Unmounted projects catch up **on mount switch** — `set_active` compares versions and
redelivers only the machines that are behind (`align=True` is now its default).
[중요] **Run it after every commit** — `check` fails when the delivered source commit is behind
`HEAD`, even when every file hash matches.
On Windows the same probe writes an absolute Python path into `backends.python`; client MCP and
`ax-fix` consume it instead of relying on the session's `py` PATH.
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

🔴 [중요] **백틱이 든 글은 셸을 거치지 않는다 — 파일에 써서 실행한다.** `python -c "… \`x\` …"`
에서 셸이 백틱을 **명령으로 실행**해 그 구절이 **조용히 사라진다** (표적: 레드마인 노트·커밋
메시지·리포트). **두 번 당했다** — 리포트 `73`(완료 노트 4구절) · `74`(종결 노트 8건).
[주의] 두 번 다 「조심한다」가 못 막았다. **막은 것은 경로를 바꾼 것이다.**

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
| [중요] **세션 시작에 먼저 읽을 둘** | `~/ax-cluster/docs/milestones/7-improvements.md`(열린 마일스톤) · `~/ax-cluster/docs/12-multi-project.md`(지금 열린 축). [주의] 항목·진행은 **레드마인만** |
| Working *in* the repo | `~/ax-cluster/CLAUDE.md` |

## Work journal

Numbered work reports accumulate in `~/ax-cluster/reports/` (in the repo; the older
`~/claude-workspace/reports/` stopped at 36). Reports are written in Korean — the user reads them.

- **Read the reports in full at session start** — grep is not a substitute. There is an incident
  where near-miss wording was filtered out and already-recorded work got re-investigated.
- **For infra work that needs a reboot or risks losing access, write the intended commands to a
  report file *before* running them and update it *during* the work** — if the connection drops,
  the file is the only surviving record of what was attempted.
- Afterwards, also update the preceding report's "remaining" list with what got done.
- [중요] **Reports are not the task list.** Work items live in **Redmine** (`:8080`).
  [중요] **AX 인프라 일감은 전용 프로젝트 `ax-cluster`(id 3) 에 둔다** (user decision 2026-09-28,
  supersedes 2026-08-09's "same as `ModularStage`"). A game/tool project's own issues go where its
  `<twin>/config.yaml` `redmine.project` says (`modularstage` · `ns` · `kimodo`).
  No fallback: unset means refuse (`#293`). Progress lives in the open milestone doc.
  Three places, three jobs — see `~/ax-cluster/CLAUDE.md` § Work flow.
