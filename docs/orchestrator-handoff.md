# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).

- **갱신 시각**: 2026-09-11 00:00 KST (UTC+9)
- **지휘 도구 / 세션 식별자**: Claude Opus 5 (1M) · `session_01762QMz8RB4gMSyu99T4Hev`
- **상태**: 🔴 **`#387` 파견 계측 — 배선 완료, 실물 한 번이 남았다.** 클러스터 깨끗.

## 🔴 바로 다음 작업 — `#387` 실물 계측 (다음 분산 작업 한 번이면 잡힌다)

배선은 `933a8df` 로 끝났고 3대 배달·`check` 초록까지 됐다. **남은 것은 완료 조건 1(실물)뿐**이고,
`.33` 에서 다음 라운드를 등재하면 **공짜로 잡힌다.** 그때 볼 것 넷:

    1  `<트윈>/usage_log.jsonl` 에 조각 수만큼 줄이 생기는가
    2  파견 로그에 `[usage] <task> lane=… mode=… 입력 N · 출력 M · $X|비용 미상`
    3  스풀 `responses/<work>/<task>.json` 의 `usage` 가 **비어 있지 않은가**
       — 이 일감의 원래 증상이 `usage: {}` 였다
    4  실패 조각이 섞이면 그쪽도 남는가 (없으면 **「못 쟀다」로 적는다** — 없는 실패를 만들지 않는다)

집계 표면: `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.usage --days 7 [프로젝트]`

[주의] 유닛이 다 통과한 채 라이브에서만 드러난 결함이 2026-09-10 하루에 **셋**이었다
(훅 문구 인젝션 거부 · 배달 검사기 거짓 실패 · 오염된 요청자 세션). **실물 전에는 닫지 않는다.**

그 뒤 후보: `#373`(캐시 prune — 재현 대상 보존 중) · `#396`(pre-push 가드) · `#384` ⑥.

## 사용자 결정 · 승인 범위 · 근거 / 미결 질문

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

    저장소   ~/ax-cluster   브랜치 main   HEAD 933a8df
             [완료] **세 곳 동기** — 로컬 · origin(GitHub private) · `.43`
             미커밋   docs/orchestrator-handoff.md (이 파일 · 커밋 승인 대기)

이 세션 커밋 3개:

    0b9fc62  feat(notice)  완료를 사람의 타이핑 없이 요청자에게 전달 — asyncRewake (정본 ⑹)
    97aae61  fix(mode)     요청자가 고른 지휘자가 서버까지 간다 (`#392`)
    962ec86  fix(check)    훅 항목 조립을 한 자리로 — 검사기가 정상 배달을 「미등록」이라 답했다
    a140d5e  docs          ⑹ 라이브 완주 기록
    933a8df  feat(usage)   파견 계측을 스풀·집계까지 잇는다 — 실패한 실행도 센다 (`#387`)

## 완료한 작업 / 검증 명령·결과

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
- **`#387`(사용량 전달) 미착수** · **`#384` ⑥ 종결 미착수** · **Codex MCP 미배선** — 그대로다.
- **실패한 것 없음.** rc≠0 로 멈춘 자리는 정리 중 pre-push 가드 하나이고, 그것은 설계대로
  사람에게 물으라고 멈춘 것이다.

## 새로 등재한 일감

    #396  [AX] pre-push 삭제 가드가 낡은 추적 참조로 판정한다 — 거짓 증거를 낸다
          실측: 가드가 `refs/remotes/gitea-write/main` 을 fetch 없이 읽어 `c5d2c6e`(낡음)로
          판정했고, 「이 커밋이 여기에만 있을 수 있다」 증거에 **이미 main 에 있는 사용자
          게임 소스 커밋 `d93e7c8`** 을 올렸다. 막는 방향은 옳으나 증거가 거짓이다

## 실행 중인 서비스 작업·프로세스 / 로그 위치

    상시    systemd 6종 active · `ax-dispatch.path` 보류 없음
    큐      works 1 (`20260910_2305_work_bd001657` · **merged** · 종결됨) · tasks 3 verified
    모드    `~/.cache/ax-dispatch/mode.json` = **claude**
    로그    파견   `journalctl -u ax-dispatch.service` / `-catchup`
            큐     `~/ax-state/.claude/logs/task_queue_*.log`
            🔴 완료 훅  `.33` 의 `<체크아웃>/.ax/work_completion.jsonl`  ← 이번에 새로 생긴 자리
    서브에이전트  없음

## 관련 문서 링크

- `docs/orchestrator-rules.md` · `docs/15-orchestrator-handoff.md`
- `docs/16-worker-orchestrator-mode.md`
- 리포트 `59`(codex 워커 지휘자 라이브) · **`60`(asyncRewake 실측 · 주입 경계)**
