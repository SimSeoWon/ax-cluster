# 현재 AX 작업 인수인계

> 2026-11-12 22:42 Claude 체크포인트 — #639 마감(범위 플랜 `kind=scope`). 같은 세션에서 앞서 #932 마감·#633 종결.
> 항목·진행과 최종 배달 결과의 정본은 Redmine이다. #639 구현 `8331dac`, 리포트 171 `2464f71`.
> 진행 중 일감 잠금·worktree 없음(#639 finish 응답). 이 문서 커밋 직후 같은 `master.issue_wrapup 639`로 배달·check 예정.
> 이전 상세는 Git `efa0264`·리포트 159~171·각 일감 노트를 따른다. 마스터는 11-12 21:33:14 부팅.

## 지휘 상태 (실조회)

- 마스터 담당 `claude` — `record_master_conductor` 2026-11-12 21:40:27(사용자 지시로 실제 인수). 기록일 뿐 생존 판정·잠금이 아니다.
- 워커 전역 `codex`(`source=state`, 2026-10-18 선택) 변경 없음. 마스터 지휘 타입은 Claude·Codex만(#829).

## #639 실제 완료 근거 — 범위 플랜

- 사용자: 「이번에 진행하자」 → 결정 넷(빠진 리뷰는 파일의 마지막 커밋을 `kind=commit` 으로 채움 · 입구는 마스터 CLI + MCP ·
  `plans/_scope/` 저장·Redmine 미등록 · 로컬 서브에이전트) → 실물 뒤 「기준 유지」 → 「1번으로 마감해」(플랜 생성 구간 실물 미확인을 한계로).
- 내용: 소비자가 `kind=scope` 를 `scope_plan.run_scope` 로 처리한다. 범위 해석 → 미등재 커밋 리뷰 등재 → WAIT(상한 12) →
  범위 안 지적으로 기존 `group_issues`·`generate_improvement_plans` → `plans/_scope/<slug>/<회차>/`. 지적이 있는데 플랜 0건이면 「플랜 기준 미달」을 남긴다.
  입구: `python -m master.context_synth.scope_plan request <대상>` · `ax-projects:request_scope_plan_tool`(마운트된 프로젝트만).
- 검사: test_scope_plan 100/100, test_review_runner 134/134, test_review_range 75/75, test_review_queue 65/65, test_planner 67/67,
  test_issue_progress 123/123, test_fix_index 52/52, test_mcp_servers 통과 57, 공식 통합 `Ran 194 tests in 191.218s OK`.
- 실물(`master/broker`, worktree 코드·운영 큐): 등재 → 미등재 2건 리뷰 채움(R332·R333) → WAIT 1/12 → 재개 → 지적 3건(low 2·mid 1) → 플랜 0건 → done.
  **상용 모델의 플랜 생성 호출은 실물로 확인되지 않았다**(기준 미달이라 호출이 없었다 · 주입 검사 근거뿐).
  그 실물의 `_summary.md` 는 수정 전 코드가 써서 `status: 완료` 다.
- 읽기 전용 조사: 현재 덮인 리뷰 기준으로 저장소 전체에서 파일별 기준(고위험 1+ 또는 중위험 3+)을 넘는 파일이 없다.
  패턴 플랜은 `master` 전체 범위에서만 나오고 그 범위는 미등재 커밋 68건이 먼저다. 지금 데이터에서는 범위 요청 대부분이 「기준 미달」로 끝난다.
- `issue_finish_tool(639, confirm=True)`: `ok=true, closed=true, registered=true, round=1, why=""`,
  `repo=/home/sim/ax-cluster/.ax-issues/639`,
  `done=["push","ff","worktree_remove","delete_branch","register","link","release","close","redmine"]`.
  범위 `efa0264..2464f71` 커밋 2·파일 10. 작성 계열 `claude` — 해시별·종합 리뷰는 큐 결과로 남는다.
- `master.issue_wrapup 639` 1회차 rc2(예정된 인수인계 대기): `ax-task-queue` [주의] 의존 변경·`ax-projects` [중요] 옛 코드 →
  oneshot `ax-dispatch` 대기 뒤 재기동(21:51:04 → 22:38:24 / 21:51:09 → 22:38:29), 재판정 깨끗. `ax-broker` 최신. 배달은 아직 안 했다.
- 한계·열린 것은 리포트 171 §8(대기 상한 · done 대상 재요청 불가 · 마지막 커밋 리뷰만 원료 · 큰 커밋 · 게시판 미노출 등).
  MCP 도구는 재기동 뒤 노출됐으나 실제 호출은 하지 않았다. 타이머가 배포 코드로 scope 항목을 도는 것도 보지 않았다.

## 같은 세션의 다른 변경

- #932 완료·배달(구현 `c4a31e2`·리포트 170 `52992a7`·인수인계 `bbd28fe`). 기한 후 부재 노트 1건·재실행 중복 0 실물 확인,
  검증 회차 1 정식 종결, 실제 마감은 회차 2. 타이머+배포 코드의 부재 알림은 따로 실증하지 않았다. 상세는 #932 노트.
- #633(리뷰 큐 부모) **완료로 종결**, #639 는 부모에서 떼어 독립 일감으로 둔 뒤 진행(사용자 결정 2026-11-12).
- 인수인계 정정 `efa0264`: #929 추적 기록은 이미 복구돼 있었다(회차 1 `skipped`/`abandoned`, 회차 2 R314 지적 5·종합 R317).
  #932 본문의 「복구 — 사용자 결정 대기」는 낡은 서술이다. 남은 것은 R314·R317 지적 처리.
- `--limit 0` 은 「LLM 호출 0」이 아니다 — `drain` 이 `max(1, limit)` 이라 대기 항목 1건을 처리한다(기존 동작). 고칠지는 사용자 결정, 일감 미등록.
- `.2` check 에 「홈 중복 스킬 1개 `~/.agents/skills/ax-work`」 주의가 뜬다(통과 판정 · 건드리지 않았다).

## 기존 마감·미확인 보존

- #829 완료·배달까지 끝남(구현 `6c30a9d`·리포트 `30819dd`). 해시 리뷰 R328(지적 0)·종합 R329 가 붙었다(본문은 읽지 않았다).
  실제 Argon 호출·CLI 완전 격리·서브 authors 자동 등록은 미실증/미구현.
- #934 리포트 168, #931 리포트 167, #933 리포트 166, #930 리포트 165 완료. `.33` 첫 실제 요청자 마감·연결은 미확인.
- #929 R314/R317·#930 R315/R316·#931 R325·#934 R326/종합 리뷰는 재검토하지 않았다.
- 실제 BC-250 poweroff 미실행. M8 open/M7 closed, 자동 로드 문서의 「M7 open」 서술 미정리, #927 새 세션 권한 확인은 범위 밖.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.

## 바로 다음 작업

1. 이 문서 커밋·push 뒤 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.issue_wrapup 639 --project AXCluster`로
   배달·check 를 끝내고 T4 완료 근거를 Redmine 에 남긴다. 최종 결과는 Redmine 노트가 정본이다.
2. 다음 일감은 사용자가 선택한다. 자동 시작하지 않는다.
3. `--limit 0` 동작, 범위 플랜의 열린 것(리포트 171 §8), 누적된 리뷰 지적(#929~#934·#829·#932·#639) 처리 범위는 사용자와 정한다.
4. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.
