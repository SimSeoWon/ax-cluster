# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).

- **갱신 시각**: 2026-09-08 23:55 KST (UTC+9)
- **지휘 도구 / 세션 식별자**: Claude Opus 5 (1M) · `session_01FxSaHM9KL43bGRDj2r9cHX`
  [완료] **담당이 기록됐다** — `conductor.json` `agent=claude` (2026-09-08T23:48:06+09:00,
  사용자 승인). `/cluster` 화면과 `get_orchestration` 이 그것을 보여 준다.
  [주의] **잠금이 아니다** — 코덱스 한도가 풀리면(09-09 03:58) 그쪽에서 `codex` 로 바꾸면 된다.
- **상태**: 🔴 **Codex → Claude 인계 완료 — 예고 없는 종료에서 복구했고, 그 자리를 마감했다.**
  Codex 가 **작업 중 한도 소진**으로 끊겼고(*"You've hit your usage limit … Sep 9th 3:58 AM"*),
  사용자가 미리 지시해 둔 대로 Claude 가 이어받아 **커밋·배달·재기동까지 끝냈다**.
  [중요] `#384` §15.6 **④(Codex → Claude)와 ⑤(중단 복구)를 실제로 돈 것**이다 — 모사가 아니다.
  🔴 **잃은 변경 0 · 중복 작업 0 · 재설명 0.**

## 🔴 이번 구간에서 끝난 것 (2026-09-08 23:10~23:55)

    커밋   54a0669  feat: 지휘 상태 표면 — `.33` 에서 워커 모드 변경 · 웹에 담당 표시
           신규 4  master/work/conductor.py · projects/control_route.py ·
                   webui/orchestration.py · test_orchestration_control.py
           수정 5  auth.py(REQUESTER_SCOPE 3줄) · projects/__main__.py · mcp_server.py ·
                   webui/routes.py · client/runtime/client_mcp.py
    동기화  로컬 · origin(GitHub private) · `.43` **모두 54a0669** (사용자 승인 후 푸시)
    배달   `deliver NS` → `check NS` **3대 전부 OK · 마스터 HEAD 와 같다**
           (직전에는 3커밋 뒤처짐 + 배달 시점 트리가 dirty 였다)
    재기동  `sudo -n /usr/bin/systemctl restart ax-projects` — **승인 사항이었고 승인받았다**
           판정은 exit code 가 아니라 `ExecMainStartTimestamp` 22:37:21 → 23:46:26

**운영 서비스에서 실물로 잰 것** (유닛 테스트가 아니다):

    GET  /control/orchestration  요청자 토큰   200 + 상태 JSON
    GET  /control/orchestration  무인증        **401**
    POST /control/worker-mode    워커 토큰     **403**
    /cluster (무인증 공개)        「지휘 상태」 카드 렌더 · `/home/sim` **0건**
    MCP                          재기동 뒤 `get_orchestration_tool`·
                                 `record_master_conductor_tool` 이 실제로 등장했다

**Claude 가 고친 것 하나** (사용자 승인 *"지금 같이 고침"*): `webui/orchestration.py` 가
`str(OSError)`·`note` 를 무인증 화면에 그대로 실었다 → 절대 경로가 찍힌다(`api_history` 가
본문·절대 경로를 빼는 것과 **같은 자리**). 고정 문구로 바꾸고 **두 경로를 주입 실증**했다.

**테스트 (Claude 가 직접 재실행)**: `test_orchestration_control` 8/8 · `test_auth` 60/60 ·
`test_client_mcp` 147/147 · `test_viewer` 79/79.

## 🔴 두 상태를 섞지 않는다 — 이 기능이 지키는 구분

    마스터 담당   claude / codex   **마지막으로 기록된** 지휘자.
                                  프로세스 생존 판정도, 잠금도, 세션 실행·종료도 아니다
    워커 실행 모드 lane/claude/codex  다음 **조각**부터 적용되는 전역 설정.
                                  실행 중인 조각에는 소급되지 않는다 · 프로젝트별·워커별 선택은 없다

