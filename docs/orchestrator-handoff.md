# 현재 AX 작업 인수인계

> 2026-11-16 — **#971 진행 중**(Claude 세션, 사용자 「배달하고 971 진행하자」 = §1.9 일감 「진행」). 시작 리비전
> `0504027`, worktree `/home/sim/ax-cluster/.ax-issues/971`(`issue/971`). T1~T4 완료·커밋, T5(전수·통합·리포트) 진행 중.
> 같은 턴에 `0504027` 배달 rc0(`.43`·`.2`·`.33` OK, 출처 HEAD 일치).
> 이 문서는 #971 T5 도중 사용자 승인(「A로 진행해」·「응 표 빼고 진행해」)으로 덮어썼다 — `0504027` 판이 마감
> 절을 쌓아 170줄(상한 150)이었다. 끝난 일감 목록·표를 두지 않는다(다음 세션도 행을 더하지 않는다).

## #971 — 동명 클래스 리뷰 고지·합성 검증 폴백·클래스명 변경

- 정본: Redmine #971 본문 `ax:spec`·`ax:plan`(T1~T5 · C1~C6 · 자율성 0.5), 수행 방식 「이 세션 직접」(사용자 선택).
- 원인(재현 완료): 그래프는 파이썬 동명 클래스를 `모듈.이름` 으로만 담는다(`pyparse.disambiguate`).
  `verify.related_classes` 는 짧은 이름 정확 일치라 `Plan: master/plan_block.py` 가 근거 없음으로 거부 →
  `master/plan_metrics`·`master/test_plan_block` 합성이 커서 `6569345` 에서 멈췄다.
- 커밋(worktree `issue/971`):
  - `89dad6e` T1 — `synth.homonym_class_files`(그래프 전체 이름 → `{짧은 이름: 선언 파일}`) +
    `verify.declared_by_file`: 그 이름의 **모든 항목**이 실제 선언 파일일 때만 인정. 운영 저장 산출물
    `f2ef2241…`·`eea55bdc…` 재검증 ok(수정 전 `[Plan,Task]`/`[Plan]` 재현). 반례 6종 거부.
  - `2cad709` T2 — `review_runner.homonym_notice`: 커밋·범위 퇴고 프롬프트 근거 칸에 동명 이름·각 선언 파일·
    「낮음」 행 이름 개선 검토 권고. 초고(로컬)엔 없음. 자동 개명·일감·차단 없음.
  - `82a7287` T3 — `plan_block` Plan/Task/Check → IssuePlan/IssuePlanTask/IssuePlanCheck(토큰 단위, 별칭 PB 21곳).
    Redmine #971·#963·#970 본문 parse→replace 바이트 왕복 True.
  - `3d009bf` T4 — OnboardingPlan · DecompositionPlan · WorkTask · ContextDocCheck. 저장소 최상위 클래스에
    Plan/Task/Check 0건(AST 실측).
- 체크리스트: C1·C2 충족(근거 노트). C3·C4 는 T5 뒤, C5(운영 합성 관측)는 **마감 뒤에만** 확인 가능, C6 은 마감 흐름.
- T5 진행: 전수 1회차 `SWEEP 236파일 · 12266/12267 · unittest 542/542` — 실패 1은 이 문서 줄 수(위 사유).
  이 커밋 뒤 전수 재실행 → 공식 통합(`tests/integration/checks.json`) → 리포트 `reports/199-971-*.md`.
- 마감 뒤 관측(C5): `ax-indexer` 회차에서 두 그룹 합성 문서 저장·`source_commit`·커서 `6569345` 이후 전진,
  그래프에 새 이름 반영과 옛 동명 고지 소멸. 단순 rc0 를 성공으로 보지 않는다.
- 파급: `service_freshness` 상 ax-task-queue·ax-projects 의존, ax-broker 교집합 없음. requester/worker 배달
  목록과 교집합 없음(`client_mcp` 미변경). 재기동은 wrapup 판정대로.
