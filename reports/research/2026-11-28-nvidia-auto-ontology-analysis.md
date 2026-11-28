# NVIDIA Auto Ontology 정밀 분석 및 AX 클러스터 온톨로지 고도화 아이디어 검토 보고서

> 작성일: 2026-11-28 · 작성: Antigravity (Gemini 4 Neon) 리서치 보고서  
> 관련 일감: Redmine `#1041` (`아이디어 — 추후 검토 수집`)  
> 분석 대상 레포: `https://github.com/NVIDIA/auto-ontology.git` (기준 커밋: `086b25ec`, 2026-11-26, Apache-2.0)  
> 대조 대상(AX 클러스터): `master/ontology/` (`__init__.py`, `synth.py`, `parse.py`, `verify_facts.py`, `drift.py`, `edit.py`, `staging.py`, `contexts.py`, `log_candidates.py`), `master/context_search/` (`index.py`, `domain_index.py`)  
> 목적: NVIDIA의 오픈소스 `auto-ontology` 실제 소스 코드를 정밀 분석하고, 코드베이스 디지털 트윈용으로 구축된 AX 클러스터 온톨로지 시스템과 구조·철학을 대조하여 **차용 가능한 설계 아이디어**와 **도입 시 주의·배제할 요소**를 도출함.

---

## 1. 개요 및 핵심 정체성

`NVIDIA/auto-ontology`는 NVIDIA Agent Toolkit / Agent Knowledge Foundation 소속으로 공개된 오픈소스 프레임워크다. 흔히 연상되는 3D/물리 디지털 트윈이 아니라, **흩어진 엔터프라이즈 관계형 DB(PostgreSQL·Snowflake·Databricks·BigQuery·DuckDB·ClickHouse·Trino·MySQL·SQLite 등 10종 커넥터) 위에 AI 에이전트용 시맨틱 레이어(지식 그래프)를 자동 생성·검증·노출하는 Text-to-SQL 컨텍스트 계층**이다.

- **풀려는 문제**: LLM이 문법적으로 맞는 SQL을 생성해도, 조직마다 다른 비즈니스 개념("매출", "활성 고객")과 숨겨진 조인 경로·그레인(grain)을 몰라 틀린 숫자를 반환하는 **Text-to-SQL 신뢰성 벽**을 해소한다(BIRD-Interact·BEAVER 리더보드 타깃).
- **AX 온톨로지와의 본질적 공통점**: 원천만 **엔터프라이즈 DB vs C++/Python 코드베이스**로 다를 뿐, **"원시 스키마/소스를 그대로 LLM에 던지면 환각이 발생하므로, 자동 추출 → 결정적 사실 검증 → 사람 인증 → MCP 노출의 중간 의미 지도를 둔다"**는 아키텍처 본질은 AX 클러스터 온톨로지와 정확히 같은 축에 서 있다.

---

## 2. NVIDIA `auto-ontology` 실제 소스 아키텍처 정밀 분석

### 2.1 전체 서비스 구성 (`docs/architecture.md`)

| 컴포넌트 | 스택 | 역할 | 포트 |
| --- | --- | --- | --- |
| Frontend / Gateway | Next.js, Better Auth, Prisma | Chat·카탈로그·설정 UI, 인증·RBAC, 공개 API 게이트웨이 | `3000` |
| Backend | FastAPI (Python 3.12+), LangChain | ReAct Text-to-SQL 에이전트, 카탈로그·온톨로지 API | `3001` (내부망 전용) |
| Ingestion Service | FastAPI | 카탈로그 수집, PII 탐지, 시맨틱 컴파일 스케줄러 | `3002` (내부망 전용) |
| MCP Server | FastMCP (`mcp/auto_ontology_mcp/`) | 공개 API 앞단의 **읽기 전용** 에이전트 도구 노출 | `3003` |
| Storage / VDB | PostgreSQL 17 + `pgvector` | 앱 상태, 카탈로그, 온톨로지 그래프, 벡터 임베딩 통합 저장 | `5432` |
| 선택 연동 | HashiCorp Vault, KumoRFM | 연결 자격증명 관리, 예측 질의(`predict`, PQL) | - |

