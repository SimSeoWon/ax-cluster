# 22 — #169 log 태깅 이식 (원전 η.12.3) + #204/#103 종결

사용자 지시: #204 종결 → #103 확인·종결 → #169 착수 ("둘 다 순서대로").

## §1 종결 둘

    #204   전 범위(빌드 큐잡 → 추론 pull → 상주화 → 실전 전환) 작동 확인·커밋 완료로 종결
    #103   M3 원 정의(3-work-pipeline.md 중 3.3 표)와 대조 — 범위는 자식 셋이 전부이고
           셋 다 완료(#104 BM25 · #105 BC-250 · #106 tool-calling). 잔여 없음으로 종결

## §2 #169 — 원전 실물과 이식 형태

원전 둘을 전문 독해 (census 인용 각 1회 → 실물 우선):

    ontology_log_tags.py (132줄)         사이드카 log_categories.yaml CRUD — 로그 태그 ↔
                                         CVar ↔ related_invariants. [중요] 저작 방향 (b)
                                         개발자 선작성 확정(2026-07-12): 게임팀이 실제
                                         코드에 CVar+태깅 로그를 넣은 뒤 사람이 사후 기입.
                                         자동 생성·자동 편입 없음
    log_tagging_candidates.py (240줄)    invariant evidence 기반 태깅 권장 지점 MD 리포트
                                         (게임팀 핸드오프용 제안형, LLM 0). 권장 이름
                                         컨벤션 <도메인>.Log<기능>.Enable

이식 (전부 원전 계약 유지):

    master/ontology/log_tags.py          CRUD + tags_for_invariant. [중요] 매치 없음 =
                                         필드 **부재** (null 아님 — "실증 불가"와 "미확인"
                                         구분, 원전 주석 그대로). 마지막 삭제는 파일째
    master/ontology/log_candidates.py    후보 리포트 → <트윈>/ontology/_log_tagging_
                                         candidates.md. evidence 파서는 원전 정규식 그대로
    뷰어 첨부                             /ontology 의 invariant 목록(load_domain_package)에
                                         log_tags 자동 첨부 — 원전 list_invariants 첨부의
                                         우리 자리
    CLI                                  python -m master.ontology log-tags <D> list|set|
                                         remove · log-candidates
    MCP 3종 (8103)                       list/set/remove_log_tag_tool — 도구 31→34종

원전과 다른 곳 둘 (근거는 우리 환경):

    [주의] 확정 등록분 표기    원전은 watcher 의 단순 파서로 사이드카를 못 읽어 dedup 을
                             포기했다("사람이 대조"). 우리는 전체 YAML 리더가 있어 등록된
                             invariant 를 버리지 않고 **[확정 등록됨] 으로 표기** — 사람의
                             대조 자리를 지우지 않고 그 대조를 대신한다
    [주의] 일일 게이트 없음    원전은 watch.exe 유휴 루프 1회/일 — 우리는 그 루프가 없다
                             (ax-indexer 는 push 구동). LLM 0 이라 CLI 로 사람이 부른다

## §3 실측

    리포트 라이브    후보 **85건 / 7개 도메인** (확정 등록 0 — 게임 코드에 아직 태깅이
                    없으니 맞는 수). 서술형 evidence(클래스 0)는 후보 제외가 실물로 확인
    MCP 라이브      ax-projects 재기동 후 도구 3종 등록 확인 · list_log_tags_tool
                    호출 왕복 (MissionRuntime → ok·count 0)
    테스트          신규 7건 (CRUD 왕복·파일째 삭제·부재 시맨틱·파서 원전 동치·제안형
                    불변·뷰어 첨부) · MCP 도구 수 계약 31→34 갱신 · 전체 3518

[주의] ax-projects 재기동에서 종료가 90초 가까이 걸렸다(deactivating 정체 후 재기동) —
서비스 stop 이 느린 것은 관찰 사실로만 남긴다. 재기동 후 livez·/ontology 200.

## §4 남은 것

    1. 커밋 (승인 대기)
    2. [중요] 실 태깅은 게임팀(사람) 몫 — 리포트(_log_tagging_candidates.md 85건)를 보고
       코드에 CVar+로그를 넣은 뒤 log-tags set 으로 확정 기입하는 것이 소비 흐름.
       #169 를 그때까지 열어 둘지, 인프라 완료로 닫을지는 사용자 판단
    3. 원전의 두 번째 절반(agentwiki-log — 기획자 PC 로컬 플레이 로그 대조 MCP)은
       이번 범위 밖 — 위키 클라이언트 자체가 우리에게 없다
