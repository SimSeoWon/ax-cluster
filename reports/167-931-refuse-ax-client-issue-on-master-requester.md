# 167 — #931 requester: master 프로젝트의 ax-client 일감 호출을 서버가 거절한다

> 2026-11-11 · Claude 지휘 · 시작 `ebd691f79419` · 브랜치 `issue/931`

## 무슨 일이 있었나

공용 규칙 §1.10 은 운영 일감 시작을 `ax-projects:issue_start_tool` 로만 하도록 정했지만 문서 규칙이었다.
AXCluster 일감도 `ax-client:issue_start`·`issue_finish`(8101 대행)로 시작·마감할 수 있었고, 실제로 `#702`·`#929` 가
그렇게 진행됐다.

- 작성 계열(`authors`)은 `ax-projects:issue_start_tool` 의 MCP clientInfo 에서만 기록된다. `ax-client` 경로로
  들어온 두 일감은 `authors` 가 비었고, 리뷰 큐가 agy 를 골라 Antigravity 작성분을 같은 계열이 리뷰했다(`#702` R312·R313).
- 같은 경로에서 `#929` 는 실재하지 않는 끝 해시가 등록됐다(`#933` 이 그 자리를 따로 막았다).

## 결정 (사용자, 2026-11-11)

| 갈림길 | 결정 |
|---|---|
| 거절 범위 | 시작·마감·보류·취소 네 호출 모두 |
| `ax-client:plan_*` | 그대로 둔다 — 작성 계열·마감 추적을 만들지 않는다 |
| 프로젝트 설정(`requester`)을 못 읽으면 | 거절한다 |

본문 「착수 때 정할 것」 2번(이미 잡힌 잠금을 이 경로로 마감)은 네 호출을 모두 거절하므로 따로 처리하지 않는다 —
마스터 잠금은 `ax-projects` 도구로만 푼다.

## 바뀐 것

| 자리 | 내용 |
|---|---|
| `master/issue_infra.py` | `requester_is_master(project)`(설정 읽기) · `requester_gate`(거절·로그) 추가. `_remote_setup` 이 프로젝트 확인 직후, 잠금 위치를 풀기 전에 판정한다. `infra_start`·`infra_finish`·`infra_pause`·`infra_cancel` 에 `requester_check=` 인자(시험 주입) |
| 거절 응답 | `ok: false` · `step: requester` · `requester: master` · `why` 에 `ax-projects:issue_<op>_tool` 이름. `check_only` 호출도 같다 |
| 판정 실패 | 설정을 못 읽으면 `step: requester` 로 거절(잠금·추적·Redmine 무변경) |
| 대역 주입 실행 | `requester_check=` 를 안 주면 판정을 건너뛴다(운영 설정을 읽지 않는다) — `git=` 와 같은 규약 |
| 로그 | `<트윈>/issue_flow.jsonl` 에 `requester` 단계(통과·거절 사유), 8101 은 기존 `[issue]` 한 줄에 `step=requester` |
| 문서 | 공용 규칙 §1.10 · `ax-plan` 3-1 · 요청자 `ax-issue` 스킬 §8 표 · `issue_start` 도구 설명 · `server.py` 주석 · `issue_infra` 머리말 |

호출부 대조: `infra_*` 넷의 운영 호출부는 `master/task_queue/server.py` 의 엔드포인트 4곳뿐이고, 마스터 정규 경로
(`master/issue_flow.py`)는 `_remote_setup` 을 쓰지 않는다. 그래서 판정을 공통 준비 한 곳에 두었다.

## 검사

- `test_issue_infra` 118/118(신규 25) — 네 호출과 `check_only` 거절·도구 이름 안내, 거절 뒤 노트 0·잠금 파일 없음·추적 없음,
  활성 잠금이 있어도 잠금 파일 바이트 동일, 판정 실패 거절, 실제 `config.yaml` 로 참·거짓·예외, 판정이 잠금 해석보다 앞.
- `test_tagging` 242/242(신규 10) — 실물 앱에서 트윈 설정을 `requester: master` 로 바꾼 뒤 여섯 호출이 200 + `ok:false`,
  잠금·추적·노트 무변경, `plan/start` 통과, 설정 복원 뒤 다시 통과.
- 변이(판정 제거): `test_issue_infra` 100/118 · `test_tagging` 234/242 로 FAIL.
- `test_issue_flow` 184/184 · `test_client_mcp` 356/356.

## 한계

- 깨진 `config.yaml` 은 8101 에서 이 판정까지 오지 않는다. 마운트 관문(`_mount_gate` → `paths.resolve`)이 먼저 읽다가
  예외를 낸다(기존 동작, 이번 범위 밖). 판정 실패의 거절은 단위 검사로만 확인했다.
- 게임 프로젝트 요청자 경로에는 `ax-client` 로 들어오는 계열 기록이 여전히 없다(§1.10 의 「일감 밖 손 커밋」과 같은 취급).
- `authors` 가 빈 추적의 처리, 이미 끝난 `#702`·`#929` 의 교차 재리뷰는 범위 밖이다(`#829` 제안).
- 손으로 worktree·merge·push 를 하는 것 자체는 막지 않는다. 막는 것은 그 뒤의 기록(잠금·마감 추적) 경로다.

전수·공식 통합 검사와 재기동 뒤 실제 서비스 확인의 최종 결과는 Redmine `#931` 마감 노트에 있다.
