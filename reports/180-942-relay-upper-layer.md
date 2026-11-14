# 180 — #942 세 CLI 대화 중계 상위 레이어 (relay)

2026-11-14 · 지휘 Claude · 직접 구현(작성 계열 `['claude']`).

## 사용자 결정 (대화로 확정, 2026-11-14)

- 본문 원안의 「터미널 창 3개 기동·유지」「agy 자동 라우팅·해석」「agy 의 Handoff Brief 생성」을 뺐다.
  사용자: 「cli 환경에 상위 레이어로 이야기가 좁혀지면서 agy 자동 라우팅 필요없어졌어」.
- 흐름: 일감을 고른다 → LLM 을 고른다 → 그 LLM 과의 대화를 상위 레이어가 중계한다. 작업 중간에 에이전트를 바꿀 수 있다.
- 작업 세션 = Redmine 일감 하나. 세션 로그 하나가 미러링 대상이자 에이전트 간 공유 메모리다.
  사용자: 「이 작업 세션에 미러링 된걸 다른 에이전트가 읽으면 되지않을까 했어」.
- 마무리 = 일감 「완료」 + 작업 보고서 저장. 그때 로그를 보관하고 세 에이전트 세션을 비운다.
- 1차는 `.57` AX 일감. `.33` 언리얼 작업은 그쪽 일감 정리 뒤 같은 흐름으로 올린다.
- 도구 권한 「전부 자동 허용」, 코드 위치 `master/` 아래(「일단 동작 확인이 우선으로 하고 정립되면 이동하자」).
- 오동작할 수 있는 곳에는 로그를 심어 파일로 남긴다(작업 중 지시).
- 웹 UI 비주얼라이저·토큰량 표시·로그인 점검·`#941` 디스코드 연동은 추후.

## 시작 경과

- `issue_start_tool` 1차 거절: `step="base"`, 운영 저장소에 미추적 `reports/research/2026-11-14-730-claude-code-mods.md` 1건.
  사용자 「커밋해서 넣고 진행해」 → 문서 커밋 `1aed470` push 뒤 재호출 성공.
- `repo="/home/sim/ax-cluster/.ax-issues/942"`, `branch="issue/942"`, `start_rev="1aed4703c974"`, `lock="acquired"`.

## T1 — 세 CLI 비대화 실행 실측

작업 위치는 worktree(`.ax-issues/942`). 에이전트마다 2회 실행했다: ① 새 세션에 암호어를 기억시킨다 ② 같은 세션을 이어
암호어를 되묻고, 셸 명령 `echo relay-ok` 실행과 MCP 서버 이름을 요청한다. 코드 변경 없음(실측 스크립트는 저장소 밖).

