# 199 — #971 동명 클래스: 합성 검증 폴백 · 리뷰 고지 · 클래스명 7개 변경

2026-11-16 · Claude · 인수인계 대조·`0504027` 배달 뒤 같은 세션에서 수행.

## 사용자 지시와 범위

- 「배달하고 971 진행하자」 — 배달(`master.client update` rc0, 3/3 OK) 뒤 #971 을 「진행」(§1.9).
- 스펙(`ax:spec`)은 앞 세션에서 확정돼 있었다: 1단계 예방(리뷰 고지)·폴백(선언 파일로 연결)을 **동명 상태에서**
  검증한 뒤, 2단계로 클래스 7개만 개명(파일명 유지). 자동 개명·자동 일감·새 차단·이름별 예외는 범위 밖.
- 플랜: 기능 분해 A(폴백)·B(고지)·C(개명) → T1~T5 · C1~C6 · 자율성 0.5. 수행 방식은 「이 세션 직접」(사용자 선택).

## 원인 — 재현

그래프는 파이썬 파일끼리 겹치는 클래스 이름을 `모듈.이름` 으로만 담는다(`graph/pyparse.disambiguate`).
`verify.verify` 의 `related_classes` 검사는 짧은 이름을 `declared`·`known`(`project_symbols`)·그룹 소스 식별자와
**정확히** 대조하고, 문서가 함께 적은 선언 파일은 버렸다. 그래서 올바른 `Plan: master/plan_block.py` 가 근거 없음이 됐다.

재현(읽기 전용, LLM 0 — scratchpad `repro971.py`, 운영 저장 산출물을 현재 verify 로 재검증):

| 산출물 | 그룹 | 수정 전 | 수정 후 |
|---|---|---|---|
| `f2ef2241…` | master/plan_metrics | ok False · `[Plan, Task]` | ok True · `[]` |
| `eea55bdc…` | master/test_plan_block | ok False · `[Plan]` | ok True · `[]` |

## 바꾼 것 (`issue/971`)

- `89dad6e` T1 — `synth.homonym_class_files(paths)`: 그래프의 전체 이름 중 **모듈 접두가 그 행 파일의 모듈명과 같은 것**만
  `{짧은 이름: {선언 파일}}` 로 모은다. `verify.related_entries`(이름·파일 쌍)와 `declared_by_file`: 근거 없는 짧은 이름은
  **그 이름의 모든 항목**이 실제 선언 파일을 적었을 때만 인정한다. 경로 없음·`?`·틀린 파일이 하나라도 있으면 그대로 거부.
  그래프를 못 읽으면 빈 사전 = 종전 판정.
- `2cad709` T2 — `review_runner.homonym_notice`: 변경 파일이 선언한 클래스 중 다른 파일에도 있는 이름을, 각 선언 파일과
  「낮음」 행 이름 개선 검토 권고와 함께 **퇴고(상용) 프롬프트 근거 칸**에 싣는다(커밋·범위 리뷰 둘 다). 로컬 초고에는
  싣지 않는다. 동명이 없거나 그래프가 없으면 빈 문자열이라 프롬프트는 종전과 바이트 동일.
- `82a7287` T3 — `plan_block`: Plan→IssuePlan · Task→IssuePlanTask · Check→IssuePlanCheck.
- `3d009bf` T4 — onboard Plan→OnboardingPlan · decompose Plan→DecompositionPlan · workmodel Task→WorkTask ·
  md Check→ContextDocCheck.
- `9ae5e0b`·`7df43f3` — 인수인계서 축소(아래 「도중에 나온 것」).

개명은 scratchpad `rename_tok.py` 로 **토큰 단위**(코드 식별자만, 문자열·주석 불변)로 했다: 선언 모듈은 전체 NAME,
다른 파일은 `<별칭>.이름` 꼴만. 별칭은 실측으로 모았다(plan_block 은 `PB` 하나·21곳, decompose `D`/`decompose`,
workmodel `WM`). 직접 import 는 `plan_state` 의 `Plan` 하나뿐이었다. `getattr` 동적 참조 0.

## 검증

- T1: `test_context_synth` 269/269 — #971 블록: 재현 2 · 통과 3 · 반례 6(없는 클래스·틀린 선언 파일·다른 전체 이름·
  경로 미상·경로 없음·한 항목 틀림) · 전체 이름 관계 유지 · **실제 합성 진입점**(`synthesize_group`)의 저장/거부.
- T2: `test_review_runner` 184/184 · `test_review_range` 96/96 — 러너 `run_once` 경유 실제 퇴고 프롬프트에 고지 절,
  DIFF 앞, 초고 미포함, 로그, 리뷰 done. 운영 그래프 렌더(LLM 0): plan_block 변경 시 Check·Plan·Task 3건.
- T3·T4: Redmine #971·#963·#970 본문 parse→replace **바이트 왕복 True**. 저장소 최상위 클래스에 Plan/Task/Check 0건,
  새 이름 각 1파일(AST 실측). 관련 단위 검사 전부 rc0.
- 전수 `master.sweep`: 236파일 · 12267/12267 · unittest 542/542 · 실패 0. 공식 통합 `Ran 210 tests` OK.

## 도중에 나온 것

- 전수 1회차가 rc1 — `test_handoff_size` 「170줄 > 상한 150」. #971 변경과 무관하게 운영 main(`0504027`)에서도 같은 실패였다.
  보고 뒤 사용자 「A로 진행해」로 인수인계서를 #971 범위에서 덮어써 줄였다. 이어 사용자 지적(「또 누적되는 형태인거야?」) —
  줄인 판에 남긴 「최근 마감」 표도 행 단위 누적이라 「응 표 빼고 진행해」로 뺐다. 줄 수 가드는 **표 형태 누적을 못 잡는다**
  (줄 수와 「이전 체크포인트」 표지만 본다) — 가드 강화는 범위 밖, 필요하면 별도 일감.
- 재현·탐색 스크립트 두 번의 자기 실수(잘못된 import 한 줄, Python 그래프 범위 미지정)는 scratchpad 스크립트만 고쳤다.

## 남은 것

- C5(운영 관측)는 마감 뒤에만 가능하다: `ax-indexer` 회차에서 두 그룹 합성 문서·`source_commit`·커서 `6569345` 이후 전진,
  그래프의 새 이름 반영. 개명 뒤에는 동명이 사라지므로 T2 고지가 이 이름들에 대해 더 나오지 않는 것도 함께 본다.

최종 결과는 Redmine #971 마감 노트.
