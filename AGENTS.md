# AGENTS.md — AX 클러스터 저장소 (`~/ax-cluster`)

    AX-ENTRY-MARK: repo

> 위 표식은 **자동 로드 검증용**이다. 새 세션이 지시 없이 이 파일을 읽었는지 가리는 데
> 쓴다 (`docs/orchestrator-handoff.md` §바로 다음 작업). 지우지 않는다.

## 세션 시작에 읽을 것

1. 🔴 **`docs/orchestrator-handoff.md`** — 지금 무엇이 진행 중인가. **한 벌만 있다.**
2. 🔴 **`docs/orchestrator-rules.md`** — 두 지휘자(Claude · Codex)가 함께 지키는 규칙.
3. `docs/milestones/6-improvements.md`(열린 마일스톤) · `docs/12-multi-project.md`(열린 축).
   [주의] **항목·진행은 레드마인(`:8080`)만** 본다.
4. `reports/` 를 **전문으로** 읽는다 — grep 은 대체가 아니다.

## 절대 놓치면 안 되는 것 (전문은 `docs/orchestrator-rules.md`)

- **커밋·푸시는 자율 실행 금지** — 매번 승인을 받는다.
- **실패는 고치는 자리가 아니라 보고하는 자리다** — rc≠0·차단·예외면 멈추고 사유와 갈래를 낸다.
- **지시받은 대상 밖의 파일은 건드리지 않는다.**
- **사람 게이트는 둘** — ⑺ 전진(`ax-advance`)과 finalize(`main` 머지).
- **`~/AgentTest` 는 참조 전용** — 수정·푸시 금지. 만들기 전에 거기부터 읽는다.
- **사용자와의 대화는 한국어.**
- **작업장은 `.33` 이다** — Unreal 작업은 거기로 들어온다. 여기서 다루는 것은 클러스터 자체다.
  기계: `.57` 마스터(이 저장소) · `.2` 워커+추론(계정 `janus`, UE5) · `.33` **게임 요청자 · 사람의
  기계**(계정 `user`) · `.43` 워커+추론(계정 `sim`). **AXCluster 마운트 시 `.33`도 워커**로
  사용한다(사용자 2026-10-03); 마스터가 요청하며 게임 트리와 분리한 `C:\trunk\AXCluster`만 쓴다.
  [주의] **이 줄은 홈 진입 문서와 중복이다 — 일부러 그렇다.** Codex 는 저장소에서 시작하면
  홈 지침을 싣지 않는다(`docs/orchestrator-rules.md` §3.1). **두 진입 파일은 각각 자족적이어야
  한다** — 한쪽에만 규칙을 추가하지 않는다.
- 이 저장소의 작업 지침 전문은 [`CLAUDE.md`](CLAUDE.md) — **도구 이름이 붙어 있을 뿐
  내용은 도구 무관**이다. Codex 도 그 규칙을 따른다.

## 마스터 실행 환경 · 지휘자 교대

**인프라 변경 요청도 RAG부터 시작한다**(사용자 2026-10-03, #716).
`ax-projects.search_context_tool`로 검색하고 현재 소스와 대조한 뒤 대상·근거·분해안을 보여
**단독(로컬 서브 에이전트) / AX 워커 분산**을 사용자에게 묻는다. 같은 작업에서 이미 정한
방식은 다시 묻지 않는다. 결정한 방식에 맞춰 서브 에이전트를 구성하고 산출물을 직접 검증·기록한다.
분산 준비가 부족하면 선행 정비를 알려 결정받으며, 즉시 파견 가능한 것으로 제시하지 않는다.
골조·소스 경계·검사는 등록 프로필 `kind`(`unreal`/`code`/`index_only`)로 분기한다.
세부 절차: [`master/skills/distribute/SKILL.md`](master/skills/distribute/SKILL.md).

- AX 도구 실행 전 작업 위치를 `/home/sim/ax-cluster` 로 맞춘다. Python 은 `.venv/bin/python` 을 쓴다.
- 프로젝트 CLI 는 환경변수가 필수다. 조회 예:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan NS`
  (`NS` 는 예시다. 대상 프로젝트를 명시한다.) `deliver`·`check` 도 같은 접두를 쓴다.
- 모든 등록 프로젝트·작업장을 현재 HEAD로 맞출 때는 프로젝트를 고르지 않고
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`를 쓴다.
- **관리되는 Codex 자산은 프로젝트 체크아웃 안에도 있다.** 배달은 `<checkout>/.agents/skills`
  와 `<checkout>/.codex/config.toml`을 만들고 `check`가 대조한다(`#699`). 홈의 동명 스킬보다
  프로젝트 로컬 정본이 우선이다. 초기화·배달 뒤 이 둘이 없으면 정상 상태가 아니다.
- 마스터의 공용 호출 창구는 `ax-projects` MCP 다. Codex 설정은 `~/.codex/config.toml`,
  Claude 설정은 `~/.claude.json` 에 있다. 설정 추가만으로 현재 세션에 도구가 생겼다고 판단하지 않는다.
- 워커 지휘자 선택은 `ax-mode` 스킬 → `get_worker_mode_tool` / `set_worker_mode_tool` 이다.
  마스터 대화 세션의 교대와 워커 모드 선택은 별개다. 선택 가능한 값은 `lane`·`claude`·`codex`.
- 배달은 커밋된 깨끗한 트리에서 한다. 문서만 미커밋이어도 `delivered_by.dirty=true` 로 기록된다.
- **AX 인프라 일감은 레드마인 `ax-cluster`(id 3)에 둔다.** 게임·도구 일감은 각 프로젝트의
  `redmine.project`를 따른다. 리뷰 상태는 `<twin>/fixes/index.json`이 정본이며, 오래된 골조
  리뷰를 처리할 때 현재 소스·후속 구현 커밋·회귀 검사를 대조한다.
- **AXCluster 통합 검사는 `tests/integration/checks.json`이 명시 목록이다.** 실행은
  `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
  색인기 단위 검사는 가짜 합성기를 주입하며 실제 브로커 성공에 기대지 않는다.
- **Windows Codex 원격 실행**: `workspace-write` + `windows.sandbox="unelevated"` +
  `sandbox_workspace_write.network_access=true`, `/IT /RL LIMITED` 런처로 **로그인 사용자 세션**에서
  실행한다. “세션 1”은 고정 SessionId가 아니다. SSH 직접 실행·예약 작업 요청 성공을 실증으로
  대신하지 않는다. 실제 셸 읽기·apply_patch 쓰기·결과 회수를 확인한다.
  readiness는 예약 런처의 등록 계약 검사이며 로그인·인증·실행 성공을 보증하지 않는다.
  정본·진단·기억은 [`docs/windows-codex-remote.md`](docs/windows-codex-remote.md).
