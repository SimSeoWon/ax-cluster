# 195 — #967 기각 후보 일괄 기각

2026-11-15 · Claude · #966 마감 뒤 같은 세션에서 수행.

## 사용자 지시와 범위

- 「쌓인 리뷰 정리하는 일감 등록해줘」 → #967 등록(open 348건 · 11월 1~15일 317건).
- 「967 이어서 진행하자. 처음에는 일간(일단) 오탐을 먼저 제외하는 것을 먼저 진행하는게 좋겠어」.
- 인터뷰: 분류 feature(가설 A — 일괄 기각 도구, 「A로 하고 지금 81건으로 시작하자」) → 조사(기획서 없음 · 사유는
  「판정 사유 그대로」) → 명세 → 재현 건너뜀 → 파급 → `ax:spec` → 플랜 T1~T4 · C1~C6 · 「응 등록하고 직접 진행해」.
- 도중 제안 「웹UI에 목록도 보여주고 … 버튼도」 → 명세 비범위(8103 웹 버튼)와 무로그인 쓰기 권한이 걸려
  사용자 선택 B: #967 은 그대로 마감, 웹은 **#968** 로 등록.

## 기존 자산 (만들지 않은 것)

- 판정: `dismissal_candidates.collect` 가 이미 소스 줄 대조까지 한 기각 후보를 만든다(2026-10-17 — 후보는 조언,
  상태 변경은 사람).
- 보기: `list_fixes`(8101 `GET /fixes`, `candidate_details=True`)가 판정 사유·근거를 이미 돌려준다.
- 기록: `fix_index.set_status` — 사유 필수·번호 형식·행 범위 거절(#883).
- 빠진 것은 「고른 후보를 한 번에」뿐이었다.

## 바꾼 것

- `f21a55c` T1 — `dismissal_candidates.dismiss_candidates(root, items, by)`: 지금 목록(`read_results(details=True)`)과
  대조해 open·`candidate`·비stale 만 판정 사유를 그대로 note 로 `set_status(dismissed)`. 항목별 결과 + 합계,
  한 항목 거절이 나머지를 막지 않는다. LLM 0.
- `79515ca` T2 — 8101 `POST /fixes/candidates/dismiss`(MOUNT·태그 필수·`[fix]` 로그) · tagging POLICY·REQUIRE_TAG ·
  요청자 스코프 정확 일치(하위 경로 403, 워커 403) · `ax-client:dismiss_fix_candidates(items, by)`(사유를 싣지 않는다) ·
  `ax-fix` 스킬 단락.

## 검사

- `test_dismissal_candidates` 18 OK(새 2: 사유·항목별 거절·stale·resolved 거절).
- `test_fixes_surface` 157/157 — 실물 앱(인증 미들웨어 포함)에서 401·403·no_project_tag·not_mounted·항목별 응답.
- `test_tagging` 260/260 · `test_client_master_local` 121/121 · `test_client_mcp` 394/394 · `test_mcp_servers` rc0 ·
  `test_skill_conventions` 52/52 · `test_client_spec` 227/227 · `test_client_bundle` 662/662 · `test_integration_coverage` OK.
- 전수 233파일 rc0 · 12122/12122 · 공식 통합 `Ran 207 tests in 232.009s` OK.
- 파급 측정(#966 교훈): 도구·경로 목록을 고정한 검사를 측정 단계에서 내용까지 읽었고, 구현 직후 전부 돌렸다 — 기대값 변경 0.

## 남은 것

- 첫 적용(T4·C6): 배포 뒤 후보 표 → 사용자 선택·승인 → 1회 호출 → 전후 open 수(기준 348).
- #968 웹 화면 — #967 마감 뒤 착수.
