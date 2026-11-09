# 165 — #930 테스트가 실제 ~/.claude.json 의 ax-client 를 덮어쓰던 결함

> 2026-11-10 · Claude 지휘 · 시작 `76941c589f5e` · 브랜치 `issue/930`

## 무슨 일이 있었나

`#929`(`eb78e03`)에서 추가한 `test_claude_skills_sync_and_check` 가 `ml._run` 을 대역으로 바꾸지 않고
`ml.apply()` 를 호출했다. `apply` 는 진짜 `claude mcp remove`·`add-json` 을 실행하고, CLI 는 `Paths` 를
모르므로 임시 경로로 불러도 **실제 `~/.claude.json`** 을 고친다. 그 결과 `ax-client` 가 삭제된
`/tmp/.../dummy_script.py` 를 가리켜 Claude 세션에서 `CONNECTION_CLOSED` 로 실패했고, Redmine 도구까지 막혔다.

- 근거: `~/.claude/backups` 는 11-10 00:41 정상, 00:48·00:54 는 서로 다른 임시 경로로 오염.
- 원인은 코드와 백업으로 판단했다. 대역 없는 옛 테스트를 다시 돌려 재현하지는 않았다.
- `master-local --check` 는 `FAIL 12/13` 이었으나 리포트 164·인수인계서에 없었다.
- 귀속: 해당 커밋은 Antigravity 지휘 작업이다. 누가 어느 시각에 실행했는지는 실행 로그로 확인하지 않았다.

## 구조적 빈틈과 수정

| 빈틈 | 수정 |
|---|---|
| 대역을 빠뜨리면 `apply` 가 실제 설정을 고친다 | `_claude_cli_writes`: `claude_json` 이 CLI 가 실제로 쓰는 파일이 아니면 호출을 거절하고 실패로 보고 (`master/client/master_local.py`) |
| 문제 테스트의 대역 누락 | 대역 추가, CLI 호출 0건 검사 (`master/test_client_master_local.py`) |
| 임시 경로만 보는 검사는 실제 오염을 못 본다 | 테스트 전후로 실제 Claude·Codex·Antigravity 의 `ax-client` 설정을 비교. 달라진 CLI 이름만 출력 |

운영 경로에서는 CLI 를 그대로 부르는지도 검사한다 — 방어가 설치를 막지 않는다.

## 범위에서 뺀 것 (사용자 합의)

통합 러너의 `HOME` 격리. 홈을 쓰는 코드가 `master` 아래 60개 파일·테스트 14개라 193종 전체에 영향이 간다.
다른 모듈의 테스트가 실제 홈을 건드리는 경우는 이번 수정으로 막지 못한다.

## 복구

`master-local --apply` 로 복구했다(`FAIL 12/13` → `OK 13/13`). 오염 상태는
`~/.claude.json.bak-master-local-20261110-010011` 에 있다. 실행 중인 세션은 복구만으로 연결되지 않아 `/mcp` 재연결이 필요했다.

## 검증

- `test_client_master_local`: 121/121 통과, rc=0
- 변이 ① 방어 제거(임시 `HOME`): 119/121 FAIL — CLI 호출을 검출
- 변이 ② 설정 오염 모사(임시 `HOME`): 120/121 FAIL — `달라진 설정: ['claude']`
- 공식 통합: `Ran 193 tests in 195.602s · OK`
- 실제 설정 해시: 단위·변이·통합 실행 전후 모두 `f134352d6e107dca` 로 동일
- `master-local --check`: `OK 13/13`

최종 결과는 Redmine 마감 노트.