## 사용자 결정## 사용자 결정 · 승인 범위 · 근거 / 미결 질문

- [완료] **축 = `#385`** (사용자 2026-09-08 *"오 맞는거 같아!"* → Codex 질문에 대한 답).
  용어 정리: 사용자가 말한 **「코덱스 폴백」 = `#385` 워커 지휘자를 Codex 로 전환하는 것**이다.
- **미결 — 래퍼(RHI 식 어댑터) 도입 여부.** 사용자 질문 2026-09-08:
  *"언리얼에 RHI 처럼 코덱스, 클로드 이런식으로 래핑하는게 좋을가?"* → §래퍼 참조. **결정 안 났다.**
- **승인 없음 — 이 세션은 커밋·푸시를 하지 않았다.** 아래 「미커밋」의 이 파일이 전부다.
- **기본값 미결** (사용자 2026-09-08): 워커 지휘자 모드의 기본값은 아직 사람이 안 정했다.
  코드 상수는 `_UNDECIDED_DEFAULT`, 값은 현재 동작(`lane`) 유지.
  [주의] **저장 상태는 지금 `codex` 다**(실증용으로 켠 채) — 되돌릴지도 미결이다.
- **유효한 금지** (사용자 지시 2026-09-08, 아직 안 풀렸다): **새 work 생성 금지 ·
  미병합 브랜치 삭제 금지.**

## 저장소 · 브랜치 · HEAD / 미커밋 파일

    저장소   ~/ax-cluster   브랜치 main   HEAD 403f6ef (2026-09-08 23:05 확인)
             [주의] 종전 기록은 d7e3e88 이었다 — 그 뒤 커밋 3건이 더 있다:
                f2cd6a2  feat: 워커 지휘자 모드 (`#385`) — lane / claude / codex
                3b7c536  fix: 스킬 배달 경로를 도구별로 (codex 는 `~/.claude/skills/` 를 안 본다)
                403f6ef  docs: `#385` 실증 결과와 하루 마감 기록
             [미확인] origin·`.43` 동기화 여부는 이 세션에서 안 쟀다
             미커밋   docs/orchestrator-handoff.md (이 파일 · 커밋 승인 대기)
             워크트리 없음 (`git worktree list` = main 하나)
             [주의] 종전 기록의 로컬 워크트리 `scratchpad/ns-base` 는 **지금 없다**

## 완료한 작업 / 검증 명령·결과

이 세션은 **대조만** 했다. 코드·설정 변경 0건.

    mode.json     {"mode":"codex","at":"2026-09-08T01:45:15+09:00","why":"#385 실증"}
    hold.json     없음 → 재개 대기 없음
    서비스        ax-task-queue · ax-broker · ax-projects · ax-indexer.path ·
                  ax-dispatch.path · ax-status.timer  → 전부 active
    work          20260908_0146_ax_385_codex_452cc503  merge_status=ready_for_review
                  round 1 · total 1 · verified 0 · redmine 386
    조각          f4db3ad4  status=failed  worker=192.168.0.2  attempt=1  epoch=1
                  fail_reason  BLOCKED
                  fail_detail  층1 위반 1: Source/NS/AxModeProbe.cpp `[PSEUDO]` 잔재
                  failed_at    2026-09-08T01:48:39+09:00
    보존 work     20260905_1705_..._2f005681 (7/7 verified · merged) — 실증과 무관

## 🔴 종전 기록의 정정 — 재시도 경로는 **있는데 이 실패엔 못 쓴다**

종전 기록: *"지원되는 재시도 경로를 아직 못 찾았다."* → **절반만 맞다.**

    있다   POST /api/v1/tasks/{task_id}/reverify   (server.py:392)
    구현   logic_lifecycle.py:291 reverify_task — status 를 failed → **submitted** 로만 뒤집는다
    전제   "커밋이 이미 올라가 있고 verify-loop 가 다시 본다"

