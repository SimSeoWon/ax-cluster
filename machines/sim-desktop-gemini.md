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
