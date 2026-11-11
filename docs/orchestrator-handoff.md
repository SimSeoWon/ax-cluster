# 현재 AX 작업 인수인계

> 2026-11-12 00:07 Codex 체크포인트 — #829 마감·Antigravity 마스터 지휘 타입 폐기.
> 항목·진행과 최종 배달 결과의 정본은 Redmine이다. 구현 `6c30a9d`, 리포트 169 `30819dd`.
> 진행 중 일감 잠금·worktree 없음(#829 finish 응답). 이 문서 커밋 직후 같은 `master.issue_wrapup 829`로 배달·check 예정.
> 이전 상세는 Git `9967957`·리포트 159~169·각 일감 노트를 따른다. 마스터는 11-11 21:57:03 부팅(이전 기록).

## 현재 지휘 계약 — #829 사용자 결정

- **마스터 지휘 LLM 타입은 Claude·Codex만.** `antigravity`/`agy` 마스터 타입을 코어·MCP enum·CLI·WebUI에서 제거했다.
  Antigravity 연결의 운영 `issue_start`는 worktree·잠금·Git·Redmine 준비 전에 거절한다. MCP clientInfo를 신뢰하는 기존 계약이며 인증 경계는 아니다.
- **Gemini 4 Argon은 범위를 지정한 서브 작업에만 허용.** 자료 사본·허용 파일·완료 조건을 전달하고 결과를 지휘자가 검증한다.
  전역 설정·공용 지침·MCP 운영·일감 시작/마감·배포를 독자적으로 실행하지 않는다.
- 기존 `ax-gemini` §4-1의 `master.work.gemini_report --task implementation --model gemini-4-argon-medium --allow-argon`으로
  패치 제안을 회수한다. 기본 research·한도 시 Flash High 폴백·자동 Argon 금지는 유지한다.
- 구현 모드는 승인 우회 대신 `--sandbox --disable-slash-commands --mode plan`. **실제 Argon 호출과 CLI 완전 격리는 미실증**이다.
  MCP·명령 금지는 지침 수준이다. 서브 패치 회수는 `authors`를 자동 등록하지 않으므로 반영 시 작성 사실·타 계열 검증을 남긴다.
- 과거 `agy` 작성 계열·리뷰·세션 수집·기존 자동 Flash는 보존했다. 지휘 타입과 하위 작성/리뷰 모델은 다르다.
- 기존 담당 파일은 보존했다. 재기동 뒤 MCP 실조회: `master.agent=unknown, retired_agent=antigravity`.
  **새 담당을 자동 기록하지 않았다.** 워커 전역 `codex`(`source=state`, 2026-10-18 선택)는 변경하지 않았다.

## #829 실제 완료 근거와 후속

- 사용자: 「829번 진행해」 → 로컬 서브에이전트 방식 → Antigravity LLM 타입 제거·Argon 서브 활용 허용.
  자동 로드 문구는 사전 제시 후 진행 승인 범위에서 반영했다.
- 시작 응답 `repo=/home/sim/ax-cluster/.ax-issues/829`, `checkout=/home/sim/ax-cluster`,
  `start_rev=996795757a9129ea07a2c437738713b437b5b1e6`, author `codex`.
- 핵심 회귀 **633건**(30+189+56+358), 공식 통합 **193/193 (193.440s)**, 정적 검사 12파일 차단0.
  `test_gemini_report` 122/122 포함. 명령·rc·세션 파일·미확인은 리포트 169.
- 구현 `6c30a9dfc7acdc47174cb7b4458552d8e91cad5f`, 리포트 `30819dd439b3c63eb2dbca251d2cdc11e03002ef`.
- `issue_finish_tool(829, confirm=True)`: `ok=true, closed=true, registered=true, round=1, why=""`,
  `repo=/home/sim/ax-cluster/.ax-issues/829`,
  `done=["push","ff","worktree_remove","delete_branch","register","link","release","close","redmine"]`.
  main 반영·worktree/브랜치 제거·잠금 해제·Redmine 완료100. 해시별/종합 리뷰는 이후 큐 결과로 남는다.
- `master.issue_wrapup 829` 1회차: `ax-projects`만 옛 코드로 판정, 기다릴 oneshot 없음.
  **11-11 23:24:48 → 11-12 00:06:11 KST**, active·재판정 깨끗. broker·task-queue는 최신으로 재기동하지 않았다.
  **rc2는 예정된 인수인계 커밋 대기**이며 배달하지 않았다. 이 문서 커밋·push 뒤 같은 명령으로 배달한다.
- 재기동 뒤 `get_orchestration_tool` 실조회에서 폐기된 담당 표시와 워커 codex 유지 확인.
- `/tmp` 전체 로그 경로 조회 rc2(Permission denied)로 중단했으나, 사용자 「응!」으로 기록·재개 승인.
  코드 검사 실패와 구분했다. 초기 회귀 합계 673 표기는 산술 오기로 633으로 정정했다.
- 지연의 「기하급수」 증가·내부 원인은 재측정하지 않았다. 이번 작업에서 속도 개선을 주장하지 않는다.
- 세션: `~/.codex/sessions/2026/11/11/rollout-2026-11-11T23-49-01-01a1cb15-6c15-73b0-895f-c9ad856cd447.jsonl`.

## 기존 마감·미확인 보존

- #934 `40b5fd9`: #933 R318~R322 정리, 리포트168. applied10/dismissed10은 이전 기록이며 이번에 내용 재대조하지 않았다.
- #931 `c22af56`: requester=master의 ax-client 시작/마감/보류/취소 거절. plan_* 유지.
  .33 실제 요청자 통과와 MCP 경유 1회는 이전 미확인으로 남는다. 리포트167.
- #933 `d1f5ae0`: 마감 해시를 git에서 도출·Gitea로 대조. .33 첫 마감 `[git]` 여부 미확인. 리포트166.
- #930 `14b3273`: 테스트의 실제 Claude 설정 오염 차단·복구. 통합 HOME 격리는 합의로 제외, 다른 테스트 홈 쓰기는 여전히 한계.
  실행 중인 Claude 세션은 필요 시 /mcp 재연결. 리포트165.
- #929 `eb78e03`·#702 `c1b2537`: BC-250 종료 안전성 보강. 실제 poweroff는 아직 실행하지 않았다는 이전 기록을 유지한다.
  SSH rc255 종료 판정은 가설·미측정이다. 리포트163~164.
- #929 회차2: R314 → Codex R317(중간2·낮음3). 이전 기록상 지적 미처리.
  #930 R315·R316, #931 R325, #934 R326/종합 리뷰는 최신 상태·본문을 이번에 재조회하지 않았다.
- 마일스톤8 open·M7 closed. 자동 로드 문서의 오래된 「M7 open」와 M8 문서 부재는 이번 범위 밖.
- #927 전체 도구 승인 정책과 새 Claude 대화형 세션 연결 확인은 별도 미확인으로 남는다.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음. #934 이전 완료 작업 중복 마감 금지.

## 바로 다음 작업

1. 이 문서 커밋·push 뒤 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.issue_wrapup 829 --project AXCluster`로 배달·check를 끝내고 T3 완료 근거와 Redmine 배포 노트를 남긴다. 최종 결과는 Redmine 노트가 정본이다.
2. 다음 일감은 사용자가 선택한다. 후보 #932·아이디어 #908/#911/#914/#919·세션 보강 #741. 자동 시작하지 않는다.
3. #929/#930/#931/#934 및 #829 리뷰 결과를 실제 코드와 대조하고 처리 범위는 사용자와 정한다.
4. 실제 Argon 서브 위임을 쓸 때 CLI 격리·패치 응답·작성 계열 기록 한계를 확인한다. 완전 격리가 입증된 것으로 다루지 않는다.
5. .33 첫 요청자 마감과 새 Claude 연결·권한 정책의 미확인을 유지한다.
6. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 추가 변경은 기존 사람 게이트를 따른다.