🔴 **우리 실패는 커밋 *전*이다** — 층1 이 `wcommit` 에서 막았고 조각 브랜치는 base 그대로다.
`submitted` 로 만들면 **없는 산출물을 있다고 적는 것**이다. `failed → pending`(재파견) 경로는
큐에 **없다**(`logic_lifecycle.py` 의 failed 전이는 `reverify` 하나뿐).

→ **필요한 상태 변경**은 둘 중 하나이고, 고르는 것은 사람이다:
  ⓐ 조각 `f4db3ad4` 를 `pending` 으로 되돌리는 경로를 **새로 만든다**(큐 API 추가 = 코드 변경)
  ⓑ 그 조각을 `cancel` 하고 **같은 work 에 라운드를 더한다**(`improve_work`, round=2)
     [주의] ⓑ 는 「새 work 생성 금지」에 걸리지 않는다 — 같은 work 이다. 다만 브랜치가
     `task/<work>/r2/<조각>` 으로 새로 나므로 r1 잔재 2건은 그대로 남는다

## 🔴 래퍼(RHI 식) 질문 — 원전 대조 결과 (Claude 세션 2026-09-08 실측)

「만들기 전 3문」 ①(원전에 있나) → **있다. 다만 클래스 계층이 아니다.**

    ~/AgentTest/worker/worker.py:78        _VALID_WRITE_BACKENDS = ("", "local_llm", "agy", "claude")
                                           문자열 enum · 모르는 값은 경고 후 거절
    ~/AgentTest/worker/claude_spawn.py:243 call_llm(prompt, cfg, cwd, ..., force_kind)
                                           함수 하나가 라우팅 · `_call_cli_llm` 안에서 kind 분기
                                           폴백은 **한 겹만** (로컬 LLM → claude)

🔴 **판정은 어댑터에 넣지 않는다** — 원전 주석: *"출력의 `TASK_COMPLETE` 는 보조 신호,
최종 판정은 `_validate_disk_after_agent`"*. 우리 `wcommit` 되읽기·층1 이 그 자리다.
→ 우리 `agent_command(mode=...)` + 갈래 파서가 **이미 그 모양**이다. Codex 의 결론
(*"얇게 감싸는 것"*)과 원전이 일치한다.

## 🔴 `AX_PROJECTS_ROOT` 실패 — 도구 차이가 아니라 **진입 문서 결함의 재발**

Codex 가 `.venv/bin/python -m master.client plan NS` 에서 `ConfigError` 로 멈췄다(§1.1 준수).
원인을 쟀다:

    셸 프로파일   ~/.bashrc · ~/.profile · 현재 셸 → **0건**. 클로드도 안 주면 똑같이 실패한다
    클로드가 안 걸린 이유   ~/.claude/settings.local.json 의 허용 규칙 ~10건이
                            `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 **명령 접두에 박아** 뒀다
    문서            ax-cluster/CLAUDE.md:321 이 그 형태로 적는다
    🔴 AGENTS.md   `master.client`·`venv/bin/python`·`AX_PROJECTS_ROOT` **전부 0건**

→ **2026-09-08 에 이미 잡았던 결함의 재발**이다(*"두 진입 파일은 각각 자족적이어야 한다"*).
`AGENTS.md` 를 **홈 지침** 기준으로만 채우고 **저장소 `CLAUDE.md` 의 명령 블록**은 안 옮겼다.
[중요] **래퍼로 감싸면 이 구멍을 가린다** — 고치는 게 아니다. 보강은 **별건**이고 승인 대상이다.

## 🔴 코덱스의 「마스터 호출 경계」 — 새로 만들 것이 아니라 **MCP 미배선**이다

    ~/.codex/config.toml   93바이트 · `[mcp_servers]` **0건** (리포트 55 서술과 일치)

마스터 호출 경계는 이미 **MCP** 이고 그 서버는 systemd 아래에서 환경을 갖춘 채 돈다.
Claude 는 `mcp__ax-projects__*` 로 불러서 환경변수를 만질 일이 없고, Codex 는 MCP 가 없어
**생 셸로 내려가서** 그 전제에 걸렸다. → 할 일은 새 계층이 아니라 **연결**이다.

## 미검증 / 실패·보류 사유

- 🔴 **`#385` 실증의 인과가 아직 안 섰다.** 스킬 배달 경로를 고쳤지만(`3b7c536`),
  **그것이 층1 차단의 원인이었는지는 재시도로만 확인된다** (사용자 정정 2026-09-08:
  *"스킬이 안 보였다는 사실과, 그것이 그 실패를 일으켰다는 판정은 다르다"*).
