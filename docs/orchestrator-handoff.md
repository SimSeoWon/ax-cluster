# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).

- **갱신 시각**: 2026-09-12 00:45 KST (UTC+9) — **지휘자 전환 readiness 구현·실물 확인**
- **지휘 도구 / 세션 식별자**: Claude Opus 5 (1M) · `session_01J3364LAVADSB4ZtwxbD5KK`
- **상태**: 워커 지휘자는 사용자 지시로 **`claude` 폴백**. `#398` ⑺ 전진·통합 빌드 완료,
  후속 `#400` 이 등재됐다. `#401` 지휘자 전환 준비·`.2` Codex 셸 결함을 기록했다.

## 🔴 바로 다음 작업

`#400`(work `20260911_2353_staggered_exhausted_2_5ea47a93`) 골조·파견 흐름을 이어간다.
전역 워커 지휘자는 `claude`이며 **다음 파견부터 적용**된다.

### 지휘자 전환 준비 — 구현·실물 확인, 커밋 승인 대기

`set_worker_mode`가 더는 `mode.json`만 쓰지 않는다. 활성 프로젝트의 SSH 워커마다 선택한
지휘자의 CLI 버전·`ax-work` 스킬을 확인하고, Windows Codex는 실제 Session 0 sandbox 셸
probe까지 통과해야 상태를 저장한다. 하나라도 실패하면 **모드 상태를 바꾸지 않는다.**

2026-09-12 NS 실물:

    claude  .2 2.1.266 OK · .43 2.1.222 OK      → 전환 가능
    codex   .2 0.153.4 셸 probe exit 1          → 전환 거절
            .43 0.153.4 OK

관련 회귀: `test_orchestration_control` 11/11 · `test_client_bundle` 308/308 ·
`test_mcp_servers` 48/48 · `test_work_mode_stamp` 15/15 · `git diff --check` 통과.

Redmine `#401`. 변경 파일은 `master/client/bundle.py` · `master/work/conductor.py` ·
`master/projects/mcp_server.py` · `master/test_orchestration_control.py` · 이 핸드오프다.

## 이전 순서 기록 — **(가) → (나) → (다)** (사용자 확정 2026-09-11)

**(가) `.33` 에서 `#398` 의 ⑺ 전진.** work `20260911_2238_ai_groggypanicked_a8879051` 은
**`ready_for_review` · 4/4 verified** 로 서 있다(Redmine `#398` · 브랜치
`task/20260911_2238_ai_groggypanicked_a8879051`, base `fa38594c`). `ax-advance` 로 네 조각을
머지하고 통합 빌드로 판정한다. 🔴 [중요] **조각 `16d2adf7` 은 워커가 `ax-work` SKILL.md 를
읽지 못한 채 프롬프트만으로 쓴 산출물이다** — 이번 통합 검사는 형식이 아니라 실질이다.

**(나) `[AX]` 등재 — `.2` codex 셸 실행 결함.** `unelevated` 로 편집·커밋은 처음 성공했으나
`command_execution` 은 여전히 `0xC0000142` 로 죽는다(아래 §부분 성공).

**(다) `[AX]` 등재 — 중간 정지 공지 결함.** 파견이 실패로 끝나 **활성 실행 0** 인데 work 이
`in_progress` 라는 이유로 `.33` 완료 훅이 상태만 적고 세션을 깨우지 않는다. 이번에는 결국
`ready_for_review` 까지 가서 공지가 났지만(23:21 `signal_emitted` · exit 2 · 278자),
**중간에 멈추면 요청자는 여전히 모른다.** 사용자: *"요청자가 모르는 상태로 멈추면 자동화로서
실패한 거야."*

## 사용자 결정 · 승인 범위 · 근거 / 미결 질문

