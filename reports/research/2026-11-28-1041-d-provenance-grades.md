# #1041-D — 온톨로지 활용 Provenance 추적 및 출처 등급 노출 분석 보고서

> 작성일: 2026-11-28 · 일감: Redmine `#1046` (상위 `#1041`, `아이디어 — 추후 검토 수집`)  
> 대조 스킬: `ax-ontology` (`master/client/skills/ax-ontology/SKILL.md`), `ax-plan` (`master/skills/ax-plan/SKILL.md`), `distribute` (`master/skills/distribute/SKILL.md`)  
> 대조 코드: `master/ontology/verify_facts.py`, `master/ontology/parse.py`, `master/ontology/package.py`, `master/ontology/edit.py`, `master/ontology/drift.py`  
> NVIDIA 원전: `auto_ontology/retrieval/text_to_sql/react/provenance.py`, `auto_ontology/retrieval/text_to_sql/react/run_sql.py`

---

## 1. 개요

NVIDIA `auto-ontology`는 에이전트가 조회한 정의(`custom_analyses`)가 최종 산출물에서 **`retrieved`(보기만 함) → `reference`(조건 재사용) → `executed`(정규화 AST 일치로 실제 실행)** 중 어디까지 반영됐는지 SHA-256 지문과 함께 결정적으로 기록한다(`react/provenance.py`). 또한 `run_sql`은 이번 에피소드에서 `retrieve`로 보지 않은 테이블을 참조하는 SQL을 거부한다.

AX 클러스터에 이 아이디어를 적용해, **① 온톨로지 조회 응답에 항목별 출처·신뢰 등급(`human_verified` / `graph_verified` / `llm_inferred` / `drift_suspect`)을 일관되게 노출**하고, **② 작업 마감·코드리뷰 단계에서 `search_context`로 조회된 도메인 `invariants`가 실제 패치에서 관련 클래스 수정에 반영(`referenced`)되었는지 정적 대조**하는 방안을 검토한다.

---

## 2. 실제 코드쪽 내용

### 2.1 NVIDIA 원전 구현 (`auto_ontology/retrieval/text_to_sql/react/provenance.py`)
- 3단계 상태 상수: `RETRIEVED = "retrieved"`, `REFERENCE = "reference"`, `EXECUTED = "executed"`.
- `sqlglot`으로 SQL을 정규화(`_normalise`)하고 SHA-256 `fingerprint`를 부여해, 미사용 CTE나 단순 테이블 겹침은 `reference`로 과대 계상하지 않도록 엄격히 판정.
- **참고할 한계**: `docs/architecture.md` L191-192에 따르면 NVIDIA의 `certify` 배지는 UI 표시용일 뿐 검색 로직에 영향을 주지 않는다. 반면 AX는 이미 `verified_by_user`·`protected`·`verify_facts`·`drift` 4종 실측 신호를 갖고 있다.

### 2.2 AX 클러스터 기존 코드 접점
- **이미 존재하는 4가지 출처/신뢰 신호 (흩어져 있음)**:
  1. `master/ontology/edit.py` & `package.py`: `verified_by_user: true` (사람 직접 검수·잠금) vs `protected: true` (스냅샷 일괄 보호, `protected_at` 커밋 기준).
  2. `master/ontology/parse.py`: `evidence`, `confidence` (`MIN_CONFIDENCE = 0.5`), `source_signal` (`function-signature`, `lifetime-pattern`, `algorithm`, `check-statement`, `comment`, `lock-pattern`).
  3. `master/ontology/verify_facts.py`: `verify_object` / `verify_action` — `classes`·`methods` 실측 테이블 대조 통과 여부.
  4. `master/ontology/drift.py`: `DomainDrift.suspect` — `protected_at` 이후 도메인 근거 파일의 실제 `git diff` 발생 여부.
