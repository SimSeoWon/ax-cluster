# 212 — 세션 귀속에 확정 장부 우선 · usage_log session_id (#1019)

> 2026-11-26 · Redmine `#1019`(Root `#741` 웨이파인더 노드) · 마일스톤 8 — 개선·확장 · 작업 브랜치 `issue/1019` · 시작 `626ca41`

## 1. 무엇을 했나

마스터 레인 호출(합성·검토 후보·doc-sync 등)은 격리용 `/tmp/ax-*` 에서 돌아 cwd 로는 프로젝트를 알 수 없고 미귀속(tmp_ax)이
됐다. 그런데 그 호출은 `usage_log.jsonl` 에 `session_id`·`source`·`work_id`·`task_id` 를 **직접** 남긴다(`usage.py`).
그 확정 장부를 cwd 보다 앞세웠다.

- `session_usage.load_ledger()` — 등록 프로젝트의 `usage_log.jsonl` → `{session_id: 행들}`. `collect`·`collect_all`·`reparse` 가
  레지스트리를 읽는 자리에서 한 번 읽는다(검사가 `shops` 를 주입하면 장부도 주입값, 없으면 빈 장부 = 종전 동작).
- `ledger_attribution()` — 장부 프로젝트가 앞선다. work·task 는 `source == "dispatch"` 행에서만 온다. 다른 출처의
  `task_id` 칸(`P10`·`readme`·모듈 경로)은 큐 task 가 아니라 버린다(사용자 결정 A — `#1020` 의 `work_of` 오답 논리와 같다).
  장부 프로젝트가 갈리면 추정하지 않고 cwd 로 두고 로그를 남긴다.
- `_place` — 세션 id 후보 = origin(`origin_sid`, `session_provenance.origin_session_id` 와 같은 규칙) ∪ 스냅샷 `session_id`.
  색인 줄에 `attributed_by`("ledger"|"cwd")·`ledger_source` 를 남긴다. 파싱은 한 번으로 줄여 스냅샷에 재사용한다.
- `/usage` 경고 문구 — 「프로젝트는 확정 장부(session_id), 없으면 작업 경로로 정합니다」(종전 「작업 경로로만」은 거짓이 됨).

커밋: `506346b`(T1) · `cc12321`(T2).

relay 장부(`~/ax-state/relay/`)는 실물이 없어(`relay.log` 만) 지도 제목의 「relay」는 이번에 재료가 없었다.

## 2. 실측

| 항목 | 전 | 후 |
|---|---|---|
| 색인 | 2,675 | 2,675 |
| 미귀속 | 2,618 | **1,651** (−967) |
| tmp_ax | 983 | **16** |
| 장부 결합 / `attributed_by: ledger` | 974 / 0 | 974 / **974** |
| dispatch work·task 채움 | 0 | 7 |
| 장부 미결합 1,701건의 귀속 변화 | — | **0** (드라이런·reparse 둘 다) |
| reparse | — | 사본 2,675 · 이동 967 · 사본 없음 0 · rc 0 |

- 스펙 시점 미귀속 2,608 은 그 사이 새로 수집된 세션 때문에 2,618 로 시작했다.
- `.ax-issues` 귀속 issue_id 는 16/16 — `#1020`·`#1019` worktree 세션이 더해졌다(`#1020` 규칙이 그대로 돈다).
- 검사: `test_session_usage` 31 OK(새 6) · `test_usage_dashboard`·`test_usage_routes`·`test_session_usage_dedupe` OK ·
  `AX_PROJECTS_ROOT` 설정 `master.sweep` rc 0(247파일 · 12769/12769 · unittest 654/654) · `test_integration_coverage` OK.
- `/api/v1/usage?source=session&project=AXCluster` 는 reparse 뒤 200.
- reparse 전 `index.jsonl` 백업(sha256 `23c2a273…`)은 세션 스크래치 — 재부팅에 사라진다. 되돌리기는 백업 복원 + 옛 코드 reparse.

## 3. 남은 것

- 남은 tmp_ax 16 은 장부에 session_id 가 없는 호출이다(agy 1 · claude 1 · codex 14) — `#1021`(스탬프 누락 방지) 몫.
- 장부 없는 세션 83개(session_id 는 있으나 색인에 없음 — 보존 기간·미수집)는 범위 밖.
- `ax-projects` 는 재기동 전까지 옛 코드로 수집한다 — 그 사이 다시 받은 레인 세션은 미귀속 자리로 돌아갈 수 있다(재기동 뒤 다음 수집에서 바로잡힌다).
- `#741` Frontier: `#1021` · `#1022`(원인별 표시, 이 노드로 풀림).

최종 결과는 Redmine `#1019` 마감 노트에 있다.
