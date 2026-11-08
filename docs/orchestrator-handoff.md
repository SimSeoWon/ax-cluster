# 현재 AX 작업 인수인계

> 2026-11-09 00:20 Antigravity 체크포인트(#926 마감 `513d5d2` · 이하 오늘 마감분은 아래 표). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `da43835`·`513d5d2`·리포트 159·160·각 일감 노트에 있다.
> 진행 중 일감·일감 잠금은 없다. 이 문서 커밋 직후 `issue_wrapup` 이 배달한다 — 결과의 정본은 #926 마감 노트.

## 🔴 오늘 바뀐 규칙 (사용자 결정 2026-11-08)

- 🔴 **일감 「진행해」 = 끝까지 승인**(`docs/orchestrator-rules.md` §1.9 · `ax-plan` §3-1): 구현 → 검사+공식 통합 → 리포트 → 커밋 →
  `issue_finish(confirm=True)` → 신선도 판정된 서비스만 재기동(oneshot 확인) → **인수인계서 커밋·push → 마지막에 배달·check rc0**.
  멈추는 자리(실패·대상 밖·설계 갈림길·파괴적 git·⑦/finalize·자동 로드 문서)는 그대로.
- 🔴 **Antigravity 진입 및 상호작용 규칙**(#920 · 사용자 결정 2026-11-08): 시작 폴더 지침만 자동 로드하므로 홈 `~/GEMINI.md` 가
  작업 루트의 `AGENTS.md` 를 먼저 읽고 AX-ENTRY-MARK 보고. **도구 승인 팝업 차단**은 `settings.json` 의
  `mode: accept-edits`, `toolExecutionPolicy: always-proceed` 로 영구 적용. 상호작용 타이밍은 **① 일 시작할 때(착수)**와
  **② 일 끝났을 때(완료/판단)** 2회로 고정(에러 시 예외 보고). 공용 지침(`CLAUDE.md`, `AGENTS.md`) 임의 수정 금지.
- 🔴 **지휘자 셋 · 교차 계열 리뷰**(#920 · #926): 운영 일감 시작은 `ax-projects:issue_start_tool` 만 된다. MCP `clientInfo` 가 작성 계열이 되고,
  Antigravity 작성분은 Codex 단독 리뷰·실패 시 폴백 없음, 그 밖은 agy. 명시 Argon 호출만 한도 시 Flash High 폴백.
- **마감 뒤 기록 몫**(`ax-plan` 3-1): 리포트=일감 커밋 시점까지 · Redmine 마감 노트=결과 정본 · **이 문서=마감 직후 main 문서 커밋**.
- 🔴 **이 문서의 절 제목 「바로 다음 작업」은 바꾸지 않는다** — `test_handoff_size` 가 `^#{2,3}\s*바로 다음 작업` 으로 판정.

## #926 마감 (Antigravity 지휘 실증 완료)

- **Antigravity 세션 단독 지휘**: `ax-projects:issue_start_tool(926)` 호출로 `author.family == 'agy'`, `client == 'antigravity-client'`, `authors == ['agy']` 스탬프 획득 실증.
- **Argon 서브에이전트 위임**: `gemini-4-argon-medium` 서브에이전트에 리포트 초안 작성을 위임하고 지휘 세션(Flash Medium)이 직접 검증 및 보정.
- **무팝업 태스크 완결**: `accept-edits` + `always-proceed` 하에서 중간 팝업 0건으로 착수/마감 2회 상호작용 규칙 준수.
- **검증**: 공식 통합 검사 **191/191 전수 통과**(`Ran 191 tests in 193.821s, OK`), `git diff --check` rc 0.
- **마감**: 커밋 `513d5d2` → `issue_finish_tool(926, confirm=True)`: push, main ff, worktree 정리, 일감 잠금 해제, Redmine 완료·100 닫기 완료.

## 오늘 완료한 일감 (2026-11-08 ~ 11-09)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #920 | 지휘자 셋 — 작성 계열 신호 · 리뷰 큐 분기 · Argon 폴백 · Antigravity `ax-projects` 연결 — 리포트 159 | `da43835` |
| #926 | Antigravity 지휘 통합 실증 (ax-projects 시작·Argon 위임·Codex 리뷰) — 리포트 160 | `513d5d2` |
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 | `54b5632` |
| #921~#925 | 마감 일원화·wrapup 방어·담당 기록·실증 정비 — 리포트 154~158 | `aea3f94` 외 |
| #820·#882 | 범위 밖 감지 게이트·범위 리뷰 재시도 노트 — 리포트 152·153 | `7d35840` 외 |

- 등록: **#908**·**#911**·**#916**·**#919** 아이디어 · **#927**(master-local·Codex 승인 어긋남).

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`513d5d2`(+ 이 문서 커밋), 깨끗함 · 로컬 브랜치 main 하나 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 이 문서 커밋을 배달 — 결과는 #926 마감 노트 |

- 상주 재기동: 신선도 판정 최신(재기동 불필요).
- Antigravity 설정: `~/.gemini/config/mcp_config.json` 에 `ax-projects` 추가 상태.
  🔴 `master-local --apply` 는 돌리지 않았다 — Codex 자동 승인 약 14개를 지운다(#927). 해결 전 전체 적용 금지.

## 유지할 운영 상태

- 마스터 담당 기록 **antigravity**(실제 인수 11-09 00:07, 사용자 지시), 워커 전역 codex(state, 10-18).
- ax-broker active · ax-projects active · ax-task-queue active, ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #926 포함 오늘 일감 전수 완료. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. **#926 Codex 교차 리뷰 확인**: #926 커밋(`513d5d2`)의 자동 리뷰가 `검증 모델: Codex`로 실행되는지 큐 및 Redmine 노트 모니터링.
2. 🔴 **#927 master-local 생성기와 Codex 자동 승인 목록 어긋남 정리**: `master-local --apply`가 Codex 승인을 지우지 않도록 정비.
3. **다음 일감 선택**: 사용자와 #927 또는 등록된 아이디어(#908·#911·#914·#916·#919) 진행 결정.
4. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.