- **모델 역할 4분리**: `REASONING` · `NON_REASONING` · `EMBED` · `RERANK` (실제 `RERANK`는 브리지 테이블 귀속 단계에만 사용되며, 질의 응답 루프에서는 사용하지 않음).
- **이식성 표준**: Apache Ossie(구 OSI) YAML import/export 지원 (`POST /api/model/import`, `export`).

### 2.2 온톨로지 생성 파이프라인 (`auto_ontology/semantic/`)

2단계 패스(테이블 단위 → 교차 테이블)로 구성되며, **결정적 규칙/SQL과 LLM 추론을 명확히 교차 배치**한다.

1. **카탈로그 수집 (`ingestion_service/ingest.py`, `catalog/diff.py`)**
   - 테이블·컬럼·PK·선언 FK·뷰·쿼리 이력을 SQL로 추출하고 `pgvector`에 임베딩.
   - `catalog/diff.py`: 재수집 시 `pandas` 기반 스키마 diff로 추가/삭제/형상 변경(`table_type`, `pk`)만 갱신하되, UI에서 사람이 편집한 `description`은 덮지 않고 보존.
2. **Per-table 패스 (`semantic/visit_enter.py`)**
   - 최대 1,000행 샘플링으로 `distinct_ratio`(≥0.95면 unique 후보)·저카디널리티 distinct values 추출(SQL) → 날짜 포맷 추론(규칙) → FK 후보·정션 테이블·컬럼 설명·Term/동의어 추출(LLM).
3. **Cross-table 패스 (`semantic/compile.py`)**
   - **`term_families.py` (규칙 전용, I/O 없음)**: `OLD_ROOMS`/`NEW_ROOMS`, `V1_`/`V2_` 같은 스키마 복제 접두사를 **미러링된 엣지 + 컬럼 Jaccard 유사도(0.8 / 0.5) + 최소 증거 3건 + 동일 접두사 내부 전이 확장**으로 결정적 그룹화(`DIM_DATE` 같은 공용 허브를 통한 오확장 차단).
   - **`semantic_fk.py` (데이터 실증 기반 관계 추론)**: 선언 FK 우선 → 없으면 VDB+LLM 후보 선택 → **실제 컬럼의 오름차순 distinct value 포함률 검증(`fk_values.py`)** → 값 기반 shortlist 폴백 → **실제 JOIN 쿼리가 1행 이상 반환할 때만 `SEMANTIC_FK` 저장**. 짧은 정수 코드(`1..16`)나 자기 테이블 밀집 `id`에 대한 오탐 폴백을 명시적으로 차단.
   - **`sql_attribute_suggester.py` (쿼리 이력 역환류)**: `sqlglot` AST로 과거 쿼리 이력에서 `WHERE`/`JOIN ON`/`HAVING`/집계/`CASE` 하위 식을 추출해 Term당 상위 10개를 LLM에 넘겨 재사용 가능한 `SqlAttribute` 후보 제안.

### 2.3 에이전트 질의 응답 & 결정적 가드 (`auto_ontology/retrieval/`)

1. **사전 커버리지 게이트 (`check_answerable` — `retrieval/entity_coverage/agents/coverage.py`)**
   - 비싼 전체 에이전트 루프를 돌리기 전에 `POST /api/question-entity-coverage`로 질의 엔티티 대비 온톨로지 커버리지(`1/n`)와 **`uncovered_entities`(미커버 개념 목록)**를 반환.
   - 커버리지가 부족하면 에이전트가 환각 답변 대신 사용자에게 명확화 질문이나 소스 연결 요청을 하도록 유도.
2. **ReAct 루프의 결정적 안전장치 (`retrieval/text_to_sql/react/`)**
   - **조회 근거 강제 (`run_sql`)**: SQL 실행 전 카탈로그로 테이블·컬럼명 실존을 검사(유사 이름 제안 포함)하고, **이번 에피소드에서 `retrieve`가 반환하지 않은 테이블을 참조하는 SQL은 거부**.
   - **조인 팬아웃(Fanout) 탐지 (`react/fanout.py`)**: `sqlglot` 스코프 분석 + 카탈로그 `distinct_ratio < 1.0`으로 `1:N` 조인 시 집계 중복 계상(`SUM` 뻥튀기)을 결정적으로 탐지. 특히 **오탐 시 1회만 거절하고 같은 SQL이 재제출되면 수용하는 소프트 가드** 설계가 돋보임.
   - **3단계 Provenance 추적 (`react/provenance.py`)**: 저장된 분석(`custom_analyses`)이 최종 SQL에서 **`retrieved`(노출만 됨) → `reference`(필터 조건 재사용) → `executed`(정규화 AST 일치로 실제 실행)** 중 어느 단계까지 쓰였는지 SHA-256 지문과 함께 결정적으로 판정.
