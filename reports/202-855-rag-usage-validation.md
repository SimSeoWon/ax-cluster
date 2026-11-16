# 202 — #855 RAG 실사용 검증: 일감 연결 기록 · 평가 라벨 · 요청 단위 검토 화면

2026-11-16 · Claude · 같은 세션(#971~#973 뒤, 색인 회차 대기 중 착수).

## 출발점

2026-11-13 분석(#855 노트): AXCluster user_command 94검색/89요청 — 원문은 94/94 있지만 session_id·work_id 94/94 빈 값,
이슈·요청 유형·검색 목적·채택 증거 필드 없음. 사용자: 「RAG의 결과물이 어느정도 적합도를 가졌는지 판단의 근거가 될 수
없는 자료였네.」 → 로그만으로는 적합도·반영률을 낼 수 없다.

## 인터뷰에서 정한 것 (사용자 확인)

분류 **신규 기능**(#837 확장) · 범위 **A+B**(연결 기록·검토 화면 + 사람 확정 평가 라벨·집계 검사) · 라벨 입력은
**MCP 도구 + CLI, 웹UI 는 읽기만**(8103 `/api/v1`·화면은 무인증) · 비범위: 가중치·게이팅·정답 자동 확정·#837 재구현·과거
94건 추측 소급·ModularStage 합산·웹UI 쓰기·#851·클라이언트 배달. 수행 「이 세션 직접」.

## 바꾼 것 (`issue/855`)

- `853dbd3` T1 — `search_context_tool(issue_id, purpose)`. `issue_id` 를 비우면 마운트 프로젝트의 **진행 중 일감 잠금**
  (`issue_lock.current`)에서 관측값을 찍는다(`issue_id_source=issue_lock`), 잠금이 없으면 아무것도 안 찍는다. 원문 속 숫자는
  연결로 쓰지 않는다. 착수 전 인터뷰 재료 검색은 그 일감 번호(`source=interview`). `list_entries(issue_id=)` 필터.
- `0ff78ea` T2 — `master/context_search/rag_labels.py`: `<트윈>/rag_labels/labels.jsonl` 에 덧붙이는 판정(근거 제공 있음/일부/
  없음/확인불가 · 채택 직접/간접/확인불가 · 후보/확정 · 근거 인용 · 검증자 · 판정 당시 문서 `content_hash`). 대상별 최신
  판정이 유효(이력 보존). **「직접」은 산출물 근거(커밋 해시 · `#N T#` · `파일:줄`) 없으면 거절**, 「확정」은 검증자+근거
  필수. `summary`(요청·검색·문서 분모 · 행별 판정 · 집계) · `check`(집계↔행·분모 불일치, 근거 없는 「직접」 행 적발) ·
  CLI `add|list|summary|check`. 원본 검색 로그는 바이트 그대로.
- `cbb1d4c` T3 — ax-projects `rag_label_tool`(기록 — 거절은 `ok:false`+사유) · `rag_labels_tool`(조회·요약·problems).
  `test_mcp_servers` 도구 수 50→52(플랜 동의 범위의 계약 변경).
- `c6e79a4` T4 — `rag_logs` 요청 묶음 머리 요약: 관측 일감+출처와 **현재 제목**(「현재 조회값 · 검색 당시 요구가 아니다」
  표기, 2초 제한·10분 캐시, 실패면 번호만) 또는 「연결 없음(확인불가) · 원문 번호 후보(확정 아님)」 · 검색 목적 · 요청 판정 ·
  검색 판정 n/m. 검색별 목적·판정은 접힌 상세. `issue_id` 필터(화면·API). 공개 API 에는 판정 요지만 — 근거 인용·메모 비공개.

## 실물 대조 (T5)

이 세션의 실제 요청 「배달하고 971 진행하자」(search `a2738b13`): 반환 6건 중 verify·test_context_synth 가 #971 `89dad6e`
수정 파일과 겹치고, synth·pyparse·review_runner(`2cad709`)는 반환되지 않았다. 수정 위치는 앞 세션 스펙이 이미 지목했다 —
그래서 **근거 일부 · 채택 간접 · 후보**(검증자가 그 검색을 쓴 에이전트 자신이라 확정하지 않음). 운영 트윈 집계: 분모 검색 125 ·
요청 120 · 문서 729, 판정 각 1, `check` 통과(행 2 · 문제 0). 상세는 #855 노트.

## 검증

- 신규 `test_rag_issue_link` 3 · `test_rag_labels` 5(checks.json 등록) · `test_rag_logs_page` 11 · `test_rag_routes` 6 ·
  `test_mcp_servers` 63 · `test_rag_trace` 4 · `test_interview_materials` 14 · `test_rag_callers` 10 — 모두 rc0.
- 전수 `master.sweep` rc0: 238파일 12284/12284 · unittest 553/553. 공식 통합 `Ran 212` OK.

## 남은 것 · 한계

- 배포 뒤 확인: 운영 MCP 검색에 `issue_id`·`purpose` 가 실제로 찍히는지, 8103 `/rag-logs` 화면 요약.
- `.33`·워커 클라이언트(`client_mcp.tool_search_context`)는 바꾸지 않았다 — 그쪽 검색은 서버 잠금 스탬프만 받는다.
- 판정은 아직 2건(후보)뿐이다. 수치를 정책 판단에 쓰려면 사람 확정 판정이 쌓여야 한다 — 이 일감은 그 **도구**까지다.

최종 결과는 Redmine #855 마감 노트.