- 🔴 **`.2` 의 codex 샌드박스를 `elevated` → `unelevated` 로 바꿨다 (사용자 승인 2026-09-11).
  「해결」이 아니라 「부분 성공」으로 읽는다** — 얻은 것과 잃은 것이 같이 있다:
  - [완료] **편집·커밋이 처음으로 됐다.** `.2` codex 모드는 09-09부터 4전 4패였는데
    (09-09 23:17·23:18 · 09-10 00:23 · 09-11 22:51), 바꾼 뒤 `16d2adf7` 이
    `75239c2b · 파일 3` 으로 커밋되고 verified 됐다.
  - 🔴 [주의] **PowerShell `command_execution` 3건은 여전히 `0xC0000142` 로 죽었다.**
    그래서 워커는 **`ax-work` SKILL.md 를 읽지 못한 채** 마스터가 프롬프트로 준 지시만으로
    본문을 썼다. 층1은 통과했지만 **눈을 반쯤 감고 통과한 것**이다.
  - 🔴 [주의] **격리 하나를 잃었다** — upstream `#35940` 의 「Why `unelevated` is not a
    workaround」 절: *"leaves the network reachable even with `--sandbox-state-disable-network`"*
    · *"kills child processes created with piped stdio"*. 뒤엣것이 잔여 셸 실패의 가장 잘
    맞는 공개 설명이고(확정은 아니다), 앞엣것은 **`.2` 워커의 샌드박스 네트워크 차단이 지금
    풀려 있다**는 뜻이다.
  - 되돌릴 자리: `C:\Users\janus\.codex\config.toml.bak-20260911-elevated` (L80 한 줄).
- 🔴 **원인은 upstream 결함으로 확정됐다 — 우리 배선 문제가 아니다** (2026-09-11 실측 + 공개
  이슈 대조, 세 건 모두 실재 확인):
  - **`openai/codex#37722`** (open · 2026-08-09) — 제목이 *"Confirmed root cause … missing
    inherited Window Station/Desktop access in a Windows OpenSSH Session 0"*. `elevated` 는
    `CreateProcessWithLogonW` 로 `CodexSandboxOffline` 계정을 띄우는데 `lpDesktop` 을 비워
    Session 0 서비스 Window Station/Desktop 을 **상속**하고, 그 객체에 샌드박스 계정 ACE 가
    없어 runner 가 `0xC0000142` 로 죽는다. **우리가 잰 오류 문자열과 글자까지 같다**
    (`timed out after 15000ms connecting runner pipe-in`). 본문에 A-B-A 실험이 있다 —
    ACE(`0x000F006E`/`0x000F00CF`) 추가 시 성공, 원복 시 재실패, DACL SHA-256 동일 복원.
  - **`#18620`** (open) — *"file edits inside the workspace still work"* 인데 셸만 죽는
    같은 모양. 단 오류 코드는 1326/1909 로 우리와 다르다.
  - **`#35940`** (open) — 위 「unelevated 는 우회가 아니다」의 출처. 같은 이슈가
    *"`codex exec` does **not** leak. Only `codex sandbox` does"* 라고 적는다.
  - 🔴 **더 나은 대안이 있다**: `#37722` 이 증명한 것은 「`elevated` 를 못 쓴다」가 아니라
    **ACE 하나가 빠졌다**이다. Session 0 의 Window Station/Desktop 에 샌드박스 계정 SID 로
    최소 ACE 를 넣으면 `elevated` 가 SSH 에서 그대로 돈다 — 네트워크 격리와 파이프 자식이
    정상인 쪽이다. [주의] **보안 객체 DACL 을 건드리는 일이라 사람 승인 없이 하지 않는다**,
    그리고 **세션마다 다시 넣어야 하는지는 미검증**이다(이슈도 임시 추가 후 원복했다).
- 🔴 **Codex CLI 모델을 `gpt-6-astra` → `gpt-5.6-sol` 로 내렸다** (사용자 결정 2026-09-11 —
  한도 절약). **네 대 전부** `~/.codex/config.toml` 최상단 `model = "gpt-5.6-sol"` 한 줄이고,
  `codex doctor` 로 네 대 다 `model gpt-5.6-sol · openai` · parse ok 확인했다. 백업은
  `config.toml.bak-20260911`. **다음 호출부터 적용** — 돌고 있는 세션은 재시작해야 바뀐다.
  추론 등급(`CODEX_REASONING = "medium"`)과 레인 순서는 건드리지 않았다.
