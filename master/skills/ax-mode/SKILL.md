---
name: ax-mode
description: AX 워커 **지휘자 모드**를 보고 바꾼다 — 마스터가 SSH 로 워커에 서브태스크를 맡길 때 그 수행을 지휘하는 주체를 `lane`(마스터가 텍스트만 만들어 써 넣음) · `claude` · `codex` 중에서 고른다. "지휘자 바꿔", "코덱스 모드로", "워커 모드 확인", "레인으로 돌려", "/ax-mode" 같은 발화에 발동.
---

# ax-mode — 워커 지휘자 모드

> 마스터가 생성해 배달한다. **손으로 고치지 말 것.**
> 정본: `~/ax-cluster/master/skills/ax-mode/SKILL.md` · 일감 `#385` · 설계 `docs/16-worker-orchestrator-mode.md`

## 0. [중요] 무엇을 고르는 것인가 — 두 층을 섞지 않는다

    지휘자 (이 스킬이 고른다)   워커에서 도는 주체. 체크아웃을 읽고 판단하고 파일을 고치고
                               `ax-work` 스킬을 따른다
    하위 작성 모델 (아니다)     지휘자가 대량 생성을 위임하는 곳 — `codex`→`agy`→로컬
                               (`lanes.DEFAULT_LANES`). **이 스킬은 그것을 바꾸지 않는다**

고를 수 있는 값 셋:

    lane     마스터에서 텍스트만 만들어 워커에 써 넣는다 — 워커에서 도는 에이전트가 **없다**
    claude   워커에서 `claude -p` 가 지휘한다
    codex    워커에서 `codex exec` 가 지휘한다

## 1. 부르는 것은 서버의 한 벌이다

**도구마다 로직을 따로 만들지 않는다** — Claude 세션이든 Codex 세션이든 **같은 MCP 도구**를 부른다:

    조회   get_worker_mode_tool()
    변경   set_worker_mode_tool(mode, why="왜 바꾸는지", by="누가")

실행 전 스킬 경로와 실제 호출을 알린다. 작업 위치는 `/home/sim/ax-cluster`이며 Python은
`.venv/bin/python`을 쓴다. MCP 가 안 붙어 있으면 같은 정본을 직접 부른다:

    AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -c "import json; from master.work import conductor as c; print(json.dumps(c.snapshot(), ensure_ascii=False))"
    AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -c "import json; from master.work import conductor as c; print(json.dumps(c.set_worker('codex', why='사용자가 선택한 변경 사유', by='현재 지휘자'), ensure_ascii=False))"

변경 명령의 모드·사유·기록자는 실제 사용자 선택에 맞춘다. **사용자가 모드를 선택했을 때만**
변경하고, 기존 선택을 다시 묻지 않는다. 마스터 세션 교대만으로 워커 모드를 바꾸지 않는다.
`set_worker()`는 활성 프로젝트의 SSH 워커 준비 검사 후 상태를 저장한다. `mode.set_mode()`나
상태 파일 직접 쓰기로 이 검사를 우회하지 않는다. 실패하면 사유를 보고하고 중단한다.
성공하면 다시 조회해 저장값과 실제 모드·출처를 확인한다.

준비 검사는 배달물과 Windows 예약 런처 등록 계약을 확인한다. 실제 로그인·인증·Codex 셸 읽기·
`apply_patch`·결과 회수 성공은 별도 실행 검증이며, 모드 전환만으로 완료했다고 말하지 않는다.

## 2. [중요] 이것은 기록이지 잠금이 아니다

우선순위는 **인자 > `AX_WORKER_MODE` > 저장 상태 > 현재 동작**이다. 저장 상태를 바꿔도
호출부가 명시한 값이 이긴다. 상태는 `~/.cache/ax-dispatch/mode.json` 에 남고 **재부팅을 넘는다.**

[중요] **조회는 모드와 함께 「출처」를 돌려준다.** 예상과 다르면 그 출처부터 본다 —
환경변수가 걸려 있는지, 저장 상태인지, 아직 아무도 안 정한 「현재 동작」인지.

## 3. [주의] 바꾸기 전에

- **기본값은 아직 사람이 정하지 않았다** (2026-09-08). 저장된 값이 없으면 **현재 동작(레인)**
  으로 돈다. 「기본값이 lane 으로 결정됐다」고 말하지 않는다
- **전역 모드는 새 work 등재의 기본값이다.** 기존 `work.worker_mode` 스탬프와 실행 중 조각에
  소급되지 않는다. 스탬프 없는 옛 work은 전역을 읽을 수 있으므로 구분해 보고한다
- **왜 바꾸는지(`why`)를 반드시 적는다.** 나중에 「왜 이 모드였나」를 그것으로만 알 수 있다
- 지휘자 모드에서는 조각마다 **지휘자 토큰이 든다.** `lane` 은 마스터에서 텍스트만 만들어 싸다

마스터 담당 기록과 인수인계는 [`../ax-handoff/SKILL.md`](../ax-handoff/SKILL.md)에서 처리한다.

## 4. [주의] 계측을 0 으로 읽지 않는다

`codex` 는 토큰은 주지만 **비용(USD)을 주지 않는다.** `cost_usd` 의 `0.0` 은 「공짜」가 아니라
**미상**이고, `cost_known` 이 그것을 가른다. 비용을 합산해 보고할 때 미상을 0 으로 섞지 않는다.
