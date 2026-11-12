# 현재 AX 작업 인수인계

> 2026-11-12 21:58 Claude 체크포인트 — #932 마감. Codex 00:30 중단 체크포인트를 사용자 지시(「인수인계서 확인해」→「응」)로 인계해 끝냈다.
> 항목·진행과 최종 배달 결과의 정본은 Redmine이다. 구현 `c4a31e2`, 리포트 170 `52992a7`.
> 진행 중 일감 잠금·worktree 없음(#932 finish 응답). 이 문서 커밋 직후 같은 `master.issue_wrapup 932`로 배달·check 예정.
> 이전 상세는 Git `ba9f435`·리포트 159~170·각 일감 노트를 따른다. 마스터는 11-12 21:33:14 부팅.

## 지휘 상태 (실조회)

- 마스터 담당 `claude` — `record_master_conductor` 2026-11-12 21:40:27(사용자 지시로 실제 인수). 기록일 뿐 생존 판정·잠금이 아니다.
- 워커 전역 `codex`(`source=state`, 2026-10-18 선택) 변경 없음. 마스터 지휘 타입은 Claude·Codex만(#829).
- #932 작성 계열은 `codex`+`claude`(인계 때 `issue_start_tool` 이 더했다).

## #932 실제 완료 근거

- 내용: 마감 추적 해시가 등록 30분 뒤에도 미러에 없으면 사유(`mirror_missing`)와 Redmine 노트 1회로 드러낸다.
  해시는 `waiting` 유지, 늦게 도착하면 복구, Git 조회 오류는 부재와 구분. 상세는 리포트 170.
- 검사(Claude 가 11-12 21:48 재실행 — Codex 원본 로그는 재부팅으로 `/tmp` 에서 사라졌다):
  issue_track 106/106 · issue_progress 123/123 · review_runner 133/133, 공식 통합 `Ran 193 tests in 196.344s OK`.
  정적 검사는 다시 돌리지 않았다(Codex 기록: 차단 0).
- 실물 검증(worktree 의 새 코드, 운영 트윈·미러·Redmine, `review_runner --project AXCluster --limit 0`):
  기한 전(00:27, Codex) 알림 0 → 기한 후 21:40:44 「등록 후 77211초 / 1800초」 부재 노트 1건 게시 →
  별도 프로세스 재실행 21:44:03 부재 노트 0. 저장 기록 `waiting`·`mirror_missing.noted=true`, Redmine 알림 노트 1건.
- 검증 회차 1(부재 검증용 식별자 `9320…9320`, 실제 커밋 아님)은 공개 함수로 정식 종결:
  `set_hash(skipped)` → `mark_hash_noted` → `set_summary(abandoned, noted)`. 21:47:13.
- `issue_finish_tool(932, confirm=True)`: `ok=true, closed=true, registered=true, round=2, why=""`,
  `repo=/home/sim/ax-cluster/.ax-issues/932`,
  `done=["push","ff","worktree_remove","delete_branch","register","link","release","close","redmine"]`.
  범위 `ba9f435..52992a7` 커밋 2·파일 7. 실제 마감은 회차 2이고 해시별·종합 리뷰는 큐 결과로 남는다.
- `master.issue_wrapup 932` 1회차 rc2(예정된 인수인계 대기): `ax-task-queue`·`ax-projects` [주의] 의존 변경 →
  oneshot `ax-dispatch` 대기 뒤 재기동(21:33:25 → 21:51:04 / 21:51:09), 재판정 깨끗. `ax-broker` 최신. 배달은 아직 안 했다.
  2회차도 rc2 — 이 문서 쓰기가 거절된 채(읽은 뒤 fast-forward 로 파일이 바뀜) 호출해 「인수인계 대기」 노트가 한 번 더 붙었다.
- **한계**: systemd 타이머가 main 에 반영된 새 코드로 부재 알림을 내는 것은 따로 실증하지 않았다(같은 진입점을 worktree 에서 실행).
  Redmine 전송 성공과 표시 저장 사이 crash 는 중복 가능(리포트 170).

## 이번에 확인한 사실 — 기록과 달랐던 것

- `--limit 0` 은 「LLM 호출 0」이 아니다. `drain` 이 `max(1, limit)` 이라 대기 항목이 있으면 1건 처리한다(기존 동작, #932 변경 아님).
  이번 두 실행이 #829 의 해시 리뷰 `6c30a9d`(R328, 지적 0)와 종합 리뷰(R329)를 1건씩 처리했다. 타이머가 처리할 항목이었고
  21:43 타이머 회차는 소비자 잠금으로 건너뛰었다. 고칠지는 사용자 결정 — 일감 미등록.
- Codex 가 준비한 `/tmp/ax-932-*` 스크립트·로그는 21:33 재부팅으로 없어져 쓰지 않았다. 명령은 문서에 적힌 원문과 공개 함수로 대신했다.
- Codex 체크포인트 문서는 마감의 깨끗한 main 조건 때문에 커밋하지 않고 이 문서로 대체했다(내용은 위에 반영).

## 기존 마감·미확인 보존

- #829 완료·배달까지 끝남(구현 `6c30a9d`·리포트 `30819dd`). wrapup 829 재실행·중복 마감 금지.
  실제 Argon 호출·CLI 완전 격리·서브 authors 자동 등록은 미실증/미구현. R328·R329 본문은 읽지 않았다.
- #934 리포트 168, #931 리포트 167, #933 리포트 166, #930 리포트 165 완료. `.33` 첫 실제 요청자 마감·연결은 미확인.
- #929 추적 기록(실재하지 않는 끝 해시 `eb78e03f5ad0…`)은 복구하지 않았다 — 사용자 결정 대기. 새 코드가 main 에 올라갔으므로
  다음 리뷰 큐 회차에서 #929 에 부재 알림 노트가 1회 붙을 수 있다(설계된 동작, 이번에 관측하지 않았다).
- #929 R317·#930 R315/R316·#931 R325·#934 R326/종합 리뷰는 재검토하지 않았다.
- 실제 BC-250 poweroff 미실행. M8 open/M7 closed, 자동 로드 문서의 「M7 open」 서술 미정리, #927 새 세션 권한 확인은 범위 밖.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.

## 바로 다음 작업

1. 이 문서 커밋·push 뒤 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.issue_wrapup 932 --project AXCluster`로
   배달·check 를 끝내고 T3 완료 근거와 배포 결과를 Redmine 에 남긴다. 최종 결과는 Redmine 노트가 정본이다.
2. 다음 일감은 사용자가 선택한다. 자동 시작하지 않는다.
3. #929 추적 기록 복구 여부, `--limit 0` 동작, 누적된 리뷰 지적(#929~#934·#829·#932) 처리 범위는 사용자와 정한다.
4. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.