3. **의도적으로 좁힌 MCP 표면 (`mcp/auto_ontology_mcp/tools.py`)**
   - OpenAPI 87개 엔드포인트 중 **단 7개(+복합 2개 = 총 9개)만 명시적 allow-list(`MCPType.EXCLUDE` 후미 차단)**로 노출.
   - *"87개를 다 열면 에이전트 도구 선택 품질이 급락한다 / 도구 설명은 프롬프트다 / 원시 스키마 브라우저를 열면 에이전트가 시맨틱 레이어를 우회한다"*는 원칙을 코드 주석으로 못박음.
   - 기동 시 `missing_from_spec()`으로 업스트림 경로 변경을 즉시 실패 처리해 도구 표면이 조용히 축소되는 현상을 방지.
4. **3-스킬 분리 (`skills/nvidia-ontology-{setup,management,query}/`)**
   - 설치(`setup`) · 쓰기/모델링/인증(`management`, REST 전용) · 조회/검증(`query`, MCP 읽기 전용)으로 스킬을 분리하고, 각 스킬에 `runtime-contract.yaml`, `BENCHMARK.md`, `evals/`를 동봉.

### 2.4 실제 소스에서 확인된 한계·기술 부채 (문서 요약만으로는 안 보이는 지점)

1. **인증(Certify)은 표시용 배지일 뿐 검색 가중치에 미반영** (`docs/architecture.md` L191-192): 인증 여부가 에이전트 검색 순위나 필터를 바꾸지 않음.
2. **쿼리 이력 사용량 랭킹 비활성 버그 보존** (`semantic/sql_attribute_suggester.py` L69-118): `_usage_score()`가 `return 0.0`으로 고정돼 있음(예전 `count_monthly_YYYY_MM` 정규식과 실제 저장 키 `count_{month}_{year}` 불일치로 인한 기존 버그를 회귀 방지 차원에서 그대로 둔 상태 → 실제로는 최다 사용이 아닌 삽입 순서 상위 10개만 사용).
3. **수동 편집한 조인 기본값 유실** (`docs/architecture.md` L189-190): 컴파일마다 `select_semantic_fk_join_defaults`가 조인 기본값을 재선택하므로, 사용자가 끈 FK 조인이 다음 컴파일에서 유지되지 않음.
4. **내부 서비스 인증 경계 취약성** (`README.md` L277-281): `:3001` 백엔드는 프론트엔드가 넘기는 `x-auto-ontology-user-id` 헤더를 무검증 신뢰하고, `:3002` 인제션 서비스는 자체 인증이 없어 반드시 프라이빗 네트워크 격리가 필수.

---

## 3. AX 클러스터 온톨로지와의 정밀 대조

