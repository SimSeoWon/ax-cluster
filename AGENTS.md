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
  기계: `.57` 마스터(이 저장소) · `.2` 워커+추론(계정 `janus`, UE5) · `.33` **요청자 · 사람의
  기계, 파견 대상 아님**(계정 `user`) · `.43` 워커+추론(계정 `sim`).
  [주의] **이 줄은 홈 진입 문서와 중복이다 — 일부러 그렇다.** Codex 는 저장소에서 시작하면
  홈 지침을 싣지 않는다(`docs/orchestrator-rules.md` §3.1). **두 진입 파일은 각각 자족적이어야
  한다** — 한쪽에만 규칙을 추가하지 않는다.
- 이 저장소의 작업 지침 전문은 [`CLAUDE.md`](CLAUDE.md) — **도구 이름이 붙어 있을 뿐
  내용은 도구 무관**이다. Codex 도 그 규칙을 따른다.

## 마스터 실행 환경 · 지휘자 교대

- AX 도구 실행 전 작업 위치를 `/home/sim/ax-cluster` 로 맞춘다. Python 은 `.venv/bin/python` 을 쓴다.
- 프로젝트 CLI 는 환경변수가 필수다. 조회 예:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client plan NS`
  (`NS` 는 예시다. 대상 프로젝트를 명시한다.) `deliver`·`check` 도 같은 접두를 쓴다.
- 마스터의 공용 호출 창구는 `ax-projects` MCP 다. Codex 설정은 `~/.codex/config.toml`,
  Claude 설정은 `~/.claude.json` 에 있다. 설정 추가만으로 현재 세션에 도구가 생겼다고 판단하지 않는다.
- 워커 지휘자 선택은 `ax-mode` 스킬 → `get_worker_mode_tool` / `set_worker_mode_tool` 이다.
  마스터 대화 세션의 교대와 워커 모드 선택은 별개다. 선택 가능한 값은 `lane`·`claude`·`codex`.
- 배달은 커밋된 깨끗한 트리에서 한다. 문서만 미커밋이어도 `delivered_by.dirty=true` 로 기록된다.