- 🔴 **훅에 명령형을 싣지 않는다** (실측 2026-09-10, 리포트 60). 깨어난 모델이 **주입으로
  거부한다.** 「무엇이 왔나」는 훅, 「그래서 무엇을 하나」는 스킬. `~/CLAUDE.md` 에 규칙으로
  박혔고 `test_signal_carries_facts_only` 가 회귀를 막는다.
- 🔴 **미결 — `improve_work(worker_mode=)` 의 사용 여부.** 「같은 work 은 같은 지휘자로
  돌아야 라운드 간 비교가 성립한다」(종전 주석)와 「막히면 그때 스왑한다」(2026-09-09 지시)가
  부딪힌다. **배선만 두고 스킬에 「사람이 정하기 전엔 쓰지 않는다」를 적었다.**
- 🔴 **미결 — 워커 지휘자 기본값.** 상수는 여전히 `_UNDECIDED_DEFAULT`(값 `lane`).
- 🔴 **미결 — `#233`·`#229` 의 처분.** 2026-09-06 감사 노트의 `[주의]` 단서가 그대로다.
- **실증 더미는 남기지 않는다** (사용자 2026-09-09·2026-09-10) — `#390`·`#395` 삭제했다.

## 저장소 · 브랜치 · HEAD / 미커밋 파일

    저장소   ~/ax-cluster   브랜치 main   HEAD (아래 커밋 목록의 마지막)
             [완료] **세 곳 동기** — 로컬 · origin(GitHub private) · `.43`
             미커밋   docs/orchestrator-handoff.md (이 파일 · 커밋 승인 대기)

이 세션 커밋 3개:

    0b9fc62  feat(notice)  완료를 사람의 타이핑 없이 요청자에게 전달 — asyncRewake (정본 ⑹)
    97aae61  fix(mode)     요청자가 고른 지휘자가 서버까지 간다 (`#392`)
    962ec86  fix(check)    훅 항목 조립을 한 자리로 — 검사기가 정상 배달을 「미등록」이라 답했다
    a140d5e  docs          ⑹ 라이브 완주 기록
    933a8df  feat(usage)   파견 계측을 스풀·집계까지 잇는다 — 실패한 실행도 센다 (`#387`)

## 완료한 작업 / 검증 명령·결과

### 🔴 `#387` 실물 계측 — **네 조건 전부 잡혔다** (2026-09-11 22:48~23:21)

`NS/usage_log.jsonl` **8행**(조각 4 + 실패 시도 4). 🔴 **rc=1 행이 4개** — 「실패한 실행도
센다」가 실물로 확인됐다. 스풀 `NS/responses/<work>/<task>.json` 의 `usage` 도 네 건 다 비지
않았다(이 일감의 원래 증상이 `usage: {}` 였다). 파견 로그에 `[usage] … 비용 미상` 도 찍혔다.

    22:48:38  ff5e6188 @.2   rc1  입력   157,529 (캐시   144,768)  출력  1,092   45.8초
    22:49:48  b1d68625 @.43  rc0  입력   231,237 (캐시   194,560)  출력  3,028  114.1초
    22:50:50  ff5e6188 @.2   rc1  입력   576,588 (캐시   538,496)  출력  3,879  123.4초
    22:51:26  7ad0d155 @.43  rc0  입력   187,872 (캐시   152,832)  출력  2,004   89.6초
    22:59:41  16d2adf7 @.2   rc1  입력   159,223 (캐시   146,176)  출력  1,116   59.8초
    23:01:03  ff5e6188 @.43  rc0  입력   215,958 (캐시   189,440)  출력  1,878  145.2초
    23:10:57  16d2adf7 @.2   rc1  입력   447,470 (캐시   425,728)  출력  3,757  118.6초
    23:21:09  16d2adf7 @.2   rc0  입력 1,224,264 (캐시 1,185,792)  출력 11,341  344.0초
    ────────────────────────────────────────────────────────────────────────────
    합계  입력 3,200,141 · 출력 28,095 · **비용 전부 미상**(`cost_known=false`)

