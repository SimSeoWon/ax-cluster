# 현재 AX 작업 인수인계

> 2026-11-09 00:37 Antigravity 체크포인트(#928 마감 `1c65dcf` · 이하 오늘 마감분은 아래 표). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `da43835`·`513d5d2`·`1c65dcf`·리포트 159~161·각 일감 노트에 있다.
> 진행 중 일감·일감 잠금은 없다. 이 문서 커밋 직후 `issue_wrapup` 이 배달한다 — 결과의 정본은 #928 마감 노트.

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
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 | `54b5632` |
| #921~#925 | 마감 일원화·wrapup 방어·담당 기록·실증 정비 — 리포트 154~158 | `aea3f94` 외 |
| #820·#882 | 범위 밖 감지 게이트·범위 리뷰 재시도 노트 — 리포트 152·153 | `7d35840` 외 |

- 등록: **#908**·**#911**·**#916**·**#919** 아이디어 · **#927**(master-local·Codex 승인 어긋남).

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`1c65dcf`(+ 이 문서 커밋), 깨끗함 · 로컬 브랜치 main 하나 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 이 문서 커밋을 배달 — 결과는 #928 마감 노트 |

- 상주 재기동: 신선도 판정 최신(재기동 불필요).
- Antigravity 설정: `~/.gemini/config/mcp_config.json` 에 `ax-projects` 추가 상태.
  🔴 `master-local --apply` 는 돌리지 않았다 — Codex 자동 승인 약 14개를 지운다(#927). 해결 전 전체 적용 금지.

## 유지할 운영 상태

- 마스터 담당 기록 **antigravity**(실제 인수 11-09 00:07, 사용자 지시), 워커 전역 codex(state, 10-18).
- ax-broker active · ax-projects active · ax-task-queue active, ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #928 포함 오늘 일감 전수 완료. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. 🔴 **#927 master-local 생성기와 Codex 자동 승인 목록 어긋남 정리**: `master-local --apply`가 Codex 승인을 지우지 않도록 정비.
2. **다음 일감 선택**: 사용자와 #927 또는 등록된 아이디어(#908·#911·#914·#916·#919) 진행 결정.
3. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.
