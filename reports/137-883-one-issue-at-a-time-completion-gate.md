# 137 — 일감 단위 작업 강제: 한 번에 한 일감 · 완료 게이트 (#883 · 부모 #826)

날짜: 2026-11-04 · 담당 Claude(마스터) · [#883](http://192.168.0.57:8080/issues/883) · 부모 [#826](http://192.168.0.57:8080/issues/826) · 앞 보고 [136](136-879-issue-branch-range-review.md)
기준 리비전 `bd10209` → `58562c1`(마감, push) · 범위 리뷰 R223(지적 0) · #883 완료 · 워커 배달 3/3
후속 등록: #884(.33 언리얼 경로) · #885(service_freshness 오판)

## 한 줄 결론

사용자 규칙 4개(한 번에 한 일감 · 마감 시 자동 리뷰 · 리뷰 상태 등록 · 높음 지적 판정 전 완료 불가)가
**코드로** 강제된다. #883 자신으로 한 바퀴 돌렸다 — 다른 일감 전이 거절, 리뷰 대기 중 「완료」 거절(PUT 0),
리뷰 뒤 통과·잠금 해제까지 실경로로 확인했다. 높음 지적이 실제로 남은 경우의 거절만 단위 검사뿐이다.

## 1. 사용자 결정 (2026-11-04)

| 갈림길 | 결정 |
|---|---|
| 막을 「다른 작업」 | 다른 일감의 `issue_start`·플랜 「작업중」 전이만 (일감 없는 커밋은 막지 않음) |
| 완료를 막는 심각도 | 높음만 |
| 우회 차단 자리 | `redmine.update_issue` 공용 함수 (MCP·8101·스킬 모두 통과) |
| 진행 방식 | 로컬 서브에이전트 (T1·T3 병렬, T2·T4 뒤이어, T5 직접) |
| 기본값(제시·수락) | 잠금은 인프라 프로젝트별 상태 파일 · 보류=잠금 해제·브랜치 유지 · 재개=`issue_start` · 취소 브랜치 삭제는 별도 승인 · 판정 대상은 그 일감의 범위 리뷰만 · 리뷰 미완·실패·포기면 완료 거절 · 잠금은 마감 뒤 「완료」까지 유지 · `.33` 경로 후속 |
| 작업 중 결정 | `test_dismissal_candidates` 82행에 반려 사유 추가 · 「작업중」 잠금 검사는 모든 일감(Redmine 조회에 project 없음) · `plan_events` 에 `lock_busy` 분류 |

## 2. 무엇이 생겼나

| 태스크 | 커밋 | 내용 |
|---|---|---|
| T1 | `4de7a0d` | `master/issue_lock.py` — `<트윈>/issue_lock.json`(schema 1, active 1칸 + paused) · flock · 원자 교체 · 깨진 파일은 `IssueLockError`(덮어쓰지 않음) |
| T3 | `4de7a0d` | `master/context_synth/issue_review.py` `issue_review_status` — 범위 리뷰 none·pending·failed·abandoned·done(최신 항목) + 미판정 높음(open·accepted·failed) → `ok_to_complete`·`why` · `fix_index.set_status` dismissed 사유 필수 |
| T2 | `c9274b3` | `issue_flow` start 잠금·재개 · `pause` · `cancel(confirm, delete_branch)` · finish 는 보류·타 활성이면 거절, 잠금 유지 · `plan_tools.transition` 「작업중」 잠금 검사 |
| T4 | `97b9f69` | `redmine.update_issue(completion_gate=)` — 닫힘(이름 「완료」 또는 `is_closed`)일 때만, 추적 일감만 · 막으면 PUT 0 · 판정 불가는 거절 · 통과 뒤 잠금 해제 |
| T5 | `58562c1` | MCP `issue_pause_tool`·`issue_cancel_tool`(45종) · 8101 `/redmine/note` `warn` · `ax-plan` §3-2 |

검사: 전수 `master/test_*.py` 206파일 9997/9997 · 통합 187 OK.

## 3. 실경로 (#883 자신)

| 단계 | 결과 |
|---|---|
| ① `issue_start(883)` (재기동 뒤) | 이미 `issue/883` — 잠금 `acquired` (#883 은 잠금 코드 이전에 시작했다) |
| ② `#882` T1 「작업중」 전이 | `#883 작업이 진행 중이다 …` 거절 · #882 노트·수정 시각 그대로(쓰기 0) |
| ②′ `issue_start(882)` | 플랜 판정(`plan_needed`)이 먼저 거절 — 판정 순서 플랜 → 잠금. 잠금 거절 경로는 단위 검사 |
| ③ `issue_finish` 미리보기 → 승인 → confirm | push `58562c1` · ff · 브랜치 삭제 · range 등재 · 노트 · 잠금 유지 로그 |
| ④ 리뷰 대기 중 `redmine_note(status=완료)` | `ok:false` 「완료 거절 — 범위 리뷰 … pending」 · Redmine 마지막 노트가 「리뷰 요청」(PUT 0 확인) |
| ⑤ 리뷰 R223 (1회 시도, 지적 0) → 「완료」 | 통과 · `… · 잠금 해제` · `warn:false` · `issue_lock.json` active·paused 빔, 이력 `complete by redmine.update_issue` |

미실증: 높음 지적이 남은 실경로 거절(단위 검사 completion_gate 47 · issue_review 26 만) · 미러 지연 WAIT(이번엔 미러가 제때 받았다).

## 4. 알게 된 것

- **배달 검사 오판(#885 등록)**: 마감 직후 `master.client update` 가 「서비스 2개 옛 코드로 돈다」로 rc=1.
  서비스는 `58562c1` 내용으로 23:14 기동했고, `issue_finish` 의 `switch main`(23:30:15) → `ff`(23:30:16) 가
  내용은 되돌리고 mtime 만 바꿨다. `service_freshness._newest` 가 mtime 비교라 생긴다 — 매 마감마다 재현된다.
  같은 내용 재기동(23:41, 승인) 뒤 `check` rc=0.
- **서브에이전트 산출물 확인**: 네 번 모두 테스트를 마스터에서 다시 돌리고 코드를 읽었다. T3 은 대상 밖
  검사 1건을 깨뜨렸고(사유 없는 반려), 고치지 않고 보고됐다 → 사용자 결정으로 한 줄 수정.
- **#883 본문에 `## 플랜` 제목이 두 번** — 본문 끝의 빈 「## 플랜」 아래에 `plan_set` 이 제목을 하나 더 넣었다.
  판정에는 영향이 없다(미등록 · 표시 문제).
- **서비스는 체크아웃 코드로 돈다** — 이번엔 T5 커밋 뒤 `issue/883` 에서 재기동해 실경로를 돌렸다. 마감 뒤
  `main` 이 같은 커밋이라 문제가 없었지만, 브랜치에서 재기동한 서비스는 main 에 없는 코드를 돌린다.

## 5. 남은 것

- #884 — `.33` 언리얼 경로(시작=브랜치/worktree, 8101 표면, 프로젝트별 잠금·게이트 루트)
- #885 — service_freshness mtime 오판
- #882 — 범위 리뷰 실패·포기·대기 노트(이번 게이트는 그 상태를 막기만 한다 — 노트로 알리는 것은 #882)
- `## 플랜` 제목 중복(미등록)
