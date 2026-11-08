# 150 — #917 R240 수용 지적 4건

> 2026-11-08 · Claude · 일감 #917 · 시작 리비전 `24cbb62` · 작업 위치 `.ax-issues/917`(`issue/917`)

## 배경·사용자 결정

- #884 종합 리뷰 R240(지적 12)을 사용자와 검토했다(2026-11-08). R240-5·7(+원 지적 R234-3·R235-3)은 오탐 기각
  — 추적 해시는 등록 때 `issue_track` 이 소문자로 정규화해 저장한다. R240-3·4·6·9·10·11 은 의도된 표기·도달 불가
  경로·저장소 관례라 기각. **R240-8·1·2·12 수용** → 이 일감.
- 「#917 진행해」 → 플랜·수행 방식 질문에 「이 세션에서 직접」(서브에이전트·워커 분산 없음).
  RAG request_id `f909a2b02f1c4897b5fc490dd1957dbc`.

## 변경

| 태스크 | 지적 | 변경 |
|---|---|---|
| T1 | R240-8 | `issue_progress._sync_round` — 워터마크 존재 검사(`_has_commit(repo, wm)`)를 회차당 **처음 필요할 때 1회**로 끌어올렸다. 없으면 `[주의]` 를 회차당 1줄. 대기 해시가 없으면 묻지 않는다 |
| T2 | R240-1·2 | 공개 이름 `issue_track.norm_sha`·`find_hash`, `review_queue.item_id`, `review_runner.is_registered_root` 추가. 밑줄 이름은 모듈 안 호출부용 별칭으로 남겼다. `issue_link`(5곳)·`issue_progress`(1곳)가 공개 이름을 쓴다 — 다른 모듈의 밑줄 참조 0(grep) |
| T3 | R240-12 | `test_issue_link` — `new_root()` 가 만든 임시 루트를 기억하고 `run_cleaning(fn)` 이 성공·실패와 상관없이 지운다(예외는 그대로 올린다) |

## 검증

- 신규 회귀: `test_워터마크_부재는_회차당_한_번`(대기 해시 3 · 미러에 없는 워터마크 → git 확인 1회 · `[주의]` 1줄 ·
  waiting 유지, 큐 해시만이면 확인 0) · `test_cleanup_on_failure`(의도한 실패 뒤 루트 부재 · 예외 전파).
- 관련 검사 rc0: issue_link 40/40 · issue_progress 96/96 · issue_track 95/95 · review_queue 65/65 ·
  review_runner 109/109 · review_range 75/75 · review_enqueue 31/31 · issue_review 43/43.
  `test_issue_link` 실행 전후 `/tmp/ax-il-*` 0 → 0.
- 정적(`pystatic.run_static`, 기준 `24cbb62`, 7파일): pyflakes 차단 0·노트 0 · import 차단 0 · mypy 차단 0·비차단 노트 8.
- `git diff --check` rc0.
- 공식 통합(정본 명령, worktree): rc0 **`Ran 188 tests in 170.501s`·`OK`(188/188)**.
- 사용자 「응 결과 나오면 커밋하고 마감까지 진행해」 — 커밋·마감 승인. 배달·재기동은 이 승인에 없다.

## 같은 날 정리한 것 (이 일감 밖, 기록용)

- #915(Antigravity 237초 시간 초과)는 #887 의 **중복**이었다 — 등록 전 기존 일감을 찾지 않은 실수(사용자 지적).
  #887 은 #888(11-06 `68f1568` 커밋 리뷰 480초·전체 diff)로 해소돼 닫았다 — 그 뒤 커밋 리뷰 done 24 · 실패 0.
- #884 T7 마감·#885 마감(#897·#912·#907 로 해소)·아이디어 #916(배달 뒤 인수인계 커밋의 1커밋 뒤처짐).

최종 결과는 Redmine 마감 노트.
