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