| 비교 항목 | NVIDIA `auto-ontology` | AX `master/ontology` | 평가 |
| --- | --- | --- | --- |
| **저장 정본** | Postgres 17 + `pgvector` | 파일시스템 YAML 패키지 + SQLite/Chroma 파생 색인 | AX가 홈 클러스터·Git 친화성·경량성에서 우위 |
| **구조 객체 생성** | 테이블 프로파일링 + LLM Term 추출 | `objects`는 결정적 추출(LLM 0), `actions`/`invariants`만 LLM | AX가 환각 면적 통제에서 더 보수적·견고함 |
| **사실 검증 게이트** | FK는 실제 DB JOIN 실행 검증 / SQL은 카탈로그+팬아웃 검증 | `parse.py` 필터 + `verify_facts.py`(`methods` 6,380건 대조) | 둘 다 "LLM 자기검증 금지, 결정적 게이트 우선" 철학 일치 |
| **사람 검수 보존** | 테이블 단위 미컴파일 유지(단, FK 기본값은 덮임) | `verified_by_user: true` 항목 잠금 + `staging.py` A/B swap | AX의 항목 단위 잠금 + 스테이징이 더 정교함 |
| **드리프트 감사** | 스키마 diff 재수집 중심, 의미 드리프트 추적 약함 | `drift.py`: `protected_at` + **실제 도메인 파일 `git diff`** | AX가 알림 피로 억제와 근거 추적에서 한 수 위 |
| **사전 커버리지 검사** | `check_answerable` (`coverage` + `uncovered_entities`) | 없음 (바로 검색·계획 진행) | **NVIDIA 측의 가장 실용적인 우위 요소** |
| **사용 이력 환류** | SQL 쿼리 이력 → `SqlAttribute` 자동 제안 | 검색 로그 저장·라벨링은 있으나 온톨로지 자동 후보 환류 미연결 | **AX에 확장 가치 높음** |
| **도구 표면 통제** | 87개 중 9개 읽기 전용 allow-list + 기동 시 spec 검증 | `ax-client` / `ax-projects`에 40~50+ 도구 노출 | **도구 표면 정리·읽기/쓰기 경계 참고 가치 높음** |
| **근거·출처 추적** | `retrieved` → `reference` → `executed` 3단계 provenance | `evidence` 문자열 + `confidence` + `verified_by_user` | **응답/리뷰 단계 실사용 추적 아이디어 유효** |

---

## 4. AX 클러스터에 차용할 만한 핵심 아이디어 5선 (우선순위순)

### 아이디어 A. 결정적 `check_answerable`형 온톨로지 커버리지 사전 게이트 (최우선 추천)
- **원전 착안**: `auto_ontology/retrieval/entity_coverage/agents/coverage.py` (`coverage` 비율 + `uncovered_entities`).
- **AX 적용 설계**:
  - 로컬 LLM(`.2`/`.43`) 호출 없이 **결정적(LLM 0)**으로 구현: 질의/일감 본문에서 추출한 심볼·키워드(`classes` 그래프 매칭 + BM25 토큰) 대비 active 도메인 온톨로지에 포함된 비율, 미분류(`unassigned`) 클래스 목록, `drift.py` 기준 `suspect`(근거 소스 변경) 여부를 반환하는 경량 도구(예: `check_ontology_coverage`).
  - 계획(`ax-plan`)·분산(`distribute`)·워커 파견 직전에 호출해, 온톨로지가 비었거나 낡은 영역이면 **추측 구현 대신 먼저 도메인 수집/갱신을 안내**하는 사전 게이트로 활용.