- **재배달·check 미실행** — 종전 기록의 ①②③(재배달 → `check` → `ax-projects` 재기동)은
  이 세션에서 **안 돌렸다.** ③은 승인 사항이다(`docs/11` §11.5).
- **`#387` 계측 결함 미착수** — `wcommit.py:267` 이 `llm()` 의 `out` 을 rc≠0 일 때만 쓰고
  버린다. 정본 ⑸ 경로는 **성공해도** usage 를 회수 안 한다(실측: 스풀 `f4db3ad4.json`
  `usage:{}` · `tail:""` — codex 가 85초 돌았는데 0). 레인 모드도 같다.
- **`#384` ④(Codex → Claude) · ⑤(중단 복구) 미착수.**
- **죽은 `AX_LANES` 주석** (`lanes.py:75`) 정리 안 됨 — 읽는 코드 0건.
- **실패한 것 없음.** 이 세션에서 rc≠0·차단·예외로 멈춘 자리는 없다.

## 실행 중인 서비스 작업·프로세스 / 로그 위치

    상시    systemd 6종 (위 목록) — 세션과 무관하게 돈다
    파견    `ax-dispatch.path` 가 골조 push 를 감시한다. 보류 없음
    로그    파견 로그가 정본. `~/.cache/ax-dispatch/` · 큐 로그는 `~/ax-state`
    서브에이전트  없음 — 이 세션은 하나도 안 띄웠다

## 바로 다음 작업

**축은 `#385` 로 정해졌다. Codex 가 지휘한다.** 멈춘 자리와 다음 갈래:

    지금 막힌 곳   `.venv/bin/python -m master.client plan NS` → AX_PROJECTS_ROOT 미설정
                   문서화된 형태는 `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client ...`
                   (ax-cluster/CLAUDE.md:321). Claude 세션 권고: **그대로 치는 것은 「수정」이
                   아니다**(§1.1 이 막는 것은 실패를 코드·설정 변경으로 덮는 것이다) → 진행 가능.
                   [주의] 결정은 사용자 몫이다 — 이 줄은 권고이지 승인이 아니다

    그 뒤          재배달 → `check` rc=0 → `ax-projects` 재기동(**승인 사항**) →
                   조각 `f4db3ad4` 상태 변경 결정(위 ⓐ/ⓑ) → 재시도로 인과 확인

    별건(승인 필요)  `AGENTS.md` 에 저장소 명령 블록 보강 (위 §AX_PROJECTS_ROOT)
                   `~/.codex/config.toml` MCP 연결 (위 §MCP 미배선)
    미착수          `#387` 계측 결함 · 워커 지휘자 기본값 결정(지금 저장값 `codex`)

## 관련 문서 링크

- `docs/orchestrator-rules.md` (공용 규칙) · `docs/15-orchestrator-handoff.md` (계획 본체)
- `docs/16-worker-orchestrator-mode.md` (`#385` 변경안 · §16.4 실증 · §16.5 계측 결함)
- `reports/54`(Claude 쪽 조사) · `55`(Codex 쪽 실측) · `56`(codex 를 워커 지휘자로)
