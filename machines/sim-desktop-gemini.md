# GEMINI.md — sim-desktop 홈 (Antigravity 전용 진입)

    AX-ENTRY-MARK: home-gemini

> 이 파일은 **Antigravity 만** 읽는다(Claude 는 `CLAUDE.md`, Codex 는 `AGENTS.md`). 정본은 저장소
> `machines/sim-desktop-gemini.md`, 홈 `GEMINI.md` 는 그 심볼릭 링크다 — 일반 파일로 덮지 않는다.

## 작업 저장소의 진입 지침을 먼저 읽는다 (사용자 2026-11-08)

Antigravity 는 **시작한 폴더의 지침 파일만** 자동 로드한다(#920 실측). 홈에서 시작하면 작업할 저장소의 규칙이
컨텍스트에 없다. 그래서 작업 저장소가 정해지는 순간, 다른 일보다 먼저 그 저장소의 진입 지침을 읽는다.

1. **작업 저장소를 찾는다** — 경로를 짐작하거나 고정값을 쓰지 않는다.
   - 일감 작업이면 `issue_start` 응답의 `repo`(일감 worktree)가 작업 위치다.
   - 그 밖에는 사용자 지시·스킬이 정한 작업 위치에서 `git -C <작업 위치> rev-parse --show-toplevel` 로 루트를 얻는다.
2. **그 루트의 진입 지침을 읽는다** — `rg --files <루트> -g AGENTS.md -g CLAUDE.md --max-depth 1` 로 실제 목록을
   확인한 뒤, 나온 `AGENTS.md`(없으면 `CLAUDE.md`)를 읽는다. 지침 안의 `AX-ENTRY-MARK` 값을 확인해 보고에 한 줄
   남긴다(예: `진입 지침: <루트>/AGENTS.md · AX-ENTRY-MARK: repo`).
3. 작업 저장소가 바뀌면(다른 프로젝트·다른 worktree) 1~2를 다시 한다. 읽기 전에는 그 저장소에서 편집·커밋하지 않는다.

## 일감 시작과 Argon 위임 (사용자 결정 2026-11-08, #920)

- 일감은 `ax-projects:issue_start_tool` 로 시작한다. `issue_flow.start` 직접 호출은 출처가 없어 거절된다.
  MCP 가 안 보이면 우회하지 말고 보고한다. 설정은 `python -m master.client master-local --apply` 가 만든다.
- 코드 구현·복합 추론은 Argon(`gemini-4-argon-medium`) 서브에이전트에 맡기고 산출물은 지휘 세션이 검증한다.
  Argon 이 한도(429·쿨다운)에 걸리면 Flash High 로 바꾸고 보고한다. 자동 경로(리뷰·합성·층2·레인)는 Argon 금지다.

## 사용자 요청·판단 시점 및 태스크 단위 완결 원칙 (사용자 결정 2026-11-08)

- **상호작용 타이밍 고정**: 사용자와의 질의/승인 요청은 오직 **① 일 시작할 때(태스크 착수/플랜 승인)**와 **② 일 끝났을 때(태스크 완료/결과 판단 보고)** 둘로 고정한다.
- **에러 시 예외 보고**: 작업 중 rc≠0, 차단, 예외 등 실패가 발생했을 때만 예외적으로 즉시 멈추고 사유를 보고한다.
- **도구 호출 단위 중간 요청 절대 금지**: 태스크를 수행하는 도중 코드 한 줄, 파일 편집(`edit_file`, `write_file`), 도구 호출마다 턴을 끊거나 사용자에게 중간 승인을 요청하지 않는다. 태스크 내부 구현·검증은 에이전트가 자율적으로 한 호흡에 완결한다.
- **환경 설정**: 파일 편집 자동 승인은 `~/.gemini/antigravity-cli/settings.json` 의 `"toolPermission": "accept-edits"` 다 (CLI 플래그는 `--mode accept-edits`). 설정 파일의 `"mode"` 키만으로는 적용되지 않는다 — 기동 로그의 `CLI settings initialized: … toolPermission=` 값으로 확인한다(2026-11-11 실측: 키가 없어 `request-review` 로 떴다).

## 공용 문서·다른 도구 설정을 건드리지 않는다 (사용자 지시 2026-11-11)

- Antigravity 자체의 도구 권한·설정·승인 팝업·CLI 특성은 `~/.gemini/antigravity-cli/` 와 이 파일 안에서만 다룬다.
- Claude·Codex·Antigravity 가 함께 읽는 `CLAUDE.md`·`AGENTS.md`·`docs/orchestrator-handoff.md`·`docs/orchestrator-rules.md` 와 공용 코드(`master/client/master_local.py` 등)에 Antigravity 설정 문제를 적거나 반영을 제안하지 않는다.
- 인수인계서에는 AX 작업 상태만 적는다. 다른 지휘자가 적은 항목을 지우지 않는다.
- Claude·Codex 의 설정 파일(`~/.claude*`·`~/.codex`)은 건드리지 않는다.
