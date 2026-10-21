# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-22 00:50 KST · Claude
- **상태**: 인계 완료 · 작업 정지. 사용자 결정 대기(아래). **답 없이 이어서 하지 않는다.**
- **저장소**: `~/ax-cluster` · `main 3123389` = origin/main · 작업 트리는 이 인계서만 dirty(미커밋)
- **배달**: `master.client update` AXCluster `.43`·`.2`·`.33` 3/3 OK · 출처 `3123389` (재기동 뒤 `check` 재확인 rc0).
  [주의] 이 인계서를 커밋하면 HEAD 가 배달 출처보다 앞서 `check` 가 실패한다 — 커밋 뒤 `update` 를 다시 돌린다.
- **마스터 서비스**: `ax-task-queue` 00:48:06 · `ax-projects`·`ax-broker` 00:48:12 재기동(사용자 지시) — `3123389` 코드,
  active/running · 8101·8102·8103 응답 200. 재기동 전 진행 중 task 0건.
- **지휘 기록**: 마스터 담당 `claude`(2026-10-21 00:52) · 워커 전역 `codex`(state, 2026-10-18 22:28). 바꾸지 않았다.
- **실행 중**: 로컬 서브 에이전트·검사 없음.

## 이번 세션에서 한 것

- 인수인계서 정리 — 2,506줄 → 현재판, 원문은 history 파일 (`8f7643a`)
- [#842](http://192.168.0.57:8080/issues/842) **완료** — 등록부 지시문·`docs/15` 덮어쓰기 규칙 + `master/test_handoff_size.py` (`ba97da5`)
- [#839](http://192.168.0.57:8080/issues/839)·[#840](http://192.168.0.57:8080/issues/840) 구현 + 실패 수정 커밋 `3123389` · push · 배달 · 서비스 재기동.
  둘 다 **「진행」 유지**(완료 아님 · 진척률 0% 그대로). 상세 [`reports/127-doc-sync-cloud-policy-local.md`](../reports/127-doc-sync-cloud-policy-local.md) 2026-10-22 절
  - 검증: 가짜 `agy`·`codex`·`claude`·`ssh`·`scp` 를 PATH 앞에 두고 공식 통합 181/181 · `master/test_*.py` 185파일 9,115/9,115 rc0 · 상용 CLI 호출 0건
  - 🔴 고치기 전 `test_descriptions.py` 가 실제 agy 를 불렀다 — 이 세션 통합 2회분 쿼터 사용 추정(사용량 기록 미대조)
  - [주의] 기존 검사 일부가 실제 SSH(`.43`·`.33` 탐침)를 시도한다 — 범위 밖이라 그대로

## 사용자 답을 기다리는 것

1. **#839 운영 근거 방식** — 출처·시각이 박힌 스냅샷 파일 vs `doc_sync` 가 직접 live 조회
2. **#839 보호 문서 4개 실증**(claude·agents·home-claude·home-agents) — 어느 문서부터, 문서별 계획·동의·레인
3. **#840 로컬 조각의 cloud 재작성 반영** — 후보 보관 vs 후속 라운드 자동 준비
4. **#840 남은 구현** — 코드 조각 사실 실패 → 다음 cloud 재작성 루프 · context 쓰기 원자성(CAS)
5. #839·#840 Redmine 진척률(둘 다 0%)을 맞출지

## 바로 다음 작업

1. HEAD·dirty·배달 출처를 재조회한다(이 인계서 커밋 여부 확인).
2. 위 질문의 답을 받아 이어서 한다 — 답 없이 #839·#840 을 완료로 닫지 않는다.

## 열려 있지만 이 작업과 별개인 것 (기록 시점 — Redmine 재조회)

- [#709](http://192.168.0.57:8080/issues/709) GitHub `SimSeoWon/Test_KimodoMotion` — 사용자가 웹에서 지운 뒤 404 확인하고 닫는다
- [#211](http://192.168.0.57:8080/issues/211) RAG 품질 — **지금은 로그 수집만**(사용자 결정). 형태소·trigram·재색인 등 착수 금지
- [#633](http://192.168.0.57:8080/issues/633) — 자식 [#639](http://192.168.0.57:8080/issues/639) 신규
- 다음 일감은 사용자가 고른다.
