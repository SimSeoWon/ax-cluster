# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).

- **갱신 시각**: 2026-09-08 00:40 KST (UTC+9)
- **지휘 도구 / 세션 식별자**: Claude Opus 5 (1M) · `session_01L77g9My6GzoA6T9bwjkFRf`
- **상태**: **작업 중** — ② 완료 · **자동 로드 검증 완료(네 조합 실측)** · 다음은 §15.6 ③
- **관련 Redmine 일감 / 목표**: [`#384`](http://192.168.0.57:8080/issues/384) [AX] Claude ↔ Codex
  마스터 지휘 교대 (마일스톤 6, 상태 **진행**, 노트 2건 — Codex 의 ① 실측, Claude 의 ② 완료).
  아이디어 상위 일감 [`#368`](http://192.168.0.57:8080/issues/368)(자동 선택 실행기)은 **이번 범위 밖**.

## 사용자 결정 · 승인 범위 · 근거 / 미결 질문

- **역할 분담** (사용자 2026-09-07): 지휘자는 **Claude**, **Codex 는 자기 쪽 실측 담당**.
- **순서** (사용자 2026-09-07): **① 조사 → ② 공용 문서**. 문서를 먼저 만들면 실제로 지원되지
  않는 기능까지 공통 규칙으로 적게 된다.
- **② 진행 승인** (사용자 2026-09-08): *"리포트 55를 반영해 ② 공용 문서·진입점 배선을
  진행하고, 자동 로드는 새 세션에서 검증하자"*.
- **승인 셋** (사용자 2026-09-08, *"세 개 다 승인, CLAUDE.md 삽입하고 커밋해"*):
  ⑴ 자동 로드 문서 두 곳(`machines/sim-desktop.md` · `ax-cluster/CLAUDE.md`) 삽입 —
     **적용됨** ⑵ 커밋 — **`8a7b3c6`** ⑶ `#384` → 「진행」 — **적용됨**.
  [주의] 이 승인은 **그 셋에 대한 것**이다. **푸시는 포함되지 않는다.**
- **미결**: 푸시 — GitHub(`SimSeoWon/ax-cluster`, private)와 `.43` 동기화가 **밀려 있다**.

## 저장소 · 브랜치 · HEAD / 미커밋 파일

    저장소   ~/ax-cluster   브랜치 main   HEAD 9e2b9de (확인 당시 기준)
             [주의] **커밋만 했고 푸시는 안 했다** — origin 보다 2 커밋 앞
             [주의] 기록된 해시는 **확인 당시 기준**이다 (사용자 2026-09-08).
                    자기 갱신 커밋까지 맞추려고 커밋을 더 하지 않는다 — 이후 변경을 대조한다
             미커밋   docs/orchestrator-rules.md · docs/orchestrator-handoff.md · AGENTS.md
                      (자동 로드 실측 반영분 — 커밋 승인 대기)

`8a7b3c6` 에 담긴 것 (10개):

    A  AGENTS.md                              Codex 진입점 (저장소)  AX-ENTRY-MARK: repo
    A  machines/sim-desktop-agents.md         Codex 진입점 (홈) ← ~/AGENTS.md 심볼릭 링크
    A  docs/orchestrator-rules.md             공용 규칙
    A  docs/orchestrator-handoff.md           이 파일
    A  docs/15-orchestrator-handoff.md        계획 본체
    A  reports/54-...claude-side-survey.md    ① Claude 쪽 조사
    A  reports/55-...codex-side-probes.md     ① Codex 쪽 실측
    M  machines/sim-desktop.md                진입 블록 + AX-ENTRY-MARK: home
    M  CLAUDE.md                              진입 블록 + AX-ENTRY-MARK: repo
    M  PLAN.md                                색인 15r·15h

**미커밋 없음.** [주의] **푸시는 안 했다** — 세 곳 동기화가 밀려 있다.

## 완료한 작업 / 검증 명령·결과

- **①-A Claude 쪽 목록화** — 리포트 54. 지침·기억 29건·스킬 2종·훅 0개·MCP 33종을 실측.
- **①-B Codex 쪽 실측** — 리포트 55. 12항목 중 승인 후 성공 6(SSH 3대·서비스·큐·브로커·HTTP
  4포트·MCP `tools/call`), 성공 3(서브에이전트 위임·회수 · Python 실행 · 실행 중 출력 회수),
  정책만 확인 2(`sudo -n -l` 재시작·훅 설치 — **실제 실행 안 함**), 미실증은 §미검증.
- **정정**: 리포트 54 의 「MCP 35종」 → **33종**. Codex `tools/list` 실측과 일치.
- **②-1** `docs/orchestrator-rules.md` 작성 (공통 규칙 · 도구별 차이 · 미실증 · 근거).
- **②-2** `docs/orchestrator-handoff.md` 작성 (이 파일).
- **②-3** 진입점 4곳에 표식 삽입 · `PLAN.md` 색인 · 커밋 `8a7b3c6` · `#384` → 「진행」+노트.
- **③ 자동 로드 검증 — 완료 (실측 2026-09-08)**. `claude -p` · `codex exec` 로 각 시작
  위치에서 새 세션을 띄웠다. 표식 결과:

      시작 위치        Claude          Codex
      /home/sim        home            home
      ~/ax-cluster     home, repo      repo

  🔴 **계층 로드가 다르다** — Claude 는 부모의 홈 지침까지 싣고 Codex 는 저장소 것만 싣는다.
  → 두 진입 파일은 **각각 자족적**이어야 한다. `AGENTS.md`(저장소)에 홈에만 있던 항목을 채웠다.
  [완료] **심볼릭 링크는 원인이 아니었다** — Codex 가 홈에서 링크 너머의 `home` 을 읽었다.
  **맥락 복원도 확인** — 두 도구 다 공용 문서를 따라가 진행 작업·승인 범위·다음 작업을
  복원했고, **각자 독립적으로** 기록 HEAD(`8a7b3c6`)와 실제 HEAD(`9e2b9de`)의 차이를 보고했다.
  = §15.4 ④ 「대조부터 한다」가 실제로 돌았다.

현재 상태 실측 (2026-09-08 조회):

    서비스   ax-task-queue · ax-broker · ax-projects · ax-indexer.path
             ax-dispatch.path · ax-status.timer   →  전부 active
    파견 보류  ~/.cache/ax-dispatch/hold.json 없음 → 재개 대기 없음
    열린 [AX] 일감 29건 (#384 포함)

## 미검증 / 실패·보류 사유

- [완료] **`AGENTS.md` 자동 로드 — 실측됨** (위 ③). 
- **대화형 세션의 자동 로드 — 미실증.** ③ 은 비대화형(`claude -p`·`codex exec`) 값이다.
- 🔴 **시작 자동 고지 — 양쪽 다 없다.** 마스터 `.57` 에는 고지 층 자체가 없다
  (Claude 훅은 `role=="requester"` 인 `.33` 에만 간다 — `master/client/spec.py:354`).
  지금 배선은 **「진입 지침 첫머리에 읽으라고 박는」 수동 수단 하나뿐**이다.
- **Codex 네이티브 MCP 연결 — 미배선.** `~/.codex/config.toml` 에 `[mcp_servers]` 없음.
  리포트 55 의 성공은 셸 HTTP 호출이고 네이티브 연결이 아니다.
- **`sudo` 실제 실행 — 미실증.** 정책 조회(`sudo -n -l`)만 통과. 다른 유닛으로 일반화 금지.
- **양방향 교대(§15.6 ③④) · 중단 복구(⑤) — 미착수.**
- **세션을 넘는 프로세스 생존·재접속 — 미실증** (같은 세션 안의 출력 회수만 확인).
- **실패한 것 없음.** 이번 구간에서 rc≠0·차단·예외로 멈춘 자리는 없다.

## 실행 중인 서비스 작업 · 프로세스 · 원격 작업 / 로그 위치

- **지휘자가 띄운 백그라운드 프로세스 없음.** 회수할 것이 없다.
- **원격 작업 없음.** `.2`·`.33`·`.43` 에 이번 건으로 보낸 작업 없음.
- 도는 것은 systemd 뿐이며 **대화 세션과 무관하다** — 로그는 `journalctl -u <unit>`.
- **큐에 돌고 있는 분산 작업 없음** (파견 보류 파일 없음).

## 서브 에이전트별 담당 파일 · 진행 · 산출물 · 종료 여부

- **Claude 쪽: 띄운 서브 에이전트 없음** — 전부 이 세션이 직접 수행.
- **Codex 쪽: `handoff_read_probe` 1건** — 지정 문서 읽기, 결과 회수 완료, **종료됨**.
  프로브 임시 파일 `/tmp/ax-codex-access-probe.py` · `/tmp/ax-codex-mcp-probe.py` 는
  **배포 도구가 아니고 커밋 대상도 아니다.**

## 바로 다음 작업

1. **커밋** — 위 미커밋 3건(실측 반영분). **승인 대기.**
2. **푸시** — `origin/main` 보다 2 커밋(+ 위 1) 앞. GitHub private + `.43` 동기화. **승인 대기.**
3. **§15.6 ③ Claude → Codex 실증** — 작고 되돌릴 수 있는 AX 작업 하나를 넘기고,
   미커밋 변경·검증 결과·다음 작업을 **재설명 없이** 이어받는지 잰다.
   [주의] ③ 의 맥락 복원 확인은 **읽기만** 잰 것이다. 실제 교대는 **작업이 오간다.**
4. 그다음 §15.6 ④ 역방향 · ⑤ 중단 복구. **양방향·중단 복구 전에는 `#384` 를 닫지 않는다.**

## 관련 문서 링크

- 계획 본체 `docs/15-orchestrator-handoff.md` · 공용 규칙 `docs/orchestrator-rules.md`
- 조사 `reports/54-orchestrator-handoff-claude-side-survey.md` ·
  `reports/55-orchestrator-handoff-codex-side-probes.md`
- 일감 [`#384`](http://192.168.0.57:8080/issues/384) · 아이디어 [`#368`](http://192.168.0.57:8080/issues/368)
- 열린 마일스톤 `docs/milestones/6-improvements.md`
