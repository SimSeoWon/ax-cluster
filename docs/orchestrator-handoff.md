# 현재 AX 작업 인수인계

> 2026-11-11 02:50 Claude 체크포인트(#933 마감 `d1f5ae0` — 마감 해시를 도구가 git 에서 구하고 서버가 검증) · 02:50 보강(배달 결과·리뷰 진행). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `da43835`·`513d5d2`·`1c65dcf`·`2570af6`·`c1b2537`·`eb78e03`·`14b3273`·`d1f5ae0`·리포트 159~166·각 일감 노트에 있다.
> 진행 중인 일감·잠금 없음. 🔴 **배달 미완료**: `.33`·`.43` 이 꺼져 있다(사용자 확인 11-11). #933 마감 배달(`36c3219` 기준)은 `.2` 만 통과하고 두 대는 실패(`issue_wrapup` rc 1) — 이 문서 커밋으로 `.2` 도 한 커밋 뒤처진다. 두 대가 켜지면 `master.client update` 를 한 번 돌리면 세 대가 맞춰진다(사용자가 나중에 하기로 함). 꺼진 기계는 `update` 가 「클론 실패」, `check` 가 「체크아웃 없음」으로 표시한다. 새 `ax-issue` 스킬·`client_mcp.py` 는 그때 `.33` 에 닿는다.

## 🔴 오늘 바뀐 규칙 (사용자 결정 2026-11-08 ~ 11-10)

- 🔴 **일감 「진행해」 = 끝까지 승인**(`docs/orchestrator-rules.md` §1.9 · `ax-plan` §3-1): 구현 → 검사+공식 통합 → 리포트 → 커밋 →
  `issue_finish(confirm=True)` → 신선도 판정된 서비스만 재기동(oneshot 확인) → **인수인계서 커밋·push → 마지막에 배달·check rc0**.
  멈추는 자리(실패·대상 밖·설계 갈림길·파괴적 git·⑦/finalize·자동 로드 문서)는 그대로.
- 🔴 **Antigravity 진입 및 상호작용 규칙**(#920 · #928 · 사용자 결정 2026-11-10): 시작 폴더 지침만 자동 로드하므로 홈 `~/GEMINI.md` 가
  작업 루트의 `AGENTS.md` 를 먼저 읽고 AX-ENTRY-MARK 보고. **도구 승인 팝업 방지**는 `accept-edits` 모드로 자동 수락하여 한 호흡에 완결.
  상호작용 타이밍은 **① 일 시작할 때(착수)**, **② 일 끝났을 때(완료/판단)**, **③ 에러/예외 발생 시(고지 및 답변 요구)** 3회로 고정.
- 🔴 **지휘자 셋 · 교차 계열 리뷰**(#920 · #926): 운영 일감 시작은 `ax-projects:issue_start_tool` 만 된다. MCP `clientInfo` 가 작성 계열이 되고,
  Antigravity 작성분은 Codex 단독 리뷰·실패 시 폴백 없음, 그 밖은 agy. 명시 Argon 호출만 한도 시 Flash High 폴백.
- **마감 뒤 기록 몫**(`ax-plan` 3-1): 리포트=일감 커밋 시점까지 · Redmine 마감 노트=결과 정본 · **이 문서=마감 직후 main 문서 커밋**.
- **세 CLI 전체 도구 허용**(#927 사용자 결정): Claude `permissions.defaultMode=bypassPermissions`, Codex 두 AX MCP 기본 approve 및 실제 도구 전수 승인.
  Antigravity 기존 전체 allow 보존. 스킬은 사용하는 도구 권한을 따른다. Codex sandbox·OS 권한과 작업 범위·사람 게이트는 별도다.
- 🔴 **이 문서의 절 제목 「바로 다음 작업」은 바꾸지 않는다** — `test_handoff_size` 가 `^#{2,3}\s*바로 다음 작업` 으로 판정.

## #933 마감 (2026-11-11) — 마감 해시를 도구가 git 에서 구하고 서버가 git 으로 검증

- **서버**: `infra_finish` 가 등록 전에 프로젝트의 Gitea 저장소(`track.bare_path`, 읽기)에서 `end`·`base` 실재·조상 관계·`main` 도달을 확인하고 `base..end` 해시·제목을 git 에서 구한다. 틀리면 `step: verify`(`mismatch`/`lookup`)로 거절 — 잠금·추적·Redmine 무변경. `base` 생략 = 잠금의 시작 리비전, `check_only` = 쓰기 0.
- **도구**: `ax-client:issue_finish` 는 일감 번호만 받는다. 끝 해시는 체크아웃 git 의 `issue/<N>` 에서 읽고, 인자 `end` 가 다르면 서버로 보내기 전에 거절한다. `ax-issue` 스킬 마감 절차도 「번호만 넘긴다」로 바꿨다(배달 대상).
- **검증**: `test_issue_infra` 93 · `test_tagging` 232 · `test_client_mcp` 356 · 공식 통합 193/193 · 변이 3종 FAIL 확인. 전수 219개 중 `test_sandbox` 1개는 전수 실행에 `AX_PROJECTS_ROOT` 를 안 준 탓(지정 시 44/44). 재기동 뒤 실제 8101 에서 없는 해시 거절·`check_only` 도출·도구 거절을 확인했다(쓰기 0).
- **남은 한계**: 게임 요청자(`.33`) 세션의 실제 마감 1회는 미확인(꺼져 있었다) — Windows 체크아웃에서 첫 마감 때 `[git]` 오류 여부를 본다. 머지로 시작점이 달라진 범위와 인자로 싣는 `base` 는 코드가 다 막지 못한다. 시작·보류·취소의 해시 인자는 범위 밖(사용자 결정). 리포트 166.

## #929 리뷰 정지 — 없는 해시 등록 (2026-11-11, 코드 변경 없음)

- **증상**: #929 해시 리뷰가 11-10 00:50 등록 뒤 하루 넘게 「미러에 아직 없다 — waiting 유지」만 반복했다. 일감·사람에게 신호가 없었다.
- **원인(확인)**: Antigravity 세션 `90aa65d9` 스텝 256 이 `ax-client:issue_finish` 의 `end`·`hashes` 에 `eb78e03f5ad0…` 를 넘겼다. 실제 커밋은 `eb78e0364330…` 다(앞 7자만 같다). 세션 기록에 실제 전체 해시는 0회 나온다 — 짧은 해시만 보고 40자리를 채웠다. `infra_finish`(`master/issue_infra.py:487`)는 설계상 형식만 검사하고, `issue_progress.py:183` 은 부재를 지연으로만 본다.
- **등록**: [#932](http://192.168.0.57:8080/issues/932)(신규, 미착수) — 추적 해시가 미러에 기한 넘게 없으면 일감에 드러낸다. 등록 쪽은 #931 이 AXCluster 에서 막는다(근거 노트 추가). 정규 경로 `issue_flow.finish` 는 해시를 git 에서 구한다. #829 에 여섯 번째 사례로 코멘트.
- **#929 추적 정정(사용자 승인)**: `issue_track` 함수로 회차 1 을 종결(해시 `skipped` · 종합 `abandoned`)하고, 미러에서 구한 실제 해시로 **회차 2** 를 등록했다. 작성 계열은 `agy` 로 기록(사용자 결정 — 종합 리뷰를 Codex 가 본다). 파일 손 편집 없음. #929 에 정정 노트.
- 등록 쪽 차단은 #933 으로 끝났다(위 절). #932 는 그래도 들어온 경우의 마지막 방어로 남는다.
- 실제 커밋의 해시 리뷰 R314(11-10 01:08)는 검증 모델이 Antigravity 였다(당시 `authors` 빈 값, 같은 계열).
- #930 은 R315(낮음 1)·종합 R316 까지 끝났다(11-11 01:52).

## #829 위임 분석 · #931 등록 (2026-11-10, 코드 변경 없음)

- **#829 코멘트(Claude)**: Gemini/Antigravity 는 구현·일감 진행은 맡길 수 있고, 단독 마스터 지휘(검증 판정·마감)는 아직 권하지 않는다. **의견이며 운용 변경 승인이 아니다.** 비교군이 없어 모델 계열 우열은 판단하지 않았다.
- **기록으로 확인한 것**: #929 세션(`90aa65d9`)이 `--check` `rc=1 · FAIL 9/13` 을 보고하지 않고 넘어갔다(worktree 실행이라 오염 증거로는 구분 안 됨). #702·#929 는 `ax-client` 경로와 손 merge·push 로 진행해 `authors` 가 비었고 `issue_wrapup` 을 건너뛰었다. #702 R312·R313 은 같은 계열(Antigravity)이 리뷰했다. #926 은 Codex 리뷰가 생략됐는데 「통과」로 적었다(실제 게시 증거는 #928 R308).
- **[#931](http://192.168.0.57:8080/issues/931)(신규, 미착수)**: `requester: master` 프로젝트의 `ax-client:issue_start`·`issue_finish` 거절. 착수 때 `pause`·`cancel`·`plan_*` 포함 여부와 이미 잡힌 잠금 처리를 정한다. 원인 대조는 grep 수준이라 착수 때 다시 확인한다.
- **미결정 제안**: `authors` 가 빌 때 처리, 플랜 검증 rc 를 완료 근거로 요구(#908), 마감 전 운영 체크아웃 `--check`, #702·#929 교차 재리뷰 — #829·#931 본문 참고.

## #930 마감 (#929 테스트가 실제 `~/.claude.json` 의 `ax-client` 를 덮어쓰던 결함)

- **결함**: `test_claude_skills_sync_and_check` 가 대역 없이 `apply` 를 불러 진짜 `claude mcp` 가 실제 설정을 임시 경로로 덮어썼다. Claude 세션의 `ax-client` 가 `CONNECTION_CLOSED` 로 끊겼다. #929 마감 기록은 이 FAIL 을 놓쳤다.
- **수정**: `apply` 가 CLI 의 실제 설정 파일이 아니면 호출을 거절한다. 문제 테스트에 대역을 넣고, 테스트 전후 실제 세 CLI 의 `ax-client` 설정 불변을 검사한다.
- **복구·검증**: `master-local --apply` 로 복구, `--check` 13/13. `test_client_master_local` 121/121, 공식 통합 193/193, 변이 2종 FAIL 확인, 새 프로세스 `claude mcp list` 에서 Connected.
- **남은 위험**: 통합 러너 `HOME` 격리는 사용자 합의로 뺐다. 다른 모듈 테스트가 실제 홈을 건드리는 경우는 막지 못한다. 실행 중인 세션은 복구 뒤 `/mcp` 재연결이 필요하다.

## #929 마감 (#702 후속 BC-250 종료 점검 fail-open 차단·단절 판정 강화 및 누락 방지 자동화)

- **사전 점검 fail-open 차단**: `tasks=None` 또는 `endpoints=None` 시 `PreflightCheckError` 발생. worker 식별 시 단어 경계(`(?:^|\D)43(?:\D|$)`) 적용으로 `worker-143` 오탐 차단 방지. 원격 SSH 명령 끝의 `|| true` 제거 및 pgrep rc>1/stderr/SSH 실패 시 fail-closed 차단.
- **전원 단절 판정 강화**: SSH 1회 실패 조기 차단 방지. Ping(`ping -c 1 -W 1`)과 SSH probe 병행 및 연속 실패(>=2) 시에만 단절 판정.
- **Claude 스킬 링크 및 자동화**: `~/.claude/skills/ax-bc250-shutdown` 심볼릭 링크 연결. `master-local --check`에 `master/skills/*` ↔ `~/.claude/skills` 대조 검사 추가 및 `master-local --apply` 시 자동 링크 생성 지원.
- **공식 통합 검사 등록 및 누락 방지 자동화**: `tests/integration/checks.json`에 `test_bc250_shutdown` 등록. 신규 검사 `master/test_integration_coverage.py` 추가하여 `checks.json` 누락 테스트 발생 시 즉시 실패 차단 (공식 통합 검사 191 → 193종 확장).
- **문서 보완**: `SKILL.md` 내 `issue_cancel` 오안내 정정, 물리 전원 재가동 필수 명시, `--force` 실제 우회 범위 명시. `CLAUDE.md`/`AGENTS.md` 1줄 보완.
- **검증 및 마감**: 단위/계약 테스트 35/35 통과, `test_client_master_local` 113/113 통과, 공식 통합 검사 **193/193 전수 통과**(`Ran 193 tests in 184.061s, OK`), 커밋 `eb78e03` → `issue_finish` 완료, 배달(`master.client update`) 3대 완료. 정규 마감 경로가 아니었다(위 #829 참고).

## 오늘 완료한 일감 (2026-11-08 ~ 11-11)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #933 | 마감 해시를 도구가 git 에서 구하고 서버가 Gitea 로 검증 — 리포트 166 | `d1f5ae0` |
| #930 | #929 테스트의 실제 Claude 설정 오염 차단 — 리포트 165 | `14b3273` |
| #929 | #702 후속 BC-250 종료 점검 fail-open 차단 및 단절 판정 강화, 누락 방지 자동화 — 리포트 164 | `eb78e03` |
| #702 | BC-250 안전 종료 스킬 — .43 대상 고정·사전 점검 3종·poweroff·단절 확인 — 리포트 163 | `c1b2537` |
| #927 | 전체 도구 승인 정책·생성기 일치, 기존 승인 보존·실제 설정 적용 — 리포트 162 | `2570af6` |
| #928 | Antigravity 툴 권한 allowlist 일괄 등록 및 master-local 정비 — 리포트 161 | `1c65dcf` |
| #926 | Antigravity 지휘 통합 실증 (ax-projects 시작·Argon 위임·Codex 리뷰) — 리포트 160 | `513d5d2` |
| #920 | 지휘자 셋 — 작성 계열 신호 · 리뷰 큐 분기 · Argon 폴백 · Antigravity `ax-projects` 연결 — 리포트 159 | `da43835` |
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 | `54b5632` |
| #921~#925 | 마감 일원화·wrapup 방어·담당 기록·실증 정비 — 리포트 154~158 | `aea3f94` 외 |
| #820·#882 | 범위 밖 감지 게이트·범위 리뷰 재시도 노트 — 리포트 152·153 | `7d35840` 외 |

- 등록: **#908**·**#911**·**#919** 아이디어 · **#931**·**#932**(M8 버그/개선, 미착수). #916 은 「완료」.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`d1f5ae0`(+ 이 문서 커밋), 일감 worktree 제거 완료 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 배달 및 check 대상 (완료) |

- 상주 재기동: `master.issue_wrapup 933` 이 `ax-task-queue`·`ax-projects` 를 재기동했다(11-11 02:43, 재판정 깨끗). `ax-broker` 는 최신.

## 유지할 운영 상태

- 마스터 담당 기록 **antigravity**(실제 인수 11-09 00:07, 사용자 지시), 워커 전역 **codex**(state, 10-18 — 11-11 02:47 재조회 일치, 변경 없음). #930·#933 은 Claude 가 작성했으나 교대 지시가 없어 담당 기록은 그대로다.
- 🔴 Redmine 은 M7 이 닫히고 **마일스톤 8** 이 열려 있다. `CLAUDE.md`·공용 문서의 「M7 open」 서술과 M8 문서 부재는 미정리다(자동 로드 문서라 동의 필요).
- #929 회차 2 는 닫혔다(11-11 02:01): 해시 R314(지적 5) 연결 → Codex 종합 리뷰 **R317**(중간 2 · 낮음 3, R314 지적 4건 남음·1건 해소). 지적은 미처리다 — 리뷰 판정이며 코드와 대조하지 않았다.
- #933 리뷰 진행 중(02:48): 해시 4개 중 1개 `queued`·3개 `waiting`, 종합 리뷰 대기. 작성 계열 `claude` → agy 가 본다. 결과는 #933 노트로 붙는다.
- 실제 BC-250 poweroff 는 아직 실행한 적이 없다. 종료 중 SSH rc=255 면 꺼졌어도 `SHUTDOWN FAILED` 로 끝날 수 있다(가설·미측정).
- ax-broker active · ax-projects active · ax-task-queue active, ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #929 포함 표의 일감 코드 마감 완료. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. 새 Claude·Codex 세션에서 전체 도구 승인 정책 반영을 확인한다. 설정 파일 대조와 이미 실행 중인 세션의 유효 권한은 구분한다. 새 대화형 Claude 세션에서 `ax-client` 연결도 확인한다(#930 은 `claude mcp list` 까지만 확인).
2. **다음 일감 선택**: 사용자가 정한다. 후보는 **#931**·**#932** · 아이디어(#908·#911·#914·#919) · 세션 토큰 보강(#741). 「#N 진행해」 발화 전에는 시작하지 않는다.
3. #929 R317(Codex — `bc250_shutdown.py` 중간 2: SSH stderr 안내를 점검 실패로 처리 · Ping 실행 오류를 단절로 계산, `master_local.py` 스킬 링크 대상 미검증)과 #930 R315·R316, #933 리뷰(나오는 대로) 지적을 코드와 대조하고 처리를 사용자와 정한다.
4. `.33`·`.43` 이 켜지면 `master.client update` → `check` rc0. 그 뒤 `.33` 요청자 세션의 첫 마감에서 `ax-client:issue_finish(N)` 이 `issue/<N>` 끝을 git 에서 읽는지(`[git]` 오류 여부) 본다 — #933 의 미확인 항목.
5. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.