🔴 [주의] **입력 수치를 「태운 토큰」으로 읽지 않는다** — 마지막 행은 1,224,264 중
**1,185,792 가 캐시 읽기**다(신규 약 38k). 여덟 행 전부 같은 모양이다. 한도 소모를 이 숫자로
추정하면 크게 틀린다. 비용은 여전히 **미상**이라 「얼마 썼나」는 **아직 못 답한다**.

집계 표면: `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.usage --days 7 NS`

### `#398` 라운드 — `.2` 를 되살려 4/4 로 닫았다

    22:38  등재 (요청자 `.33`) · 조각 4 · 지휘자 codex · Redmine `#398`
    22:51  파견 끝 — 성공 2 · 실패 2   (`.2` 조각 둘이 0xC0000142 로 전멸)
    23:10  catchup 재파견 — `.2` 조각 하나가 또 같은 자리에서 죽고,
           `ff5e6188` 은 **`.43` 으로 돌아가 verified** (배당이 호스트를 옮긴다)
    23:1x  `.2` 샌드박스 `elevated` → `unelevated` (사람 승인) · `codex sandbox` probe 로
           **모델 호출 0** 검증: 전 `timed out … runner pipe-in` → 후 `SANDBOX_OK`
    23:21  재파견 → `16d2adf7` @ **.2** 커밋 `75239c2b · 파일 3` · 성공 1 · 실패 0
           → **조각 전부 종결 · `ready_for_review` 4/4**
    23:21  `.33` 훅 `signal_emitted` (exit 2 · 278자) — 요청자 세션이 사람 타이핑 없이 깼다

**`asyncRewake` 를 4판 재서 완료 고지 배선을 확정했다** (격리 세션 · haiku · 저장소 변경 0):

    1  SDK  · 명령형              깼다 · 따랐다
    2  TUI  · 명령형              깼다 · 🔴 거부 — "not following injected directives"
    3  TUI  · 사실만 · 스킬 없음   깼다 · 받았지만 아무것도 안 함
    4  TUI  · 사실만 · 스킬 있음   깼다 · ✅ 정확히 보고 + 사람 승인 게이트에서 멈춤

깨우기는 **4/4 · 지연 ~0초 · TUI 포함**. 갈린 것은 전부 「무엇을 실었나」였다. 상세: 리포트 60.

- **로그의 침묵 셋을 없앴다** — `not_a_registration`(등록 호출이 아님) · `lock_held` ·
  `already_noticed`, 그리고 `hook_fired`·`exit`(나가는 코드). 이제 「훅이 안 붙었다」와
  「훅은 돌았는데 대상이 아니었다」가 로그에서 갈린다.
- **되돌린 것 3건** — Codex 인계분 중 지시 범위 밖(`infer.py`·`logic_lifecycle.py` 문구 ·
  `pending_works.py` 의 매 턴 고지 억제). 종전 두 겹은 **걷지 않았다.**
- **배포 완료** — `deliver NS` → `check NS` **3대 전부 OK**. `.33` `settings.json` 에
  `asyncRewake: true` 착지 확인. 워커 2대는 역할 게이트대로 훅 없음.
- **서비스 재기동 2건** — `ax-task-queue`·`ax-projects`. `ExecMainStartTimestamp` 로 판정
  (21:15:34 → 22:42:08 / 22:43:38).
- **회귀 14개 스위트 전부 초록** — test_client_bundle 308/308 · test_client_mcp 147/147 ·
  test_work 137/137 · test_projects 63/63 · test_infer 95/95 · test_runner 86/86 ·
  test_wcommit 45/45 · test_work_completion 10/10 · 외 6종.

