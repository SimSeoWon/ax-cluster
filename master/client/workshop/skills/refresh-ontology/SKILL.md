---
name: refresh-ontology
description: ontology 도메인 패키지 (manifest + objects/ + actions/) 를 지금 상태 기준으로 일괄 재합성. Phase η.5/η.8 의 명시 트리거 진입점 — 평일 10시 자동 게이트와 별개로 즉시 실행. 자연어 발화 "ontology 갱신해줘" / "온톨로지 다시 만들어줘" / "MissionEditor ontology 재합성" 에 자동 발동. stale 도메인만 (디폴트, 리비전 워터마크 비교) 또는 전체 강제 (--all) 또는 특정 도메인 (인자) 선택 가능. 도메인당 LLM 약 3회 호출 (classifier batch + invariants + actions) — 비용 인식 필요.
---

# Refresh Ontology — 명시 트리거 일괄 재합성

## 목적

두 가지 용도를 겸한다:
1. **stale repair** — 리비전 워터마크 비교상 stale 인 도메인(오브젝트 저장 source_commit ≠
   컨텍스트 문서 source_commit)을 즉시 재합성. 평일 10시 자동 게이트를 안 기다리고 즉시.
2. **정규 클린 재생성기** — 클래스 **개명·이동·멤버 편집** 이 끝난 뒤 도메인을 깨끗하게 다시
   합성하는 정식 경로. 멤버 추가는 per-edit partial(scope)이라 반복되면 중복·stale 이 누적된다.
   변경이 **정착된 뒤** 해당 도메인을 인자로 1회 돌려 full 재합성하면 partial 잔재가 정리된다.
   (개명/이동은 `rename_class` 또는 `/manage-domain` 후 본 스킬로 마무리.)

## 호출 방법

사용자 발화:
- `/refresh-ontology` — stale 도메인만 재합성 (게이트 우회, 디폴트 = repair)
- `/refresh-ontology <도메인>` — 변경 정착 후 **클린 full 재합성** (정규 사용 — 권장)
- `/refresh-ontology --all` — 모든 active 도메인 강제 재합성 (stale 무관)
- `/refresh-ontology MissionEditor` — 특정 도메인만 강제 재합성
- `/refresh-ontology MissionEditor UI` — 여러 도메인 강제 재합성
- `/refresh-ontology --rename-english` — 비영문(한글·공백) 도메인을 영문 PascalCase 로 **preview** (제안만, watch 로그 출력)
- `/refresh-ontology --rename-english --apply` — 검토 후 **실제 변환** (MD 재명명 + DB 키 이전 + 패키지 dir 이동)
- 자연어 — "ontology 갱신해줘" / "MissionEditor 다시 추출" / "온톨로지 전체 재합성" / "한글 도메인 영문으로 바꿔줘"

## 환경 확인 (BLOCKING)

1. `.claude/vector_db/class_graph.db` 존재 (Phase η.1 분류 인프라 준비됨)
2. `.claude/context/_domains/*.md` ≥ 1 (사용자 SSOT 존재)
3. RAG 서버 응답 (server_mode 또는 단독) — `context_search` MCP `refresh_ontology` 도구 호출

응답 실패 시 즉시 종료 + 사용자에게 RAG 서버 / watch.exe 상태 안내. localhost fallback X.

## 흐름

### Step 1: 사전 확인

```
audit_ontology_drift(project_root=".")  # 진단만 — 갭 있으면 안내
list_stale_domains(project_root=".")    # 리비전 워터마크 stale 도메인 확인 (옛 list_dirty_domains)
```

- stale 도메인 0건 + 사용자가 `--all` / 도메인 인자 안 줬으면 → "재합성 대상 없음 — 변경 커밋이
  반영되면(컨텍스트 문서 source_commit 갱신) 자동 stale. 또는 `--all` 로 강제 실행" 안내 후 종료
- 사용자에게 비용 안내 — "도메인당 LLM 약 3회 호출, N 도메인 = ~N×3회 호출" + 진행 confirm

### Step 2: 사용자 confirm (AskUserQuestion)

옵션:
- `진행 (stale 도메인 N건)` — 디폴트
- `모든 active 도메인 강제 (--all)` — stale 무관 전체 재합성
- `취소`

사용자 인자에 명시 도메인 있으면 confirm 생략 (사용자 의도 명시).

### Step 3: refresh 호출

```
refresh_ontology(project_root=".", domains=[...] or None, force_all=True/False)
```

비영문 도메인 영문화 (`--rename-english`):
```
refresh_ontology(project_root=".", rename_non_english=True, apply=False)  # preview — watch 로그에 매핑 출력
refresh_ontology(project_root=".", rename_non_english=True, apply=True)   # 검토 후 실제 변환
```
- **preview 먼저** 돌려 `[rename] 전역 이벤트 시스템 → GlobalEventSystem` 매핑을 watch 로그에서 확인하게 안내.
- 사용자가 제안 영문명 검토·동의하면 `--apply` 로 적용. apply 는 LLM 재합성 없이 이름만 이전(분류/invariants/actions 보존). 디렉토리·DB 키·URL 식별자가 영문이 되어 ontology 도구 호출이 살아남.

서버 응답 = `{status, trigger, refreshed_domains, details, elapsed_sec}`.

### Step 4: 결과 보고

```
ontology refresh 완료 — trigger=stale_walk
  도메인: MissionEditor, UI 관리 시스템
  분류된 클래스: 27건 (1-hop 확장 포함)
  invariants_candidates: 8건
  actions: 19건
  소요: 84초
```

도메인별 디테일 (변경 있는 경우만):
- 새로 추가된 클래스 (objects/ yaml 신규)
- LLM 응답 confidence 분포
- yaml_changed=True 인 도메인

### Step 5: 사후 안내

- η.2.5 sync 자동 호출됨 — bm25_domains.db + ChromaDB ontology_domains 컬렉션 갱신
- watch.exe 다음 polling 에 게이트 통과 시 자동 실행 안 함 (이미 처리됨, last_run_at 마킹)
- 추가 코드 수정 → 컨텍스트 문서 source_commit 이 갱신되면 그 도메인이 stale → 다음 평일 10시 자동 게이트에서만 재합성
- **partial 경고가 응답에 있으면** (`partial_scoped`/`prior_partial`) — 변경 정착 후 해당 도메인을
  인자로 1회 더 돌려 클린 full 재합성 권고 (중복·stale 누적 차단).

## 안전 가드

- **active 도메인만 대상** — archive/draft 도메인은 거부 (`/cleanup-drift` 영역)
- **사용자 SSOT MD 절대 변경 X** — `.claude/context/_domains/*.md` 읽기만 (사람 편집 영역)
- **각 L{n}/objects · L{n}/actions · L{n}/invariants 의 stale yaml 정리·재작성** — manifest 보존.
  레거시 flat `objects/`·`actions/`(L 분리 이전, manifest 미참조 dead) 는 full 모드에서 **자동 청소**
  — `.claude/` 내부 기계 산출물이라 사용자 수동 삭제 불필요.
- **`--all` 옵션은 확인 게이트** — 비용 폭증 (N 도메인 × LLM 3회) 가능성 명시
- **stale 아닌데 강제 실행 시** — `--all` 또는 명시 인자 요구 (silent 전체 실행 차단)
