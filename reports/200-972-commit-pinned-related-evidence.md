# 200 — #972 관계 근거를 합성 대상 커밋의 선언 파일로

2026-11-16 · Claude · #971 마감 직후 C5 운영 관측 실패에서 나온 버그. 같은 세션.

## 무엇이 실패했나

#971 마감(main `09e4698`) 뒤 새 코드로 돈 `ax-indexer` 회차(22:00:41 · 22:02:11)가 `master/plan_metrics` 를
커서 커밋 `6569345` 고정 트리에서 합성했는데 agy·codex 둘 다 `related_classes: Plan, Task` 로 거부됐다. 커서는 멈추고
회차마다 상용 호출 2회가 소모됐다.

원인: 상용 레인은 커밋 고정 트리에서 돌아 문서가 **그 커밋 기준**으로 쓰이지만(`Plan: master/plan_block.py`,
`source_commit: 6569345`), 사실 게이트 근거 — `declared`·`project_symbols`·#971 T1 `homonym_class_files` — 는 **현재 HEAD**
다. #971 T3·T4 개명이 같은 회차에 그래프를 `09e4698` 로 올리면서 옛 커밋 합성의 근거를 지웠다.
**#971 의 C1 은 동명 상태에서만 쟀고, 「개명 → 밀린 옛 커밋 합성」 상호작용은 재지 않았다** — 순서를 정할 때의 누락이다.

## 사용자 결정

갈래 A(근거를 합성 대상 커밋 기준으로) · 새 버그 일감 · 「이 세션 직접」. 인터뷰 5단계·스펙·플랜(T1·T2, C1~C5)을 한 번에
보이고 「예, 그대로 진행」으로 확정했다.

## 바꾼 것 (`issue/972`)

- `32821cf` T1 — `synth.commit_class_files(paths, commit, doc)`: 문서 `related_classes` 의 `이름: 경로` 마다 그 경로를
  `git show <commit>:<경로>`(커밋이 없으면 현재 작업 트리)로 읽어 기존 파서(.py pyparse · C++ gparse)로 최상위 클래스를 센다 →
  `{이름: {경로}}`. `_merge_class_files` 로 #971 그래프 동명 맵과 합쳐 `verify(class_files=…)` 에 넘긴다.
  인정 판정은 #971 의 `verify.declared_by_file` 그대로(그 이름의 **모든 항목**이 실제 선언 파일). 경로 없음·`?`·`..`·절대 경로·
  커밋에 없는 파일·파싱 실패는 근거에서 빠질 뿐 통과가 아니다.
- 비범위로 남긴 것: 프롬프트 본문(`bodies`)도 현재 작업 트리에서 읽는다 — 상용 레인 작업 트리(커밋)와 기준이 다르다.
  이번에는 관계 근거만 맞췄다.

## 검증

- `test_context_synth` 280/280 — #972 블록 12건: 옛 커밋 `Plan`/HEAD 개명 픽스처에서 HEAD 기준 거부 유지 · 커밋 기준 통과 ·
  반례 6종(없는 클래스·틀린 파일·커밋에 없는 파일·경로 미상·저장소 밖·한 항목 틀림) 거부 · HEAD 새 이름 통과 ·
  **커밋 고정 합성 진입점**(`synthesize_group(commit=…)`) 저장.
- 운영 산출물 재검증(LLM 0, scratchpad `repro972.py`): `a7c24bf4…`(plan_metrics) HEAD `[Plan, Task]` 거부 → 커밋 `6569345`
  통과 · `eea55bdc…`(test_plan_block) HEAD `[Check, Plan, Task]` → 커밋 통과.
- 전수 `master.sweep` 2회: 1회차 rc1 — `test_rounds.py` 「작업장 요청자 — 등재 본문 ③ 이 그 호스트다」 한 건. 단독 실행은
  운영 main 1회·worktree 2회 모두 통과, 2회차 전수 rc0(236파일 12278/12278 · unittest 542/542). #972 변경(합성 검증)과
  무관한 **병렬 실행 간헐 실패**로 보고 코드는 건드리지 않았다 — 재현 조건 조사는 별건 후보.
- 공식 통합 `Ran 210 tests` OK.

## 남은 것

- C4(운영 관측)는 마감 뒤에만: `ax-indexer` 회차에서 `master/plan_metrics`·`master/test_plan_block` 저장·`source_commit`·
  커서 `6569345` 이후 전진. 이 관측이 #971 C5 의 근거도 된다.

최종 결과는 Redmine #972 마감 노트.