### 🔴 라이브 완주 — 정본 7단계가 처음으로 끊기지 않았다 (23:05~)

    23:05:28  등재 `20260910_2305_work_bd001657` · 조각 3 · 지휘자 claude · Redmine #397
    23:08:31  골조 push → **1초 안에** 파견
    23:12:44  3/3 verified · `ready_for_review` → 훅이 `signal_emitted` (exit 2 · 223자)
              🔴 **`.33` 세션이 사람 입력 없이 스스로 깨어 결과를 받았다**
    이어서   ⑺ `ax-advance` (사람 승인) → 통합 빌드 → 마감 `main` 머지 · `#397` 「완료」
    ──────────────────────────────────────────────────────────────────
    등재→완주 **7분 16초** · 3/3 · 실패 0 · 재시도 0 · 개입 0

깨어난 세션이 **스스로** ⑴ 사실을 요약하고 ⑵ *"main 으로 바로 가는 게 아니라 작업 브랜치를 한 칸
전진"* 이라 갈랐고 ⑶ **워크트리**를 쓰겠다 했고 ⑷ **승인을 물었다.** 훅이 보낸 223자에는 이 중
아무것도 없다 — 전부 `ax-request` 스킬(신뢰 경로)에서 왔다. 격리 4판이 예측한 그대로다.

[주의] **첫 시도는 오염된 세션 하나로 태웠다** — `.33` 이 지워진 `bf7a6533` 을 사실로 들고 왔다.
출처를 전부 막아 확인한 결과 남은 곳은 `.33` 의 세션 기록(`~/.claude/projects/…/*.jsonl`)뿐이었다.
🔴 **「정리했다」의 증명 범위에 요청자 세션 문맥은 안 들어간다 — 실증 전 `.33` 세션은 이어 열지
말고 새로 연다.** (`.33` 에 자동 메모리는 없다.)

### 정리 — 전수 증명 (어제 실증분 `20260910_0116_work_bf7a6533`)

    Redmine #395     삭제 (DELETE 204 → 되읽기 404)
    큐               works=[] · tasks=[] · `_index.md` 표까지 비움
    트윈             NS/responses/ 비었다
    Gitea 원격       `refs/heads/main` **하나만** 남았다 (task 3개 삭제)
    .2 · .33 · .43   전부 `main` 뿐 · origin/task 전부 pruned · reflog expire 완료
    보류             `hold.json` 없음

[주의] **브랜치 3개 삭제는 pre-push 가드(`#125`)를 `--no-verify` 로 넘겼다** — 사용자 승인.
버린 커밋은 골조 `59b09ef` · 워커 산출물 `ccd3371`·`1360d1a` 셋이고, 전부 어제 실증 산출물이다.

## 미검증 / 실패·보류 사유

- ~~⑹ 라이브 미검증~~ → **완주했다** (아래 §라이브 완주). 남은 미검증은 아래 둘뿐이다.
- **훅 `timeout` 7260초의 상한 초과 시 CLI 동작은 안 쟀다.**
- ~~**`#387` 미착수**~~ → **실물 4조건 충족** (위 §완료). 남은 것은 **비용 산정**이다 —
  `cost_known=false` 라 토큰은 세지만 돈은 못 센다.
- **`#384` ⑥ 종결 미착수** · **Codex MCP 미배선** — 그대로다.
- 🔴 **`.2` 의 잔여 셸 실패 원인 미확정.** `unelevated` 에서도 `command_execution` 이
  `0xC0000142` 로 죽는다. `#35940` 의 *"kills child processes created with piped stdio"* 가
  가장 잘 맞지만 **공개 자료만으로는 확정 못 한다** — `%USERPROFILE%\.codex\.sandbox\` 의
  날짜별 로그와 시스템 이벤트 26 을 대조해야 한다.
- 🔴 **`elevated` + Session 0 ACE 대안은 미검증.** `#37722` 의 A-B-A 는 남의 기계 것이고,
  **우리 `.2` 에서 재현한 적 없다.** 세션마다 재적용이 필요한지도 모른다.
