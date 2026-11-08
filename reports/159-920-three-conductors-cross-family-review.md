# 159 — #920 지휘자 셋 정립: 작성 계열 신호 · 교차 계열 리뷰 · Argon 폴백

> 2026-11-08 · Claude (Opus 5.5) · 일감 #920 · 시작 리비전 `b9e534f` · 작업 위치 `.ax-issues/920`(`issue/920`)

## 왜

Antigravity 가 쓴 커밋을 같은 계열인 agy 가 리뷰하고 있었다. 커밋에 작성 도구를 구별할 값이 없어 코드로 가를 수도 없었다.

사용자 결정(2026-11-08, 「920을 마일스톤 7로 옮겨서 진행하자」 뒤 플랜 질문):

- 신호: MCP `clientInfo` 자동 기록. 측정 뒤 추가 결정: Antigravity 에 `ax-projects` 연결 + 운영 경로 직접 호출 거절
- 대체 리뷰어: Codex 단독, 실패 시 폴백 없음
- Argon: `ax-gemini` 폴백 + 규칙. 자동 경로 금지 유지
- 실행: 이 세션 단독. 실제 Antigravity 통합 실증은 새 일감으로 분리

## 측정

| 항목 | 결과 |
|---|---|
| `clientInfo.name` (임시 HOME 탐침) | `claude-code` 2.1.319 · `codex-mcp-client` 0.167.0 · `antigravity-client` v1.0.0 |
| 도구 안에서 읽기 | `ctx.session.client_params.client_info.name`. 세션 모드는 값 있음, `stateless_http` 는 None. 운영은 stateless 를 쓰지 않는다 |
| Antigravity 경로 | MCP 는 `ax-client` 만 연결. 이력에 `issue_flow.start(820·882·913·923)` 직접 호출. 이 경로엔 `clientInfo` 가 없다 |

처음 고른 신호가 실제 경로에 닿지 않아 구현 전에 멈춰 다시 물었다.

## 변경

- **신호**: `issue_start_tool` → `issue_flow.start(client=)` → 잠금 `authors` → 마감 라운드 `authors`. 교대로 재호출하면 쌓인다. 운영 호출에 출처가 없으면 거절한다.
- **리뷰 큐**: `review_runner` 가 작성 계열에 `agy` 가 있으면 `codex_only`, 아니면 `agy_only` 를 고른다. 커밋·범위 공통이다. 마감이 push → 등록 → 잠금 해제 순이라, 등록 전 틈은 활성 잠금의 계열로 덮는다.
- **Argon**: `gemini_report` 의 명시 호출만 한도 응답·쿨다운에서 `gemini-3.8-flash-high` 로 한 번 넘어간다. 첫 시도 기록은 보존한다. `agy_models.execute` 의 Argon 폴백 거절(#830)은 그대로라 자동 경로는 바뀌지 않았다.
- **설정**: `master-local` 이 Antigravity `mcp_config.json` 에 `ax-projects` 를 넣고 토큰 때문에 0600 으로 둔다. `--check` 에 행을 더했다.
- **문서**: 공용 규칙 §1.10, 자동 로드 문서의 「지휘자 둘」→「셋」, `GEMINI` 진입 지침, `ax-plan`, `ax-gemini`.
- `client_mcp.py` 는 바꾸지 않았다(플랜 대상에는 있었다). `ax-client` 의 `issue_start` 는 요청자 경로라 worktree 를 만들지 않는다.

## 검증

- 단위: `test_issue_flow` 184/184 · `test_issue_lock` 56/56 · `test_issue_track` 95/95 · `test_issue_infra` 69/69 · `test_review_runner` 123/123 · `test_gemini_report` 117/117 · `test_agy_models` 20건 · `test_client_master_local` 86/86 · `test_mcp_servers` 55/55.
- 실물: 임시 트윈에서 실제 커밋 `8bcaa6d` 를 `run_once` 기본 경로로 Codex 1회 호출. 큐 done · `format_ok` True · 검증 모델 Codex · 입력 22,497/출력 925 토큰 · 저장소 깨끗.
- 공식 통합 수치는 Redmine 태스크 노트에 남긴다.

## 진행 중 고친 것

- 제가 추가한 가짜 agy 의 이스케이프 오류, 그리고 문자열로 소스를 보던 ⑰ 검사(`agy_only(...)` 문장). 실패를 보고한 뒤 사용자 승인으로 고쳤다. ⑰ 은 `_ask` 가 두 리뷰어에 `log` 를 넘기는 동작 검사로 바꿨다.
- `master-local` 테스트가 대역 복구 뒤 실제 CLI 를 부를 뻔한 것을 실행 전에 고쳤다. 실제 설정 3개 해시 불변을 확인했다.

## 한계

- Codex 리뷰 표본은 1건이고 지적이 0건이라 **지적 품질은 측정되지 않았다**.
- 일감 밖 손 커밋, 모르는 클라이언트, `ax-client` 요청자 경로는 계열을 몰라 agy 가 본다.
- 교대한 세션이 `issue_start_tool` 을 다시 부르지 않으면 계열이 더해지지 않는다. 시작 세션의 계열만 남는다.
- 일감 잠금이 활성인 동안 들어온 손 커밋은 그 일감의 계열로 판정한다.
- Argon 내부 서브에이전트 호출은 코드가 강제하지 못한다. 잔여 한도를 미리 읽지도 못한다.
- 실제 Antigravity 지휘 통합 실증은 후속 일감으로 분리했다.

최종 결과는 Redmine 마감 노트.
