# 154 — #921 일감 마감 뒤 단계를 명령 하나로 · 검사 파일 직접 실행 규약

> 2026-11-08 · Claude · 일감 #921 · 시작 리비전 `5069e17` · 작업 위치 `.ax-issues/921`(`issue/921`)

## 왜

같은 날 세 지휘자가 모두 마감 뒤 단계를 한 번 이상 빠뜨렸다.

| 빠진 것 | 사례 |
|---|---|
| 마감 뒤 배달 | #913·#882·#820(Antigravity) — 워커 `check` rc=1 |
| 배달 **뒤** 인수인계 커밋 | #916 맞물림 — 오늘 4회 |
| 재기동 직전 oneshot 확인 | #918 broker 재기동(Claude) — 리뷰 큐 실행 중 |
| 검사 파일 직접 실행 | #820 `test_scope_check.py` — 「7/7」 보고, 직접 실행 rc=1 |

규칙은 진입 지침(홈·저장소 AGENTS.md)에 이미 있었다(#920 배선 2번 확인). 그래서 문서가 아니라 코드로 강제한다
(#920 배선 4번 · 공용 규칙 §1.9 `5069e17`).

## 사용자 결정 (2026-11-08)

「응 3번 일감 등록하고 진행해」 → ① CLI 명령(issue_finish 는 ax-projects 안의 MCP 라 자기 재기동이 안 되고 배달은
1~2분) ② 인수인계서가 끝 커밋 뒤 없으면 **배달 전에 멈춤** ③ 검사 파일 규약은 새 검사 + 공식 통합 등록.
수행은 이 세션 직접. RAG request_id `1566010784ba41debc3de9ae98990da0`.

## 변경

- **`master/issue_wrapup.py`**(신규) — `python -m master.issue_wrapup <N> [--dry-run]`
  ① 마감 추적 기록(끝 커밋)·잠금 확인 ② 운영 저장소 main·깨끗·origin 일치·끝 커밋 포함 ③ `service_freshness.check()`
  (판정 불가면 멈춤) ④ [중요] 옛 코드·[주의] 의존 변경으로 **판정된 상주만** 재기동 — oneshot(리뷰 큐·파견·색인기)
  대기(상한 900초) 뒤 기존 `service_restart.restart`(기동 시각·상태 검증), 재기동 뒤 재판정 ⑤ 끝 커밋 뒤
  `docs/orchestrator-handoff.md` 커밋이 없으면 **배달 전에 rc 2** ⑥ `master.client update` ⑦ Redmine 노트.
  rc 0/1/2. 재실행하면 ③④는 할 일이 없어 지나간다. 자동으로 고치는 것은 없다.
- **`master/issue_flow.py`** — `finish` 반환에 `next`(그 일감의 마감 뒤 명령).
- **`master/test_test_runnable.py`**(신규) — `master/test_*.py` 의 모듈 수준 `master` import 앞에 `sys.path.insert`
  를 AST 로 강제(표본 4 + 저장소 전수). **`master/test_scope_check.py`** 정정.
- **`tests/integration/checks.json`** — `test_issue_wrapup`·`test_test_runnable`·`test_scope_check` 등록(188 → 191).
- **`master/skills/ax-plan/SKILL.md` §3-1 · `docs/orchestrator-rules.md` §1.9** — 그 명령을 가리킨다.

## 검증

- `test_issue_wrapup` rc0 **29/29**(대역 — 실 systemctl·sudo·배달·Redmine 없음): 깨끗한 경로 · 판정된 것만 재기동 ·
  재기동이 배달보다 먼저 · oneshot 대기·상한 · 인수인계 없음 → rc2·배달 없음 · 재실행 · 멈춤 10갈래 · 다른 일감
  잠금은 통과 · 의존 판정 불가는 재기동 대상 아님 · dry-run.
- 실저장소 dry-run(#918, 읽기만): finish → repo → fresh 3 최신 → 재기동 없음 → 인수인계 `5069e17` 확인 → 배달 생략 rc0.
- `test_test_runnable` 5/5(215+ 파일 위반 0) · `test_scope_check` 직접 실행 `Ran 7 tests` OK · `test_issue_flow`
  174/174 · `test_skill_conventions` 49/49.
- 정적(`pystatic`, 기준 `5069e17`, 6파일): pyflakes·import·mypy 차단 0.
- 공식 통합(정본 명령, worktree): rc0 **`Ran 191 tests in 183.625s`·`OK`(191/191)** — 신규 3건 포함.
- 사용자 「응 결과 나오면 끝까지 진행해」 — §1.9 흐름(커밋·마감·재기동·인수인계·배달).
- 실경로: 이 일감 마감 뒤 `master.issue_wrapup 921` 를 실제로 돌린다 — 결과는 Redmine 마감 노트.

최종 결과는 Redmine 마감 노트.
