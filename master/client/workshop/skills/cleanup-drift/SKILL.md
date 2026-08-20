---
name: cleanup-drift
description: ontology DB 의 옛 데이터 잔재 (active MD 부재 도메인 + archive 분류 잔재 + NULL 도메인 분류) 를 대화형으로 정리한다. watcher startup 카나리 `[ontology drift]` 가 갭을 보고하면 본 스킬로 정리. 자연어 발화 "ontology drift 정리", "DB 잔재 정리", "옛 도메인 데이터 삭제", "MissionRuntime 정리" 등에 자동 발동. inactive 도메인 row 삭제 시 FK ON DELETE CASCADE 로 class_ontology row 도 자동 정리. 사용자 콘텐츠 (active MD) 영역은 보호 — 거부 가드.
---

# Cleanup Drift — 온톨로지 DB 잔재 대화형 정리

## 목적

Phase η.4 (Drift 자동 추적) 가 startup 카나리로 보고하는 DB 잔재를 사용자 결정으로 정리.
대상:

- **inactive 도메인** — `domains` 테이블에 row 있지만 사용자 SSOT MD 부재 + archive 도 아님.
  예: 옛 시점에 등록했다가 MD 만 삭제한 도메인 (MissionRuntime 등). DB row + 옛 분류 결과
  잔재가 검색·재분류에 노이즈
- **archive 분류 잔재** — archive 도메인이지만 `class_ontology` 에 row 남아있음. 다음 분류
  사이클이 자연 회복하지만 즉시 정리 옵션
- **NULL 도메인 분류** — `class_ontology` 의 `ontology_domain IS NULL`. 분류 실패 또는 옛
  active 외 응답 차단 잔재. 새 active 도메인 등록 시 재분류 매칭

## 호출 방법

사용자 발화:
- `/cleanup-drift` — 진단만 (read-only)
- `/cleanup-drift --interactive` — 진단 + AskUserQuestion 으로 도메인별 결정 (기본)
- 자연어 — "DB 잔재 정리해줘" / "ontology drift 정리" / "옛 MissionRuntime 데이터 삭제"

## 환경 확인 (필수)

1. 본 메타 저장소 / 배포된 프로젝트인지 확인 — `.claude/vector_db/class_graph.db` 존재
2. RAG 서버 응답 — server_mode 면 `<server_url>/api/v1/ontology/audit_drift` HTTP. 단독
   모드면 `context_search` MCP 도구 `audit_ontology_drift` 직접 호출
3. 응답 실패 시 즉시 종료 + 사용자에게 RAG 서버 상태 안내 (localhost fallback 금지 — BLOCKING)

## 5단계 흐름

### Step 1: 진단

```
audit_ontology_drift(project_root=".")
```

결과 보고 (한국어, 한 단락):
- inactive 도메인 N건 (각 항목 분류 count 명시 — 사용자가 영향 범위 가시화)
- archive 분류 잔재 N건 (도메인:count)
- NULL 도메인 분류 N건 (앞 5건 미리보기 + 총 카운트)
- 갭 0건이면 "정리할 잔재 없음 — 종료"

### Step 2: 사용자 결정 (AskUserQuestion)

drift 카테고리별로 별도 질문 (최대 4개 질문, 멀티선택 X):

**Q1 — inactive 도메인 처리** (도메인 1~3개일 때):
- 옵션: `모두 삭제 (DB row + 분류 cascade)` / `개별 선택` / `무시`
- inactive 도메인이 4+ 개면 더 정밀한 선택 — Q1.1, Q1.2 도메인별로 분리

**Q2 — archive 분류 잔재 처리**:
- 옵션: `다음 분류 사이클 자연 회복 대기` (디폴트) / `즉시 무효화` / `무시`
- 다음 분류 사이클이 active 도메인 매칭으로 자연 회복하므로 디폴트는 대기

**Q3 — NULL 도메인 분류 처리**:
- 옵션: `즉시 일괄 정리 (DB 잔재 제거)` / `새 active 도메인 등록 후 재분류 매칭 대기` (보수) / `무시`
- NULL row 발생 원인: LLM 분류 실패 / 옛 cleanup 의 FK SET NULL 잔재 / active 외 도메인 응답
  정규화 결과 — 모두 같은 잔재. 즉시 정리해도 분류 가치 손실 작음 (다음 polling 에 active
  멤버이면 자연 재분류)

### Step 3: 정리 실행

사용자 결정에 따라 호출:

- inactive 도메인 삭제 — `cleanup_inactive_domain(domain_name)` 도메인마다 1회. 안전
  가드: active 또는 archive 도메인은 거부. 도메인 row 삭제 + 매핑된 class_ontology row 명시
  DELETE (FK 가 SET NULL 이라 자동 cascade 안 됨 — 명시 정리)
- NULL 도메인 분류 일괄 삭제 — `cleanup_null_classifications()`. `ontology_domain IS NULL`
  row 모두 DELETE. 다음 polling 의 분류 사이클이 active 멤버를 자연 재분류
- archive 분류 잔재 — 현재 별도 도구 없음. 다음 분류 사이클이 active 매칭으로 자연 회복 또는
  무시

### Step 4: 결과 보고

```
정리 완료:
  - 삭제된 도메인: MissionRuntime (도메인 row 1 + class_ontology row 12 cascade)
  - archive 잔재: 대기 (다음 분류 사이클 처리)
  - NULL 도메인: 대기
```

### Step 5: 사후 안내

- watch.exe 다음 polling (60s) 에 fingerprint 갱신 → drift audit 갱신
- 다음 startup 카나리에서 inactive_domains 0건 확인 가능
- `/cleanup-drift` 재호출로 사후 검증 가능

## 안전 가드

- **active 도메인 삭제 시도** — `cleanup_inactive_domain_impl` 가 거부 (사용자 SSOT 보호)
- **archive 도메인 삭제 시도** — 같은 가드 (의도된 잔재)
- **DB 쓰기는 명시 결정 후만** — Step 2 AskUserQuestion 통과 안 한 도메인은 손대지 않음
- **사용자 콘텐츠 (도메인 MD) 영역 절대 변경 X** — `/ontology-register` / `_domains/` 디렉토리는
  본 스킬 영역 밖