- [주의] **내 진단 probe 가 부작용을 남겼다** — `codex sandbox` 를 `.2` 에서 4회 돌렸고,
  `#35940` 에 따르면 그 호출은 **호출당 로그온 세션 하나를 흘린다**(재부팅 전까지 회수 불가).
  4개는 무해한 양이지만 기록해 둔다. `codex exec` 는 안 흘린다.
- **실패한 것 없음.** rc≠0 로 멈춘 자리는 정리 중 pre-push 가드 하나이고, 그것은 설계대로
  사람에게 물으라고 멈춘 것이다.

## 이번 세션에 닫은 일감 (근거와 함께)

    #393  test_mcp_servers 도구 수      전체 회귀 5027/5027 로 해소 확인
    #391  워커 stdout 폐기              🔴 라이브에서 `[agent] … 말:` 이 실제로 남았다
    #389  지휘자 모드 work 스탬프        🔴 라이브 `지휘자=claude (work 스탬프) — 파견 전체 고정`

**닫지 않고 노트만 남긴 것** — 왜 안 닫는지가 노트에 있다:

    #392  절반만 됐다. **진행 중** 라운드의 모드는 여전히 못 고치고, 그것이 옳은지가 미결
    #385  라이브 완주했으나 **완료 조건 4(기본값을 사람이 정한다)** 가 남았다
    #356  요청자 세션은 이제 불린다. 그러나 **Redmine 자신의 알림 채널**은 그대로다 —
          세션을 안 열어 둔 사람·팀 배포는 여전히 안 잡힌다. 훅으로 대체됐다고 적지 않는다
    #388  revise 루프는 **이번에도 못 쟀다** — 실패한 조각이 0이었다.
          🔴 없는 실패를 만들어 재지 않는다

## 새로 등재한 일감

    #396  [AX] pre-push 삭제 가드가 낡은 추적 참조로 판정한다 — 거짓 증거를 낸다
          실측: 가드가 `refs/remotes/gitea-write/main` 을 fetch 없이 읽어 `c5d2c6e`(낡음)로
          판정했고, 「이 커밋이 여기에만 있을 수 있다」 증거에 **이미 main 에 있는 사용자
          게임 소스 커밋 `d93e7c8`** 을 올렸다. 막는 방향은 옳으나 증거가 거짓이다

## 실행 중인 서비스 작업·프로세스 / 로그 위치

    상시    systemd 6종 active · `ax-dispatch.path` 보류 없음
    큐      works `20260911_2238_ai_groggypanicked_a8879051` = **ready_for_review 4/4**
            (Redmine `#398` · `.33` 의 ⑺ 대기) · 활성 조각 0 · 파견 프로세스 없음
    모드    `~/.cache/ax-dispatch/mode.json` = **codex** (2026-09-11 21:59 사용자 전환)
    `.2`    🔴 `~/.codex/config.toml` **`sandbox = "unelevated"`** · 모델 `gpt-5.6-sol`
            · codex-cli **0.153.4** (마스터는 0.154.0 — 어긋나 있다)
    로그    파견   `journalctl -u ax-dispatch.service` / `-catchup`
            큐     `~/ax-state/.claude/logs/task_queue_*.log`
            🔴 완료 훅  `.33` 의 `<체크아웃>/.ax/work_completion.jsonl`  ← 이번에 새로 생긴 자리
    서브에이전트  없음
    🔴 `.43`  **켜져 있다** (2026-09-11 21:30 실측 — SSH·`codex doctor` 응답). 00:10 인계의
              「정지됨」은 낡았다 — 워커가 `.2`·`.43` 둘이라 **병렬이 실제로 병렬이다**.
              한 대만 살아 있을 때는 파견 로그가 그 사실을 찍는다
              (`병렬이지만 파견 가능한 워커가 1대`)

## 관련 문서 링크

- `docs/orchestrator-rules.md` · `docs/15-orchestrator-handoff.md`
- `docs/16-worker-orchestrator-mode.md`
- 리포트 `59`(codex 워커 지휘자 라이브) · **`60`(asyncRewake 실측 · 주입 경계)**
