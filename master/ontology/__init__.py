"""온톨로지 문서 — 마일스톤 2 의 중 1.3.

🔴 **범위가 좁다.** 원본 η.1 원안은 1,799 클래스 전체 분류였으나 **active 도메인 멤버십
합집합만**으로 좁혔다(24 클래스로 confidence ≥0.7 100% 달성, 36배 절감). 사용자 발화가
근거다 — *"도메인에 잡혀있는 것만 온톨로지 대상으로 처리"*.

🔴 **폐지된 것을 이식하지 말 것** — Obsidian `.md` 병행 출력 · 검수 큐 · sidecar JSON ·
`ontology_artifacts`. 특히 후자는 **사용자의 청소를 60초 만에 되돌리는 사고**를 냈다.
산출물 표면은 **YAML 하나**다.

## 원본 결정 로그에서 가져온 규칙 (마일스톤 문서에서 이관 — 여기가 읽히는 자리다)

- **자동 실행 4가드**: class_graph≥100 · dep_graph≥100 · active_members≥1 · 미분류≥1
- **매 폴링 무비용 3가드**: 자원 가드 · dirty check(입력 fingerprint) · skip_unchanged
- **PyYAML 의존성 0** — 수동 직렬화, 우리 산출물 형식만 지원 (`yaml_io`)
- **디렉토리 패키지**: `domains/<D>/{domain.yaml, objects/<C>.yaml, actions/<A>.yaml}`.
  **DB 색인 대상은 `domain.yaml` manifest 뿐**
- 🔴 **액션은 함수 1:1 매핑이 아니다** — 누가/누구에게/무엇을/어떤 플로우의 **의미 단위
  종합 기술**. 온톨로지는 컨텍스트 문서들을 **합치고 그 사이 관계·호출을 담는 개념 문서**다
- ✅ 분류는 `classes` 컬럼이 아니라 `class_ontology` **별도 테이블 + FK CASCADE** —
  원본도 `save_graph()` 의 DELETE+INSERT 가 분류를 덮는 사고를 겪고 그렇게 갔다
- 🔴 **멤버 수집은 대화형** — 원본은 자식 1홉을 자동 확장하지만(`expand_seeds_with_one_hop_children`)
  우리는 **제안 → 확인**이다 (`collect.propose`)
- 🔴 **개념 계층은 사람이 요청한다** — `[미션 시스템]` 아래 `[미션 에디터]`. 도구가 추측하지
  않는다 (`hierarchy.add_child`)
"""
