# #1041-A — 결정적 `check_answerable`형 온톨로지 커버리지 사전 게이트 분석 보고서

> 작성일: 2026-11-28 · 일감: Redmine `#1043` (상위 `#1041`, `아이디어 — 추후 검토 수집`)  
> 대조 스킬: `ax-plan` (`master/skills/ax-plan/SKILL.md`), `distribute` (`master/skills/distribute/SKILL.md`), `ax-ontology` (`master/client/skills/ax-ontology/SKILL.md`)  
> 대조 코드: `master/ontology/drift.py`, `master/ontology/unassigned.py`, `master/context_search/search.py`, `master/context_search/domain_index.py`  
> NVIDIA 원전: `auto_ontology/retrieval/entity_coverage/agents/coverage.py`, `mcp/auto_ontology_mcp/tools.py` (`check_answerable`)

---

## 1. 개요

NVIDIA `auto-ontology`는 에이전트가 비싼 본 작업(`ask_question`)에 들어가기 전에 `check_answerable`로 질의 엔티티 대비 온톨로지 커버리지(`1/n`)와 미커버 개념(`uncovered_entities`)을 먼저 판정한다.

AX 클러스터에 이 개념을 **LLM 0(완전 결정적)** 형태로 도입해, `ax-plan` 착수 전 인터뷰/플랜 수립과 `distribute` 분해 직전에 **"요청에 등장하는 클래스·키워드가 active 도메인 온톨로지에 얼마나 덮여 있는지, 미분류(`unassigned`)인지, 근거 파일이 변경된 `suspect` 상태인지"**를 한 번에 점검하는 사전 커버리지 게이트(예: `check_ontology_coverage`)를 검토한다.

---

## 2. 실제 코드쪽 내용

### 2.1 NVIDIA 원전 구현
- `auto_ontology/retrieval/entity_coverage/agents/coverage.py`:
  - `_compute_coverage(entities, col_attr_hits)` → `len(covered) / len(entities)` 비율 계산.
  - `_uncovered_entities(entities, col_attr_hits)` → 순서 보존 미커버 엔티티 목록 반환.
  - `mcp/auto_ontology_mcp/tools.py`: `search_terms` → `check_answerable` → `ask_question` 순서를 도구 설명(프롬프트)으로 안내.

### 2.2 AX 클러스터 기존 스킬·코드 접점
- **`ax-plan` (`master/skills/ax-plan/SKILL.md`)**:
  - `ax-projects:plan_start_tool(issue_id)`이 `materials`(일감 본문·코멘트·RAG·온톨로지·보고서)를 이미 수집하고, `plan_needed` 단계에서 `search_context_tool`을 호출한다.
  - 다만 현재는 **"검색 결과가 얇거나, 대상 클래스가 active 도메인 밖(`unassigned`)이거나, 도메인이 `drift` 의심 상태"**여도 이를 구조화된 커버리지 수치/경고로 묶어 주지 않는다.
- **`distribute` (`master/skills/distribute/SKILL.md`)**:
  - 요청 접수 시 `search_context_tool` → 실제 소스 대조 → 기능 분해 표 작성 흐름을 탄다. 분산 파견 전 온톨로지 공백을 조기 감지할 결정적 게이트가 없다.
- **재사용 가능한 AX 결정적 모듈**:
  - `master/context_search/search.py`: `focus(query)` (`_BRACKET_RE`로 `[클래스]` 토큰 추출), `fuse()` (BM25 + 벡터 RRF).
  - `master/context_search/domain_index.py`: BM25 0건 차단·유사도 임계(`0.2`)·상한 2건 노이즈 가드.
  - `master/ontology/drift.py`: `audit(paths, domain=...)` → `DomainDrift.suspect` (`changed_files`, `ghosts`, `missing`).
  - `master/ontology/unassigned.py`: 어느 도메인에도 속하지 않은 클래스 판별.

---

## 3. 주의사항

1. **로컬 추론 노드 제약 — LLM 호출 금지(LLM 0)**:
   - NVIDIA 원전은 `REASONING` LLM으로 엔티티 추출과 후보 필터(`CandidateRetrievalAgent`)를 수행한다. AX의 `.2`/`.43` 노드는 `num_ctx=8192`·메모리 여유가 빠듯하므로 **절대 LLM을 태우지 않고** `[대괄호]` 토큰 + 영문 식별자 정규식 + `classes` 테이블 매칭 + 시소러스 별칭 + `domain_index` BM25로만 계산해야 한다.
2. **하드 블로킹 금지 (경고·가이드 성격 유지)**:
   - AX 원칙상 *"정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다"*(`verify_facts.py` 철학). `index_only` 프로젝트나 신규 기능(아직 클래스가 없는 상태)에서 커버리지가 0%여도 **작업 착수를 강제 차단하면 안 되고**, `"미커버 클래스 N개 · stale 도메인 M개"`를 `materials`/응답에 투명하게 실어 주는 soft gate여야 한다.
3. **자동 도메인 편입 금지 (`ax-ontology` §0)**:
   - 미커버 클래스가 발견되더라도 자동으로 도메인에 넣지 않는다. `ax-ontology` 절차대로 사용자에게 제안만 한다.

---

## 4. 좋은점

- **추측 구현 조기 차단**: 온톨로지가 비었거나(`unassigned`) 근거 파일이 이미 바뀐(`drift.suspect`) 상태에서 에이전트가 낡은 문서만 믿고 설계·코드를 짜는 사고를 착수 단계에서 방지.
- **착수 전 인터뷰(`ax-plan`) 품질 향상**: `interview_ask_tool`의 `confidence`/`gaps`에 실제 결정적 근거("대상 클래스 4개 중 2개 미분류, 1개 도메인 소스 변경됨")를 바로 공급 가능.
- **비용 0에 가까움**: 이미 구축된 SQLite `classes`·`class_ontology`·BM25·`drift.audit`만 조합하므로 지연과 토큰 비용이 거의 없다.

---

## 5. 나쁜점 및 리스크

- **신규 기능(Greenfield)에서의 거짓 경고**: 아직 코드베이스에 존재하지 않는 새 클래스를 만드는 일감에서는 식별자 매칭률이 낮게 나오므로, "기존 클래스 미커버"와 "신규 생성 예정"을 구분하지 않으면 알림 피로가 생긴다.
- **한글 질의 토큰화 한계**: `ax-ontology` §1에 실측된 대로 BM25는 리터럴 매칭이라 별칭이 없는 한글 개념은 미커버로 잡힐 수 있다(오히려 별칭 등록 유도 신호로 활용할 수도 있으나 초기엔 노이즈 가능).
- **도구/스킬 복잡도 증가**: 별도 MCP 도구를 또 늘리면(하위 E 이슈와 충돌) 도구 선택 부담이 커진다. 독립 도구 신설보다 `plan_start_tool`의 `materials` 또는 `search_context` 응답 부가 필드로 녹이는 편이 안전할 수 있다.

---

## 6. 실 작업 착수 시 권장 경계

- **1차 최소 범위**: `master/ontology/coverage.py` (순수 함수, LLM 0) 작성 — 입력 텍스트에서 실재 클래스(`classes`)·별칭(`thesaurus`)을 추출해 `covered` / `unassigned` / `suspect_domains`만 반환.
- **연결 지점**: 새 MCP 도구를 늘리기 전에 `plan_start_tool`의 `materials` 요약 한 블록으로 먼저 실증.
