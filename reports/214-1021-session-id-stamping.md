# 214 — 비대화형 호출의 session_id 스탬프 · claude·agy (#1021)

> 2026-11-26 · Redmine `#1021`(Root `#741` 웨이파인더 노드) · 마일스톤 8 — 개선·확장 · 작업 브랜치 `issue/1021` · 시작 `700f1ab`

## 1. 무엇을 했나

`usage_log` 의 `session_id` 는 #1019 장부가 세션을 프로젝트·work·task 에 잇는 열쇠인데, 지금까지 codex 만 채워졌다(#726).
기준선(운영 `700f1ab`): AXCluster `usage_log` lane agy 2,183행 · claude 7행 — session_id **0**.

- **claude** — `usage.parse_claude_json` 이 봉투의 `session_id` 를 버리고 있었다(봉투에 있음: `relay/agents.py`·`test_relay`).
  이제 `Usage.session_id` 로 담는다. 레인 `call_claude` 와 층2·리뷰 `call_claude_why` 가 같은 파서라 둘 다 얻는다.
- **agy** — 봉투에는 id 가 없다. 대신 `run_agy` 가 매 호출 새로 만드는 BRIEF 디렉터리를 표지로
  `agy_trace.find_conversation`(#888 하트비트용)이 대화 DB `~/.gemini/antigravity-cli/conversations/<id>.db` 를 찾는다.
  그 `<id>` 가 수집 사본 `brain/<id>` 와 같다(실측 518/518). `run_agy` 가 끝나면(시도가 있었으면) 이 조회로
  `AgyResult.conversation_id` 를 싣고, `call_agy_why` 는 **최종 시도** 기록에만, 레인 `call_agy` 는 `Usage` 에 넘긴다.
  하트비트와 무관하고, 못 찾거나 읽기 오류면 빈 값 — 호출을 죽이지 않고 지어내지 않는다.

커밋: `5f7eac9`(T1) · `c97cc8a`(T2).

처음 「첫 확인 항목」이던 「agy 출력에 대화 id 가 있나」는 agy 를 돌리지 않고 풀렸다 — 이미 있는 대화 DB 와
`find_conversation` 으로 충분했다(공용 쿼터 0).

## 2. 범위 밖으로 남긴 것

- **ax-gemini**(`gemini_report` 자체 실행기 — `.33` 에서도 돈다, session_id 빈 행 15) — 사용자 결정 A.
- **local(ollama)** 레인 — 세션 파일이 없는 호출이라 해당 없음(≈2,553행).
- **과거 행 보정** — 지도 목적지 「과거는 추정으로 덮지 않는다」.
- 폴백 중간 시도의 대화 id — 최종 대화 하나만 남긴다(받아들인 트레이드오프).

## 3. 검사

- `test_usage_accounting` 28 OK(`test_claude_envelope_session_id_1021`) · `test_layer2_grounding` 39 OK
  (`AgyConversationIdTests` 5 — 찾음·표지=BRIEF · 못 찾음/예외=빈 값 · 폴백 최종만 · 시도 없으면 조회 안 함 · 레인).
- 회귀: `test_conductor_metrics` · `test_usage_cli_paths` 57/57 · `test_usage_sink` 35/35.
- `AX_PROJECTS_ROOT` 설정 `master.sweep` rc 0 — 247파일 · 12769/12769 · unittest 663/663.
- 함정: 새 검사 클래스가 `json` 을 쓰는데 파일이 import 하지 않아 첫 실행이 import 단계에서 죽었다(사용자 승인 뒤 한 줄 추가).

## 4. 마감 뒤 확인 (C3·C4 — 사용자 결정)

C3(마감 배달·check)·C4(운영 호출 실측)는 마감·재기동 뒤에만 확인된다. 마감 전 「제외」로 두고 결과는
Redmine `#1021` 마감 노트에 덧붙인다. 절차:

1. `issue_wrapup 1021` rc 0(배달·check) 확인.
2. 재기동 뒤 운영 호출(합성·리뷰 타이머)이 남긴 새 agy 행에서 `session_id` 를 뽑아
   `~/.gemini/antigravity-cli/conversations/<id>.db` 존재와 다음 수집 뒤 `raw/**/agy/brain/<id>/` 를 대조한다.
3. claude 운영 호출이 그 사이 있으면 같은 방식(`~/.claude/projects/**/<id>.jsonl`), 없으면 그 사실을 적는다.

최종 결과는 Redmine `#1021` 마감 노트에 있다.
