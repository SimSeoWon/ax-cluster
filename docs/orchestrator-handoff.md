# 현재 AX 작업 인수인계

> 2026-11-10 Claude 체크포인트(#930 마감 `14b3273` · #929 테스트의 실제 Claude 설정 오염 차단). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `da43835`·`513d5d2`·`1c65dcf`·`2570af6`·`c1b2537`·`eb78e03`·`14b3273`·리포트 159~165·각 일감 노트에 있다.
> #930 코드 마감·잠금 해제 완료. 이 커밋 직후 배달 — 결과는 #930 마감 노트에 덧붙인다.

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
- **검증 및 마감**: 단위/계약 테스트 35/35 통과, `test_client_master_local` 113/113 통과, 공식 통합 검사 **193/193 전수 통과**(`Ran 193 tests in 184.061s, OK`), 커밋 `eb78e03` → `issue_finish` 완료, 배달(`master.client update`) 3대 완료.

## 오늘 완료한 일감 (2026-11-08 ~ 11-10)

| 일감 | 결과 | 커밋 |
|---|---|---|
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

- 등록: **#908**·**#911**·**#919** 아이디어. #916 은 「완료」.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`14b3273`(+ 이 문서 커밋), 일감 worktree 제거 완료 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 배달 및 check 대상 (완료) |

- 상주 재기동: `master.issue_wrapup 930` 의 신선도 판정을 따른다.

## 유지할 운영 상태

- 마스터 담당 기록 **antigravity**(실제 인수 11-09 00:07, 사용자 지시), 워커 전역 codex(state, 10-18). #930 은 Claude 가 작성했으나 교대 지시가 없어 담당 기록은 그대로다.
- 🔴 Redmine 은 M7 이 닫히고 **마일스톤 8** 이 열려 있다. `CLAUDE.md`·공용 문서의 「M7 open」 서술과 M8 문서 부재는 미정리다(자동 로드 문서라 동의 필요).
- #929·#930 리뷰 노트는 큐 소비자가 끝나는 대로 붙는다. #929 는 11-10 00:52 에 미러 지연으로 대기 중이었다.
- 실제 BC-250 poweroff 는 아직 실행한 적이 없다. 종료 중 SSH rc=255 면 꺼졌어도 `SHUTDOWN FAILED` 로 끝날 수 있다(가설·미측정).
- ax-broker active · ax-projects active · ax-task-queue active, ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #929 포함 표의 일감 코드 마감 완료. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. 새 Claude·Codex 세션에서 전체 도구 승인 정책 반영을 확인한다. 설정 파일 대조와 이미 실행 중인 세션의 유효 권한은 구분한다.
2. **다음 일감 선택**: 사용자와 등록된 아이디어(#908·#911·#914·#919) 또는 세션 토큰 보강(#741) 진행 결정.
3. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.