- **현재의 빈틈**:
  - `get_object_spec` · `get_action_spec` · `find_invariants_by_class` · `search_context` 응답에서 위 4가지 신호가 **통일된 출처 등급(`trust_grade`)**으로 요약돼 나오지 않는다.
  - 특히 `drift.py` L27-29가 스스로 짚듯 **"호출 표기가 없는 설계 규칙 서술(산문 invariant)"**은 `verify_facts`를 무사 통과하므로, 에이전트가 확정 사실과 LLM 추론 산문을 같은 무게로 취급할 위험이 있다.

---

## 3. 주의사항

1. **코드 패치에 대한 `executed` 판정 과욕 금지**:
   - SQL은 `sqlglot` AST 정규화로 `executed` 일치를 증명할 수 있지만, C++/Python 코드 패치가 자연어 `invariant`를 "실행/준수했다"는 것은 정적으로 완전 증명할 수 없다.
   - AX에서는 **`retrieved`(검색에 노출됨) → `touched`(해당 invariant의 근거 클래스/파일을 패치가 실제로 수정함)** 2단계 정적 매칭까지만 결정적으로 판정하고, 실제 준수 여부 판단은 기존 교차 계열 코드리뷰어에게 넘겨야 한다.
2. **기존 YAML 스키마 파손 방지**:
   - 출처 등급(`trust_grade`)은 YAML에 중복 저장해 드리프트를 만들지 말고, **조회 시점(read-time)에 기존 필드(`verified_by_user`, `protected`, `source_signal`, `drift.suspect`)로부터 결정적으로 계산**해 붙이는 것이 안전하다.
3. **정상 문서 차단 금지 (`verify_facts.py` 원칙)**:
   - `llm_inferred` 등급이라도 조회에서 제외하지 않고, 에이전트가 "소스를 직접 열어 재확인해야 하는 항목"으로 무게를 달리 두게 하는 신호로만 쓴다.

---

## 4. 좋은점

- **에이전트의 맹신 방지**: 조회 결과에 `human_verified` / `graph_verified` / `llm_inferred` / `drift_suspect` 등급이 한 줄로 보이면, 에이전트가 `llm_inferred`나 `drift_suspect` 항목을 만났을 때 실제 소스를 열어 대조하는 습관을 강제하기 쉽다.
- **코드리뷰 집중도 향상**: 리뷰 시 *"이번 패치가 건드린 클래스에 걸린 invariant 5건 중, 작업 중 `search_context`로 조회된 것은 2건, 미조회 3건"*을 결정적으로 보여 주면 리뷰어가 누락된 불변식을 바로 짚을 수 있다.
- **기존 자산 재활용 극대화**: 새 저장소나 LLM 없이 이미 있는 `search_log` + `find_invariants_by_class` + `git diff --name-only` 조합으로 구현 가능.

---

## 5. 나쁜점 및 리스크

- **등급 오해 리스크**: `protected: true`(스냅샷 보호)와 `verified_by_user: true`(사람 검수)를 한 등급으로 뭉개면 `package.py` L86-88이 어렵게 분리해 둔 의미가 퇴색된다. 반드시 둘을 구분해 표기해야 한다.
- **리뷰 노트 장문화**: 모든 `retrieved` 항목을 리뷰 노트에 다 나열하면 노이즈가 커지므로, **패치가 실제 수정한 클래스에 걸린 `touched` invariant 중 미조회/충돌 의심 건**만 추려 짧게 보여야 한다.

---

## 6. 실 작업 착수 시 권장 경계

- **1차 최소 범위**:
  1. `master/ontology/view.py` 또는 조회 헬퍼에 read-time `trust_grade` 계산 함수 추가 (`human_verified` > `protected_fresh` > `graph_verified` > `llm_inferred`, 별도 플래그 `drift_suspect`).
  2. 마감/리뷰 준비 단계에서 `git diff` 수정 클래스 ↔ `find_invariants_by_class` 교차표 1블록(조회 여부 포함)을 결정적으로 첨부하는 옵셔널 리포트.