### 아이디어 B. 실사용 이력(검색 로그 + Git Co-change) 기반 온톨로지 후보 역환류
- **원전 착안**: `sql_attribute_suggester.py`의 쿼리 이력 → `SqlAttribute` 제안 파이프라인 + AX 기존 [log_candidates.py](file:///home/sim/ax-cluster/master/ontology/log_candidates.py)의 "제안 전용(자동 편입 없음)" 원칙 결합.
- **AX 적용 설계**:
  - 정적 `#include`/상속 그래프만 보지 않고, ① `search_log`에서 **반복 실패/저점수 질의 키워드** → 도메인 `aliases` / `tags` 후보 제안, ② Git 커밋 이력에서 **함께 자주 수정되는 클래스 쌍(co-change)** → `collect.propose` 도메인 멤버 추가 및 `action`/`invariant` 후보 제안.
  - 자동 덮어쓰기 없이 제안 리포트(`_usage_candidates.md`)로만 출력해 사람이 선택 반영.

### 아이디어 C. 유사·구버전 클래스군(`term_families` 개념) 구분 표식
- **원전 착안**: `semantic/term_families.py`의 접두사·구조 기반 twin family 감지(`OLD_*`/`NEW_*`, `V1_`/`V2_`).
- **AX 적용 설계**:
  - 언리얼/대형 코드베이스에서 흔한 `Legacy_*`/`Old_*`/`V2_*` 또는 중복 역할 클래스군에 대해, 클래스 그래프 + 네이밍 패턴으로 **구·신 구현 쌍 후보**를 감지하고 도메인 `object` 메타(예: `superseded_by` 또는 `family` 표식)로 기록.
  - 에이전트가 검색에 걸린 레거시 클래스를 현행 정본으로 오인해 수정하는 사고를 예방.

### 아이디어 D. 온톨로지 활용 Provenance 추적 (`retrieved` → `referenced` → `respected`)
- **원전 착안**: `react/provenance.py`의 3단계 활용도 추적 + `run_sql`의 "미조회 테이블 참조 차단" 원칙.
- **AX 적용 설계**:
  - 워커/에이전트가 `search_context`로 받은 도메인 `invariants`·`actions`가 실제 생성된 패치/코드리뷰에서 **단순 조회(`retrieved`)에 그쳤는지, 관련 클래스 수정에 반영(`referenced`)되었는지**를 정적 대조해 리뷰 요약에 첨부.
  - 또한 `verified_by_user`(사람 인증) · `graph_verified`(AST/`methods` 실측) · `llm_inferred`(추론) 출처 등급을 조회 응답에 일관되게 노출.

### 아이디어 E. MCP 도구 표면 큐레이션 & 읽기/쓰기 경계 강화
- **원전 착안**: `mcp/auto_ontology_mcp/tools.py`의 allow-list 큐레이션(87→9)과 `missing_from_spec()` 기동 검증, 그리고 `query`(읽기) / `management`(쓰기) 스킬 분리.
- **AX 적용 설계**:
  - 현재 `ax-client`·`ax-projects` MCP에 수십 개 도구가 한꺼번에 노출되어 에이전트 도구 선택 토큰과 오호출 위험이 커질 수 있음.
  - 일반 조회·작업 에이전트용 **최소 읽기 표면(allow-list)**과 온톨로지 편집/스테이징/동기화 전용 관리 표면의 경계를 점검하고, 도구 설명을 "언제 이 도구를 골라야 하는지" 중심으로 다듬는 검토 과제화.

---

## 5. AX에 그대로 가져오면 안 되는 것 (배제 기준)

1. **풀스택 인프라 직수입 금지**: PostgreSQL 17 + `pgvector` + FastAPI 2대 + Next.js + LangChain 구조는 AX의 핵심 장점인 **YAML 단일 정본 · PyYAML 의존성 0 · 경량 로컬 운용**을 훼손한다. 아이디어만 현재 YAML/SQLite/Chroma 위에 얇게 얹어야 한다.
2. **질의마다 LLM 필터링(`CandidateRetrievalAgent`) 배제**: `.2`/`.43` 로컬 추론 노드는 메모리·컨텍스트 여유가 빠듯하므로(`num_ctx=8192`), 커버리지 검사·팬아웃류 정적 검사는 반드시 **LLM 0 결정적 규칙**으로 변형해야 한다.
3. **표시용 인증 배지 모방 금지**: `auto-ontology`의 `certify`는 검색에 영향을 주지 않는 UI 표시 수준이지만, AX는 이미 `verified_by_user` 잠금과 `drift.py` 감사를 갖고 있으므로 기존 보호 계약을 약화시키면 안 된다.

---

## 6. 결론 및 후속 제안

`NVIDIA/auto-ontology`는 DB/Text-to-SQL 영역에서 **"결정적 검증(실제 JOIN·팬아웃 AST·조회 근거 강제) + 사전 커버리지 게이트(`check_answerable`) + 좁고 정제된 읽기 전용 MCP 표면"**을 매우 실전적으로 구현한 좋은 레퍼런스다. 반면 항목 단위 잠금·소스 diff 기반 드리프트 감사·경량 로컬 운용 면에서는 현재 AX 온톨로지가 이미 더 단단한 기반을 갖추고 있다.

따라서 전체 스택이 아니라 위 **5가지 경량 아이디어(특히 A: 결정적 커버리지 게이트, B: 검색 로그·Git co-change 역환류)**를 선별해 Redmine `아이디어 — 추후 검토 수집` 마일스톤에 등록하고, 추후 마일스톤 우선순위에 따라 단계적으로 검토·반영하는 것을 권장한다.
