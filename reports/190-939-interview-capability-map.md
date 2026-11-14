# 190 — #939 착수 전 인터뷰·기능 분해 표 이식과 `plan_set` 스펙 경고

2026-11-14 · Claude · 이 세션이 직접 구현(사용자 선택).

## 발단과 결정

- 사용자: 「939번도 진행하려고 하는데 … PStack처럼 상위 부모 일감 만들고, 이번에는 초반 플랜 작성 부분을 이식하는 일감을 진행하자」.
- 일감 정리:
  - 부모 아카이브 #956(아이디어)을 만들었다. 출처는 `addyosmani/agent-skills` `301b02b`이고 분석 보고서 `reports/research/2026-11-13-939-agent-skills-interview-analysis.md` 를 옮겨 적었다.
  - 자식 아이디어 셋을 만들었다 — #957 doubt-driven · #958 Floor Guard · #959 context-engineering.
  - #939 는 #956 의 자식으로 옮기고 마일스톤 8 로 이동했다. 제목은 이식 범위로 바꿨다.
- #939 본문은 #911 스펙 템플릿 형식으로 다시 썼다. 첫 실사용이고 `plan_start` 의 `spec_missing` 은 `[]` 였다.
- 사용자 결정(2026-11-14):
  - 범위 = 인터뷰 + Capability Map(3단 경계 포함).
  - 코드 = `plan_set` 응답에 `spec_missing` 경고만 싣는다(거절 없음).
  - 수행 = 이 세션이 직접. 플랜 사유에 #911 선택을 재사용한다고 먼저 적었다가 다른 일감이라 다시 물었다.
  - 확신도 표기 = 「높음·중간·낮음」(본문의 열린 결정).

## 변경

- `master/plan_tools.py` — `set_plan` 응답에 `spec_missing`(= `plan_start.spec_missing(new_body)`)을 더했다. 등록 흐름·거절 규칙은 그대로다.
- `master/test_plan_tools.py` — `test_set_reports_spec_missing` 를 추가했다.
  - 스펙이 빈 본문도 등록되고 경고 6개가 실린다.
  - 6항목 본문은 빈 목록이다.
  - 갱신 때 플랜 영역 안은 세지 않는다.
- `docs/issue-spec.md`
  - §4 착수 전 인터뷰: 선조회 → 가설·확신도 → 질문 하나 + 추정 답 → 6항목 요약(비범위 필수) → 명시 승인 → 멈춤. 무인 경로는 묻지 않는다. `interview-me` 6줄과 우리 6항목의 대응표를 넣었다.
  - §5 기능 분해 표(10줄 이내 · 기능·책임·선행·검증)와 3단 경계를 넣었다.
- `ax-plan` 스킬
  - §2 에 인터뷰 6단계 요약을 넣었다.
  - §3 에 기능 분해 표 단계와 `plan_set` 응답 `spec_missing` 처리를 넣었다.
- `distribute` 스킬 — 「요청을 받으면」 3 의 분해안을 기능 분해 표와 3단 경계로 적게 했다.

## 안 한 것

- 판정·등록 거절.
- `.33` 요청자 스킬.
- `ax-projects`·`ax-client` MCP 도구 설명문 갱신 — 대상 목록 밖이다. 응답 필드는 그대로 실린다.
- 인터뷰를 코드로 강제하는 것. 대화라서 코드가 볼 수 있는 것은 결과(본문 스펙)뿐이고, 그 결과는 `spec_missing` 이 본다.

## 검사

- `test_plan_tools` 48/48 · `test_plan_start` 44/44 · `test_skill_conventions` 50/50 rc0.
- 전수 `master/test_*.py` 225파일 11794/11794, 실패 0(`AX_PROJECTS_ROOT` 지정) · 공식 통합 `Ran 199 tests` OK.
- 드라이런(worktree 코드 · 실제 Redmine 읽기 · 가짜 updater 라 쓰기 0):
  - #939 `set_plan` → `spec_missing: []`. 템플릿으로 다시 쓴 본문이다.
  - #908 → `['triage', 'observe', 'scope', 'done']`.
  - 처음 돌린 스크립트는 가짜 updater 인자 이름(`description`·`notes`)을 틀려 `TypeError` 로 멈췄다. 조회 스크립트 쪽 실수라 그것만 고쳤다.
- 운영 경로(재기동 뒤 실제 `plan_set_tool` 응답)는 마감 노트에 덧붙인다.

최종 결과는 Redmine #939 마감 노트를 본다.
