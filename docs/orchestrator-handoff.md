# 현재 AX 작업 인수인계

> 2026-11-08 22:35 Antigravity 체크포인트(#923 마감 `ec30077` 배달 완료 · Antigravity accept-edits/always-proceed 설정 갱신 · 이하 오늘 마감분은 아래 표). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `d946ba7`·`54b5632`·`93c93d0`·리포트138~156·각 일감 노트에 있다.
> 진행 중 일감·일감 잠금은 없다. 배달(`master.client update`) rc0 완료.

## 🔴 오늘 오후 바뀐 규칙 (사용자 결정 2026-11-08)

- 🔴 **일감 「진행해」 = 끝까지 승인**(`docs/orchestrator-rules.md` §1.9 · `ax-plan` §3-1): 구현 → 검사+공식 통합 → 리포트 → 커밋 →
  `issue_finish(confirm=True)` → 신선도 판정된 서비스만 재기동(oneshot 확인) → **인수인계서 커밋·push → 마지막에 배달·check rc0**.
  멈추는 자리(실패·대상 밖·설계 갈림길·파괴적 git·⑦/finalize·자동 로드 문서)는 그대로.
- 🔴 **Antigravity 진입 및 상호작용 규칙**(#920 · 사용자 결정 2026-11-08): 시작 폴더 지침만 자동 로드하므로 홈 `~/GEMINI.md` 가
  작업 루트의 `AGENTS.md` 를 먼저 읽고 AX-ENTRY-MARK 보고. **도구 승인 팝업 차단**은 `settings.json` 의
  `mode: accept-edits`, `toolExecutionPolicy: always-proceed` 로 영구 적용. 상호작용 타이밍은 **① 일 시작할 때(착수)**와
  **② 일 끝났을 때(완료/판단)** 2회로 고정(에러 시 예외 보고). 공용 지침(`CLAUDE.md`, `AGENTS.md`) 임의 수정 금지.
- **마감 뒤 기록 몫**(`ax-plan` 3-1 · `331b260`·`ed0b5d6`): 리포트=일감 커밋 시점까지(끝에 「최종 결과는 Redmine 마감 노트」) ·
  Redmine 마감 노트=결과 정본 · **이 문서=마감 직후 main 문서 커밋**(마감·배포 승인에 포함). 배포를 마감 뒤 **따로** 승인받아
  했으면 배포 결과로 이 문서를 **한 번 더** 맞춰 커밋·push 한다.
- **읽기 조회 경로 부재 예외**(`6284054` — `~/CLAUDE.md`·`AGENTS.md`·`docs/orchestrator-rules.md`): 「실패는 보고하는 자리」의
  유일한 예외. 읽기 전용 조회가 `No such file or directory` 면 확인된 경로로 재조회하고 보고에 남긴다.
- 🔴 **이 문서의 절 제목 「바로 다음 작업」은 바꾸지 않는다** — `test_handoff_size` 가 `^#{2,3}\s*바로 다음 작업` 으로 판정하고
  `AGENTS.md` 가 이 절을 이름으로 가리킨다. #898 Codex 인계본이 「바로 이어갈 자리」로 써서 공식 통합이 1회 실패했다.

## #898 마감 (Codex 구현 → Claude 인수·마감)

- Codex 한도 소진으로 worktree 에 인계 → Claude 가 인계서·리포트148·Redmine·diff 대조 후 인수(마스터 담당 기록 claude 16:41).
- 내용: 요청자 `ax-client` 관리 도구 **20개**(용어·온톨로지 편집/잠금·작업장·도메인 필드·로그 태그·staging·개명)를
  인증 **8101 POST 대행**(`master/task_queue/ontology_proxy.py`)으로 기존 마스터 코어에 연결. 요청자 스킬
  `ax-ontology`·`ax-request`·`manage-domain`·`refresh-ontology` 를 실제 도구·인자로 정정, `test_skill_conventions` 에
  역할별 MCP 서버 호출 검사 추가. 도메인 전체 삭제·멤버 추가/제거는 코어 미확인이라 미지원으로 명시.
- Claude 몫: 규약 47/49 의 두 표기(manage-domain:151 제목 → `rename-class`, refresh-ontology:35 → `ax-client:rename_class`)
  · 인계서 절 제목 복원. 사용자 「응 refresh-ontology 포함해서 진행해」·「응 1번으로 진행해」.
- 검증: 공식 통합 rc0 **188/188**(`Ran 188 tests in 167.594s`) · 규약 49/49 · 서버 13/13 · client 350/350 · `diff --check` rc0.
- 사용자 「응 커밋하고 마감까지 진행해」 → 커밋 `54b5632`(14파일) → `issue_finish_tool(898, confirm=True)`:
  `done=[push, ff, worktree_remove, delete_branch, register, link, release, close, redmine]`, `closed=true`, `why=""`.
- 반영: 사용자 「응 재기동하고 배달까지 진행해」 → `sudo -n /usr/bin/systemctl restart ax-task-queue` rc0,
  `ExecMainStartTimestamp` 12:31:43 → **16:49:16**, active. `master.client update` rc0, 워커 3/3 OK.

## 🔴 일감 작업 위치 (#907)

- **AXCluster 일감은 운영 체크아웃에서 편집하지 않는다.** 운영 `/home/sim/ax-cluster` 는 서비스 코드라 **늘 `main`**.
  `ax-projects:issue_start_tool(N)` 이 `/home/sim/ax-cluster/.ax-issues/<N>` 에 `issue/<N>` worktree 를 만든다.
  **응답의 `repo` 가 편집·검사·커밋 위치**, `checkout` 은 운영 저장소(편집 금지).
- `finish(confirm=True)` = push → 운영 main ff → worktree 제거 → 브랜치 삭제 → 마감 추적·잠금 해제·완료.
- `pause` = worktree 제거(브랜치 유지), 재개 = `issue_start_tool`. **#898 에서 깨끗한 worktree 의 보류→재개를 실증했다**
  (16:15, 리비전 보존). 미커밋 변경이 있는 보류는 미검증 — dirty 상태에서 pause 하지 않는다.
- 🔴 `AXCluster/repo`(`track.local_clone`)는 **색인기의 push 봉인 미러**다 — 작업 위치가 아니다(#906).

## 오늘 완료한 일감 (2026-11-08)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #893 | 미검토 커밋 목록 유실 수정 | `c62b2fb` |
| #906 | 일감 작업 위치 운영 저장소 복귀 + 봉인 저장소 거절 | `201a81a` |
| #907 | 마스터 일감 worktree · `master_workspace`(AXCluster 전용) — 리포트 143 | `9f7248d` |
| #909 | #893 후속 — 해시 지적 0건이면 판정 절 요구 안 함 | `5de2c16` |
| #910 | worktree 에서 `test_ontology`·`test_sandbox` 상시 실패 해소 — 리포트 144 | `1f07442`·`2142338` |
| #897 | 상주 서비스 신선도를 기동 내용 해시로 판정 — 리포트 145, 상주 3개 재기동(12:31) | `172cea8` |
| #912 | #897 후속 — journal `-n` 제거 · mtime 1차 거름 | `478a820` |
| #894 | 종합 리뷰 판정 칸 마크다운 꾸밈 인식 — 리포트 146 | `c47d5b2` |
| #895 | 라운드 공지 검사의 멱등 저장 대기 — 리포트 147, 배달 3/3 OK | `dc778fe` |
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 (위) | `54b5632` |
| #886 | 마스터 로컬 잔재 정리(아래) + `cleanup machines` 가 task/·attempt/ 밖 로컬 브랜치도 열거 — 리포트 149 | `86e1351` |
| #917 | R240 수용 4건(워터마크 검사 1회화 · 공개 이름 · 테스트 임시 루트) — 리포트 150 | `93d7688` |
| #918 | 서비스 신선도 두 등급 — 직접 경로 [중요] stale · import 의존(정적 폐포) [주의] 「재기동 권장」(rc 미반영) — 리포트 151 | `bee9ddc` |
| #913 | Gemini 4 Argon 모델 성능 평가(Antigravity 단독 수행) — 리포트 2026-11-08-913 | `f3d63b8` |
| #882 | 범위 리뷰 실패·포기·대기 일감 진행 노트 기록 — Argon 서브에이전트 위임 · 리포트 152 | `62d0dd8` |
| #820 | 조각 범위 밖 변경 감지 및 ⑦ 사람 게이트 고지 — Argon 위임 · 리포트 153, 배달 3/3 OK | `7d35840` |
| #921 | 마감 뒤 단계를 명령 하나로(`master.issue_wrapup`) · 검사 파일 직접 실행 규약(`test_test_runnable`) · 통합 191 — 리포트 154 | `aea3f94` |
| #922 | `issue_wrapup` 후속 — oneshot 대기를 재기동 서비스별로 · rc 2 노트 — 리포트 155 | `f9a9a91` |
| #923 | R298 지적 6건 — issue_wrapup 하위 명령 실패/예외 방어 · next 명령 인자 — 리포트 156 | `ec30077` |
| #884·#885·#887·#915 | 코드 변경 없이 종결 — #884 T7 마감 · #885 해소 · #887·#915 해소 | — |

- 등록: **#908**·**#911**·**#916**·**#920** 아이디어(일감 아님). R240 지적 12 전부 처분.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`93c93d0`(+ 이 문서 커밋), 깨끗함 · 로컬 브랜치 main 하나 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | 배달(`master.client update`) 3/3 OK 완료 (HEAD `93c93d0`) |

- 상주 재기동: ax-broker 17:39:08 · ax-task-queue 17:41:31 · ax-projects 22:08:19(#923 `issue_wrapup` 이 의존 변경 판정으로 재기동).
  재기동 뒤 `service_freshness.check()`: stale 0 · 판정 불가 0 · 의존 [주의] 0. 재기동 중 리뷰 큐·색인기 영향 없음.

## Codex 가 알아야 할 것

- **검사 기준**: `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 주고 일감 worktree 에서. 공식 통합 목록 `tests/integration/checks.json`
  (현재 191건) — 실패 0 이 기준. `-f` 라 첫 실패에서 멈추니 실패 뒤 수치는 분모가 아니다.
- **인계서 형식**: 상한 150줄 · 「바로 다음 작업」 절 필수(`test_handoff_size`). worktree 에 인계를 남겨도 같은 검사가 공식 통합에서 돈다.
- 검사·커밋·push·재기동은 각각 승인 규칙대로.

## 유지할 운영 상태

- 마스터 담당 기록 **claude(11-08 16:41)**, 워커 전역 codex(state, 10-18).
- ax-broker active(17:39) · ax-projects·ax-task-queue active(17:41), ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #820·#882·#884~#887·#893~#907·#909·#910·#912·#913·#915·#917·#918·#921~#923 완료: 리포트138~156·Redmine. 중복 마감·산출물 재생성 금지.

## 바로 다음 작업

1. 🔴 **세션 재연결 테스트**: 새 Antigravity 세션 연결 시 도구 승인 팝업 없이 태스크 착수와 완료 판단 시점에만 상호작용하는지 확인.
2. `ax-handoff` 로 이 문서와 실제 상태(운영 main=origin/main · `.ax-issues` 비어 있음 · 잠금 없음)를 대조한다.
   Antigravity 는 홈 `GEMINI.md` 규칙대로 **작업 저장소 루트의 `AGENTS.md` 를 먼저 읽고 AX-ENTRY-MARK 를 보고**한다.
3. **다음 일감 선택**: 사용자와 다음 진행할 일감 결정 (등록된 아이디어 #908·#911·#916·#920 또는 신규 일감).
4. #898 실사용 확인: 게임 프로젝트 마운트 전환 뒤 `.33` 요청자 세션에서 새 `ax-client` 관리 도구를 한 번 불러 본다(사용자 결정).
5. #920 남은 배선: 1번(지휘자 기록 claude/codex 만) · 3번(교차 계열 리뷰 조건 — Antigravity 가 쓰고 agy 가 리뷰하면 같은 계열). 결정은 사용자.
6. 다른 일감을 자동 시작하지 않는다. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존대로 멈춰 묻는다.

