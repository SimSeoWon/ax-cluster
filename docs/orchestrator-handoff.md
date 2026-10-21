# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다 — 지난 내용은 `reports/`·Redmine 노트에 남기고, 2026-10-21 까지의 원문은
> [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-21 23:59 KST · Claude (인계서 정리만 했다 — 코드·검사·Redmine·LLM·파견 변경 없음)
- **상태**: 인계 완료 · 작업 정지. 마지막 실작업은 Codex 세션(#839·#840)이 토큰 소진으로 끝낸 것이다.
  **사용자 재개 지시 전에는 아무것도 이어서 하지 않는다.**
- **저장소**: `~/ax-cluster` · `main 4f40439` = origin/main (23:59 fetch 뒤 실측)
- **지휘 기록** (`conductor.snapshot()` 23:5x 실측): 마스터 담당 `claude`(2026-10-21 00:52 기록) ·
  워커 전역 `codex`(state, 2026-10-18 22:28). 이번 정리에서 둘 다 바꾸지 않았다. 담당 기록은 잠금이 아니다.
- **실행 중**: 로컬 서브 에이전트·검사 프로세스 없음(23:5x `pgrep`). 마스터에 Codex 앱 서버 데몬(pid 5905 등)만 떠 있다.
  AX 상주 서비스·원격 워커·큐는 이번에 재조회하지 않았다 — **미확인**.

## 진행 중인 일감 — #839 · #840 (둘 다 진행, 완료 아님)

상세·실패·남은 결함은 **[`reports/127-doc-sync-cloud-policy-local.md`](../reports/127-doc-sync-cloud-policy-local.md)** — 재개 전에 전문을 읽는다.
Redmine: [#839](http://192.168.0.57:8080/issues/839) · [#840](http://192.168.0.57:8080/issues/840) (부모 [#788](http://192.168.0.57:8080/issues/788)) — 경과 노트는 Codex 가 남기고 되읽었다.

- **승인 범위**: 사용자가 두 일감과 **로컬 서브 에이전트 방식**을 골랐다 — 다시 묻지 않는다.
  커밋·push·배포·서비스 재기동·실제 LLM 호출·워커 파견은 **승인 없음**.
- **#839** 영향 문서 탐지 `doc_sync plan/draft --since/--until` 구현 · 직접검사 20/20 · 실제 저장소 `plan --since HEAD~1` rc0.
- **#840** LLM 정책(agy→codex→quota 때만 claude→전부 quota 때만 local) · 생성 3경로 · local 결과 표시 ·
  재검증 배치 구현 · 직접검사 전부 통과(수치는 리포트 127).
- 🔴 **공식 통합 검사 rc1 — 36개 중 35 통과 / 1 실패, `-f` 로 나머지 미실행.**
  `master/test_review_gen.py:390-391` 이 `DEFAULT_LANES[0] == "codex"` 를 기대한다. 원인은 이 검사가
  리뷰/계획 체인(`layer2_verify.WHY_BACKENDS`)과 본문 작성 체인(`lanes.DEFAULT_LANES`)을 같은 규칙으로 묶은 것.
  이 파일은 **처음 편집 목록 밖**이라 수정하지 않았다. 검사를 통과시키려고 리뷰/검증 체인을 바꾸지 않는다.
- **소스 대조로 찾은, 수정 안 한 결함** (재현 검사 없음): ① ontology 일부 레이어만 cloud 로 갱신돼도 전체 표시 해제
  (`ontology/synth.py:609-632`) ② 재검증이 정렬 첫 2건만 집어 실패 시 뒤 대상이 밀림(`work/revalidation.py:181`)
  ③ 스캔 루트·상위 symlink 경계 미검사 ④ context 쓰기 비원자(CAS 아님). 코드 조각 사실 실패 → 다음 cloud 재작성 루프도 미구현.

### 미커밋 파일 — 지우거나 빠뜨리지 않는다

수정: `docs/document-sync.md` · `master/batch/{gates,run}.py` · `master/context_synth/synth.py` ·
`master/doc_sync/{__main__,registry}.py` · `master/ontology/synth.py` · `master/test_context_synth.py` ·
`master/test_doc_sync_{cli,registry}.py` · `master/test_infer.py` · `master/test_lanes.py` ·
`master/test_ontology_synth.py` · `master/test_runner.py` · `master/work/{infer,lanes,runner}.py` ·
`tests/integration/checks.json`
신규: `master/work/{llm_policy,revalidation}.py` · `master/test_{llm_policy,revalidation}.py` ·
`reports/127-doc-sync-cloud-policy-local.md`
인계서 정리분: `docs/orchestrator-handoff.md`(이 파일) · `docs/orchestrator-handoff-history.md`(신규)

## 사용자 답을 기다리는 것

1. **실패 수정 재개 여부와 범위** — `test_review_gen.py` 편집 포함 여부, 위 결함 ①~③ 수정 포함 여부
2. **#839 근거 방식** — 출처·시각이 박힌 스냅샷 파일 vs `doc_sync` 가 직접 live 조회
3. **#839 보호 문서 4개 실증** — 문서별 계획·동의·레인
4. **#840 조각 재작업 반영** — 후보 보관 vs 후속 라운드 자동 준비

## 바로 다음 작업

1. HEAD·dirty 를 위 목록과 대조하고 리포트 127 을 읽는다.
2. 위 질문 1 의 답을 받는다. 승인되면 구정책 검사 분리 → 레이어 coverage → 재검증 순환 → 루트 경계를 고치고,
   회귀 검사와 공식 통합(`tests/integration/test_axcluster.py`)을 다시 돌린다. 커밋 전에 `master/test_*.py` 전수.
3. 그 전에는 #839·#840 을 완료·운영 반영으로 말하지 않는다. 커밋·배포는 따로 승인받는다.

## 열려 있지만 이 작업과 별개인 것 (기록 시점 — Redmine 재조회)

- [#709](http://192.168.0.57:8080/issues/709) GitHub `SimSeoWon/Test_KimodoMotion` — 사용자가 웹에서 지운 뒤 404 확인하고 닫는다
- [#211](http://192.168.0.57:8080/issues/211) RAG 품질 — **지금은 로그 수집만**(사용자 결정). 형태소·trigram·재색인 등 착수 금지
- [#633](http://192.168.0.57:8080/issues/633) — 자식 [#639](http://192.168.0.57:8080/issues/639) 신규
- 다음 일감은 사용자가 고른다.