| | claude 2.1.325 | codex-cli 0.169.0 | agy 1.5.8 |
|---|---|---|---|
| 비대화 실행 | `claude -p --output-format stream-json --verbose` | `codex exec --json` | `agy --output-format stream-json -p=<입력>` |
| 전부 자동 허용 | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--dangerously-skip-permissions` |
| 새 세션 ID | 호출자가 정한다 `--session-id <uuid>` | 첫 이벤트 `thread.started.thread_id` | 첫 이벤트 `init.conversation_id` |
| 이어가기 | `--resume <uuid>` | `codex exec resume … <id> <입력>` | `--conversation <id>` |
| 암호어 기억 | 맞음 | 맞음 | 맞음 |
| 셸 실행 | 됨 (`tool_use` Bash → `tool_result`) | 됨 (`command_execution`, `exit_code` 0) | 됨 (`step_type=tool`, `run_command`) |
| MCP | `ax-projects`·`ax-client` connected | `ax_client`·`ax_projects` | `ax-client`·`ax-projects` |
| 소요(1회/2회) | 6.7초 / 9.7초 | 5.9초 / 8.4초 | 11.6초 / 12.8초 |

이벤트 형식(한 줄 = JSON 하나):

- **claude**: `type` = `system`(`subtype=init` — `session_id`·`permissionMode`·`mcp_servers`) · `assistant`(`message.content[]` 의
  `text`·`tool_use`) · `user`(`tool_result`) · `rate_limit_event` · `result`(`is_error`·`result`·`usage`·`num_turns`).
- **codex**: `thread.started` · `turn.started` · `item.started`/`item.completed`(`item.type` = `agent_message`·`command_execution`) ·
  `turn.completed`(`usage`).
- **agy**: `event` = `init` · `step_update`(`step_type` = `user_input`·`system_message`·`agent_response`(`text_delta` 조각)·`tool`
  (`tool_name`·`tool_info`), `state` = `ACTIVE`·`DONE`) · `result`(`status`·`response`·`usage`).

실측에서 걸린 것:

- **agy 의 `-p` 는 바로 뒤 인자를 입력으로 먹는다.** `agy -p --output-format …` 은 rc 2 로 거절됐다(오류 원문이 `-p='…'`
  형태를 안내). `-p=<입력>` 으로 붙여서 통과했다. 호출부는 이 형태로 고정한다.
- **codex 는 표준 입력이 열려 있으면 추가 입력을 기다린다**(`Reading additional input from stdin...`). 호출부는 표준 입력을 닫는다.
- agy 실측 모델은 `gemini-3.8-flash-medium` 을 지정했다(내 측정에 Argon 을 쓰지 않는 기존 결정).

한계:

- 연속 2회·짧은 입력만 쟀다. 긴 작업·한도 소진·중단 뒤 이어가기는 재지 않았다.
- 비대화 세션에서 `issue_start_tool` 을 불렀을 때 작성 계열 기록이 맞게 남는지는 재지 않았다(잠금을 바꾸는 호출이라 실증 T6 에서 본다).
- 이벤트 종류는 이번 실행에 나온 것만 적었다. 모르는 종류는 버리지 않고 원문 그대로 로그에 남기는 것으로 구현한다.

## T2~T5 — 구현 (`master/relay/`)

| 파일 | 하는 일 |
|---|---|
| `store.py` | 일감 번호별 세션 디렉터리 — `log.jsonl`(순번 붙은 추가 전용 기록) · `state.json`(에이전트별 세션 ID·본 순번·횟수·현재 에이전트) · `debug.log`. 보관은 디렉터리째 옮기기 |
| `agents.py` | 세 CLI 비대화 실행, 이벤트 줄을 공통 형식으로 변환, 세션 ID 취득·이어가기, Ctrl-C 시 프로세스 그룹 종료 |
| `boundary.py` | 작업 경계 — `candidates`·`may_open`·`closable`. 일감을 닫지 않고 읽기만 한다 |
| `console.py` · `__main__.py` | `/issue`·`/agent`·`/status`·`/reset`·`/close`·`/quit`, 그 밖의 입력은 지금 에이전트에게 전달 |

정한 것과 이유:

- **저장 위치는 `~/ax-state/relay`**(`AX_RELAY_ROOT` 로 변경). 트윈 디렉터리는 미커밋이 쌓이는 문제(`#326`)가 있어 피했다.
- **전달문에는 사실만 싣는다.** 「작업 세션은 일감 #N 이다 · 기록 파일은 어디다 · 몇 번부터가 이 에이전트를 거치지 않은 대화다」.
  무엇을 하라고는 쓰지 않는다(자동 경로의 명령형은 주입으로 거부된다 — 리포트 60). 세션 시작·교체 표시만 있고 대화 기록이
  없으면 기록 안내를 붙이지 않는다.
- **본 순번은 성공했을 때만 올린다.** 실패한 차례의 기록은 다음 전달문에서 다시 「안 본 대화」로 안내된다. 세션 ID 는 실패해도 남긴다.
- **실패는 다시 시도하지 않는다.** 화면·세션 기록(`kind=error`)·디버그 로그에 남기고 다음 입력을 기다린다.
- **마무리는 판정만 한다.** 일감 「완료」 + `reports/*-<N>-*.md` 존재 + 잠금 해제일 때만 보관한다. 마감은 `issue_finish` 몫이다.
- **다른 일감이 작업 중이면 세션을 열지 않는다**(일감 잠금 활성 기준). 보류된 일감의 세션은 남아 있다가 다시 열면 이어 간다.

로그(사용자 지시 — 오동작할 수 있는 곳마다 파일로):

- `sessions/<N>/debug.log`: 세션 생성·이어감, 에이전트 교체, 세션 ID 변경, 전달(입력 길이·본 순번·안 본 기록 수), 실행 명령
  (입력 본문은 길이만), 종료 코드·소요·이벤트 수·해석 실패 수·usage, 오류 출력 원문(끝 4,000자), 모르는 이벤트, 해석 못 한 줄,
  변환 예외, 경계 판정과 거절 사유, 보관.
