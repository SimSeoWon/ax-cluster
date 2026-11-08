# 현재 AX 작업 인수인계

> 2026-11-09 Codex 체크포인트(#927 마감 `2570af6` · 전체 도구 승인 생성기·실제 설정 적용). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `da43835`·`513d5d2`·`1c65dcf`·`2570af6`·리포트 159~162·각 일감 노트에 있다.
> #927 코드 마감·잠금 해제 완료. 이 문서 커밋 직후 `issue_wrapup` 이 배달한다 — 결과의 정본은 #927 마감 노트.

## 🔴 오늘 바뀐 규칙 (사용자 결정 2026-11-08 ~ 11-09)

- 🔴 **일감 「진행해」 = 끝까지 승인**(`docs/orchestrator-rules.md` §1.9 · `ax-plan` §3-1): 구현 → 검사+공식 통합 → 리포트 → 커밋 →
  `issue_finish(confirm=True)` → 신선도 판정된 서비스만 재기동(oneshot 확인) → **인수인계서 커밋·push → 마지막에 배달·check rc0**.
  멈추는 자리(실패·대상 밖·설계 갈림길·파괴적 git·⑦/finalize·자동 로드 문서)는 그대로.
- 🔴 **Antigravity 진입 및 상호작용 규칙**(#920 · #928): 시작 폴더 지침만 자동 로드하므로 홈 `~/GEMINI.md` 가
  작업 루트의 `AGENTS.md` 를 먼저 읽고 AX-ENTRY-MARK 보고. **도구 승인 팝업 방지**는 `settings.json` 의
  `permissions.allow` 에 `mcp(ax-projects/...)`·`mcp(ax-client/...)` 및 클러스터 필수 CLI 접두사를 일괄 사전 등록하여 보장(#928).
  상호작용 타이밍은 **① 일 시작할 때(착수)**와 **② 일 끝났을 때(완료/판단)** 2회로 고정(에러 시 예외 보고).
- 🔴 **지휘자 셋 · 교차 계열 리뷰**(#920 · #926): 운영 일감 시작은 `ax-projects:issue_start_tool` 만 된다. MCP `clientInfo` 가 작성 계열이 되고,
  Antigravity 작성분은 Codex 단독 리뷰·실패 시 폴백 없음, 그 밖은 agy. 명시 Argon 호출만 한도 시 Flash High 폴백.
- **마감 뒤 기록 몫**(`ax-plan` 3-1): 리포트=일감 커밋 시점까지 · Redmine 마감 노트=결과 정본 · **이 문서=마감 직후 main 문서 커밋**.
- **세 CLI 전체 도구 허용**(#927 사용자 결정): Claude `permissions.defaultMode=bypassPermissions`, Codex 두 AX MCP 기본 approve 및 실제 도구 전수 승인.
  Antigravity 기존 전체 allow 보존. 스킬은 사용하는 도구 권한을 따른다. Codex sandbox·OS 권한과 작업 범위·사람 게이트는 별도다.
- 🔴 **이 문서의 절 제목 「바로 다음 작업」은 바꾸지 않는다** — `test_handoff_size` 가 `^#{2,3}\s*바로 다음 작업` 으로 판정.

## #928 마감 (Antigravity 툴 권한 allowlist 일괄 등록)

- **settings.json allowlist 사전 완비**: `ax-projects` 45종, `ax-client` 64종 전수 도구 및 필수 CLI 접두사 20종 등 92개 항목을 일괄 등록(누적 241개)하여 도구 호출 시 승인 팝업 반복 원인 해소.
- **master-local 생성기 정비**: `AGY_BASE_COMMANDS`를 신설하고 `check()`의 agy 권한 대조를 `issubset` 검사로 완화하여 확장된 화이트리스트가 대조 실패를 유발하지 않도록 수정(`test_client_master_local` 88/88 통과).
- **리포트 160 정정**: 가상 설정(`toolExecutionPolicy`) 및 팝업 0건 오류를 실측 사실(수동 승인 반복 및 #928 해결)로 정정하고 리포트 161 작성.
- **검증 및 마감**: 공식 통합 검사 **191/191 전수 통과**(`Ran 191 tests in 183.246s, OK`), 커밋 `1c65dcf` → `issue_finish_tool(928, confirm=True)` 완료.

## 오늘 완료한 일감 (2026-11-08 ~ 11-09)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #920 | 지휘자 셋 — 작성 계열 신호 · 리뷰 큐 분기 · Argon 폴백 · Antigravity `ax-projects` 연결 — 리포트 159 | `da43835` |
| #926 | Antigravity 지휘 통합 실증 (ax-projects 시작·Argon 위임·Codex 리뷰) — 리포트 160 | `513d5d2` |
| #928 | Antigravity 툴 권한 allowlist 일괄 등록 및 master-local 정비 — 리포트 161 | `1c65dcf` |
| #927 | 전체 도구 승인 정책·생성기 일치, 기존 승인 보존·실제 설정 적용 — 리포트 162 | `2570af6` |
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 | `54b5632` |
| #921~#925 | 마감 일원화·wrapup 방어·담당 기록·실증 정비 — 리포트 154~158 | `aea3f94` 외 |
| #820·#882 | 범위 밖 감지 게이트·범위 리뷰 재시도 노트 — 리포트 152·153 | `7d35840` 외 |

- 등록: **#908**·**#911**·**#916**·**#919** 아이디어.

## #927 검증·실제 적용

- 로컬 서브 에이전트 구현·독립 읽기 검토. 회귀109/109, 정적 차단0(비차단 타입노트25), 공식 통합 **191/191**, `Ran 191 tests in 203.398s · OK`.
- `issue_finish(confirm=True)`: `done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `closed=true`, `why=""`.
- main 반영 뒤 운영 경로에서 `master-local` 계획→`--apply`→`--check` **rc0 · 12/12**. Codex ax-client64개·두 AX MCP 기본approve, Claude 전체허용 적용.
- Antigravity settings는 쓰지 않았고 전후 SHA256 `f85c631f36256e8368993d6787b02a859ed911a15c33e08bccf905efd0796a3a` 동일.
- 백업 접미사 `bak-master-local-20261109-005651`(Claude settings·Codex config). 실제 MCP redmine_meta 조회 성공. 새 대화 세션의 팝업 여부는 별도 확인 대상.
- wrapup 1차: 세 상주 최신·재기동 없음, 인수인계서 대기 rc2. 이 문서 커밋 뒤 같은 명령을 재실행해 배달·check한다.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`2570af6`(+ 이 문서 커밋), 일감 worktree 제거 완료 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 이 문서 커밋을 배달 — 결과는 #927 마감 노트 |

- 상주 재기동: 신선도 판정 최신(재기동 불필요).
- `master-local --apply` 전체 적용은 #927로 승인 손실 없이 실증했다. **운영 경로에서 실행**한다(worktree에서 하면 제거될 경로가 영구 등록될 수 있다).

## 유지할 운영 상태

- 마스터 담당 기록 **antigravity**(실제 인수 11-09 00:07, 사용자 지시), 워커 전역 codex(state, 10-18).
- ax-broker active · ax-projects active · ax-task-queue active, ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #927·#928 포함 표의 일감 코드 마감 완료. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. 새 Claude·Codex 세션에서 전체 도구 승인 정책 반영을 확인한다. 설정 파일 대조와 이미 실행 중인 세션의 유효 권한은 구분한다.
2. **다음 일감 선택**: 사용자와 등록된 아이디어(#908·#911·#914·#916·#919) 또는 새 일감 진행 결정.
3. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.