- 임시 도구(정본 아님): scratchpad `repro971.py`(저장 산출물 재검증) · `rename_tok.py`(토큰 개명).

## 현재 운영 관측

- 21:38 재부팅 뒤 ax-task-queue·ax-broker·ax-projects active. `ax-indexer` 21:38:11 시작 회차가
  `master/plan_metrics` 를 agy 로 합성 중이었다 — 운영 main 은 아직 폴백 전 코드라 같은 거부가 예상된다.
  결과는 그 회차 로그로 확인한다(타이머·코드를 손으로 바꾸지 않았다).

## 남은 관측 — 끝난 일감은 여기 적지 않는다

- 끝난 일감의 결과는 Redmine 완료 일감(`ax-cluster`, 상태 완료)의 마감 노트와 `reports/` 가 정본이다.
- #964·#966 배포 후 관측(C6): `ax-batch` 회차 `complete:true` · 완료 주차 재생성 없음 · 새 생성 호출이 `[agy]` 먼저.
  agy 우선 뒤 생성 호출 56→10/15분 감소는 사용자에게 올릴 발견이다(조치 미결정, 자동 배치 끄지 않음).
- #383 미실측: 상용 체인 합성 실물(토요일 22시 이후 `ax-batch`), finalize 로 쌓이는 pipeline 신호.
- #942 relay: `.venv/bin/python -m master.relay` · 로그 `~/ax-state/relay` · 한도 소진 뒤 이어가기 미실증. #941 미착수.

## 지휘·승인·미확인

- 마스터 마지막 담당 기록 claude(2026-11-14 15:48:34) — 이번 세션도 Claude 라 재기록하지 않았다.
  워커 전역 codex(state, 2026-10-18). 모드 변경 없음.
- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842, 상한 150줄).
- #971 승인 범위: 「진행」 = 커밋 → `issue_finish(confirm=True)` → 신선도 판정 재기동 → 인수인계 커밋·push →
  배달·`check`(§1.9). 이 문서 축소는 사용자 「A로 진행해」로 #971 범위에 포함됐다.
- 미처리 리뷰: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · #942 R351~R355 ·
  그 뒤 마감분(#383~#970)은 도착 미확인 — 각 Redmine 노트로 본다. R193-1 은 사용자 판단 보류.
- 결정·구현 대기: #326 · #935 · #839 · #741 · #738 · #941 · #968.
- 조건 대기: #272(ModularStage 마운트), #211·#855(KR 정답 30건·RAG 실사용 검증), #858(#856 선행).
- `.33` 첫 실제 요청자 마감·연결, 실제 BC-250 poweroff 미확인. 자동 로드 문서의 M7 open 서술 미정리(M8 열림).
- `.2` 홈 중복 스킬 경고(`~/.agents/skills/ax-work`)는 #738 축. 8103 LAN 리포트 공개는 사용자 2026-11-13 결정으로 유지.
- #938 등 리서치와 아이디어 부모 #952·#956(자식 #953~#955·#957~#959)은 착수 승인이 아니다.
- ⑦ 전진·finalize·파괴적 Git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.

## 바로 다음 작업

1. #971 T5: 전수 재실행 rc0 → 공식 통합 → 리포트 199 → C3·C4 기록 → `issue_finish(971)` 미리보기 → `confirm=True`
   → `master.issue_wrapup 971`(재기동 판정 → 인수인계 커밋·push 요구 시 rc2 → 재실행으로 배달·`check`).
2. 마감 뒤 C5 운영 관측(위 「마감 뒤 관측」) — 결과를 #971 노트에 덧붙인다.
3. #964·#966 관측과 agy 처리량 감소 보고 · 실물 확인 거리: `ax-batch` 의 `recipe_synthesis` 줄(#383) ·
   rejected 라운드 `[history]` 줄(#943) · relay 한도 20% 배너(#368) · `색인 걷기가 아직 안 지났다` 줄(#950).
   다른 일감은 사용자 선택을 기다린다.