- `sessions/<N>/raw-<에이전트>.jsonl`: CLI 가 낸 줄 원문 전부.
- `relay.log`: 세션이 없을 때의 기록(기동, 열기 거절, 보관 위치, 콘솔 예외).

검사: `master/test_relay.py` **113/113 rc0** — 임시 디렉터리와 가짜 실행 파일만 쓴다. 저장소(순번·동시 쓰기·깨진 파일·보관),
호출부(세 계열 이벤트 변환·이어가기 인자·실패·큰 결과), 경계(열기·마무리 판정), 콘솔(선택→대화→교체→이어받기→마무리 한 바퀴).
`tests/integration/checks.json` 에 등록. 정적 검사 pyflakes·imports·mypy 차단 0(노트 26).
경계 판정은 실제 Redmine·일감 잠금으로도 읽어 봤다: 열린 일감 42건·활성 942, `may_open(942)` 허용, `may_open(738)` 거절,
`closable(710)` 가능, `closable(942)` 거절.

## T6 — 실경로 실증

실제 세 CLI, 일감 `#942`, 작업 디렉터리는 worktree, 저장 위치는 저장소 밖 임시 디렉터리(운영 위치에 실증 세션을 남기지 않으려고).
agy 모델은 `gemini-3.8-flash-medium` 지정. 입력은 표준 입력으로 흘렸다(사람이 치는 것과 같은 `input()` 경로).

| 차례 | 에이전트 | 물은 것 | 결과 |
|---|---|---|---|
| 1 | claude (새 세션) | `store.py` 의 세션 로그 파일 이름 상수 + 낱말 `MANGO-42` 기억 | `LOG_NAME = "log.jsonl"` · 4.6초 |
| 2 | codex (교체, 처음 참여) | 앞 대화에서 찾은 상수와 낱말 | 기록 1~9번을 `head` 로 읽고 `LOG_NAME = "log.jsonl"` · `MANGO-42` · 12.0초 |
| 3 | agy (교체, 처음 참여) | 지금까지 누가 무슨 답을 했나 | 기록 파일을 읽고 claude·codex 의 답을 요약 · 17.8초 |
| 4 | claude (복귀, 같은 세션 이어감) | 그 사이 다른 에이전트에게 물은 것과 답 | 기록 9~26번을 읽고 순번까지 짚어 답함 · 8.9초 |

- 세 에이전트 모두 전달문의 **사실 문장만 보고** 기록 파일을 스스로 읽었다(읽으라는 지시 없음).
- claude 는 4차에서 1차와 같은 세션 ID 로 이어 갔고 본 순번 8 → 안 본 대화 기록 13건으로 안내됐다.
- 해석 실패 0, 모르는 이벤트 0. `/close` 는 「일감 상태가 진행 · 잠금 활성」으로 거절됐다(의도한 동작).
- 작업 트리 변경 없음(`git status` 깨끗).

## 한계

- 한 줄 입력만 받는다(여러 줄 붙여넣기는 줄마다 따로 전달된다).
- agy 의 말은 조각으로 오지만 화면에는 다 모인 뒤 한 번에 낸다.
- 긴 작업·한도 소진·중단 뒤 이어가기, 에이전트가 이 레이어 안에서 일감 시작·마감 도구를 부르는 경로는 실증하지 않았다.
  특히 비대화 세션에서 `issue_start_tool` 의 작성 계열 기록이 맞게 남는지는 미확인이다.
- 도구 권한은 전부 자동 허용이다(사용자 선택). 승인 게이트는 에이전트 지침과 마감 도구의 `confirm` 에 달려 있다.
- 기록이 길어지면 처음 참여하는 에이전트가 읽는 비용이 커진다 — 줄이는 장치는 없다(문제가 되면 정한다).
- 저장소 밖 디렉터리에서 실행하려면 `PYTHONPATH` 에 저장소를 넣어야 한다. 실행 래퍼는 만들지 않았다.
- `fcntl` 파일 잠금과 프로세스 그룹 종료는 리눅스 기준이다 — `.33` 으로 옮길 때 바꾼다(이번 범위 밖, 사용자 결정).

최종 결과(마감·재기동·배달)는 Redmine #942 마감 노트가 정본이다.
