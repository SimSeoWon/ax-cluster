# 56 — `codex exec` 를 워커 지휘자로 쓸 수 있나 (실측)

작성 2026-09-08 · 일감 [`#385`](http://192.168.0.57:8080/issues/385) · 변경안 `docs/16-worker-orchestrator-mode.md`

사용자 요구: **마스터가 SSH 로 워커에 서브태스크를 맡길 때, 그 수행을 지휘하는 주체를
Claude / Codex 중에서 고른다.** [중요] `#384`(마스터 **대화 세션** 인수인계)와 **별개 축**이다.

---

## 56.1 먼저 — 「지휘자」와 「하위 작성 모델」이 코드에서 갈리는 자리

    지휘자 (워커에서 도는 에이전트 · SSH)
      runner.py:285  worker_command()   claude -p --output-format json
                                        --dangerously-skip-permissions "<INSTRUCTION>"
      infer.py:172   infer_command()    같은 모양 · 지시문만 다르다
      → 체크아웃을 읽고 판단하고 파일을 고친다 · `ax-work` 스킬을 따른다 · git 은 금지
      🔴 **`claude` 하드코딩 — 갈래가 없다**

    하위 작성 모델 (마스터에서 텍스트만 생성)
      lanes.py:73    DEFAULT_LANES = ("codex", "agy", "qwen2.5-coder:14b")
      → `bundle._remote_write`(scp + sha256)로 워커에 써 넣는다. 워커 에이전트 없음

[중요] **`ax-work` 스킬이 지휘자의 존재를 이미 못박고 있다** (§0 ②④):
*"마스터의 작업 요청은 네가 1차로 받고, **네가 오케스트레이션한다**"* ·
*"너 혼자 다 하지 않는다 — 대량 생성은 `codex`→`agy`→로컬에 **위임하고 너는 검증한다**"*.
즉 사용자 요구는 새 개념이 아니라 **스킬에 적혀 있는데 코드가 못 고르는 것**이다.

🔴 [주의] **정상 파견에는 지금 워커 지휘자가 없다.** `infer.py:804-810` — 레인이 기본 경로이고
`run_worker`(지휘자)는 **골조를 못 읽었을 때의 폴백**이다. 스위치만 만들면 평소에 안 타는
경로를 바꾸게 된다.

---

## 56.2 실측 — 세 검증

측정 방법: 격리된 임시 git 저장소에 `[DOC]`/`[PSEUDO]` 골조를 놓고 **실제 지시문과 같은 모양**
으로 시켰다. 잔재는 전부 지웠다(`.43` `.2` 확인 출력).

### ⓐ 기본 실행 — 워커 두 대 통과

|  | `.43` (Fedora) | `.2` (Windows) |
|---|---|---|
| `codex-cli` | 0.153.4 · 인증 O | 0.153.4 · 인증 O |
| 비대화형 SSH 실행 | 통과 | 통과 |
| 파일 실제 수정 | 통과 | 통과 |
| `git` 금지 준수 | 지킴 | 지킴 |
| `RESULT: DONE` 마커 | 정확히 출력 | 정확히 출력 |
| 토큰 계측 | `tokens used 4,715` | `tokens used 6,011` |

실행 형태: `codex exec --dangerously-bypass-approvals-and-sandbox -C <dir> "<지시>" < /dev/null`
(윈도우는 `< NUL`). `.43` 에는 `~/.codex/config.toml` 이 **없는데도** `-C` 로 준 디렉토리에서 돌았다.

[주의] **이번에는 그 옵션으로 성공한 것이다.** 무인 실행에 실제로 필요한 **권한 범위는 아직
안 좁혔다** — `-s workspace-write` 로도 되는지 재지 않았다. (`#385` 완료 조건 3)

### ⓑ 윈도우 한글 골조 — 통과

한글 `[DOC]`/`[PSEUDO]` 가 든 `.h` 를 **바이트째 scp**(sha256 3자 일치)하고 영문 지시로 시켰다.

    [PSEUDO] Max 가 0 이면 0 을 반환하고, 아니면 Cur / Max 를 실수로 계산해 반환한다.
      → float Ratio(int Cur, int Max) { return Max == 0 ? 0.0f : static_cast<float>(Cur) / Max; }

결과 파일 회수해 대조: **UTF-8 유지 · 주석 4줄 바이트 동일 · 한글 조건을 실제로 이해했다.**

[중요] **초판의 「윈도우에서 한글이 깨진다」는 내 프로브의 결함이었다.** `.ps1` 을 UTF-8 로
보냈는데 PowerShell 이 코드페이지로 읽어 **커밋 전에 이미 `?` 가 됐다**(git blob 바이트
`3F 3F …`). codex 는 한글을 본 적이 없었다. 도구를 탓하기 전에 하네스를 의심할 것.

### ⓒ `ax-work` 스킬 준수 — 통과 (갈래를 만들 필요가 없다)

스킬 §1 의 *"`./.ax/config.json` 이 없으면 추측하지 말고 **멈춘다**"* 를 판정 기준으로 삼았다.
없으면 멈추는가 = 스킬을 읽고 따르는가.

    Run A  스킬 O · config X   →  `cat ./.ax/config.json` 시도 → 없음 확인 →
                                 스킬 경로를 인용하고 한글 규칙("없으면 추측하지 말고 멈춘다")을
                                 근거로 **RESULT: BLOCKED** · 파일 변경 0
    Run B  스킬 O · config O   →  구현 진행. 층1 기준 대조:
                                   `[PSEUDO]` 잔재 0 · `[DOC]` 2건 보존 ·
                                   **선언 동결 유지**(`.h` 선언 2건 그대로) · git 미조작

[중요] **`.claude/skills/ax-work/SKILL.md` 를 찾아 읽었다** — Claude 형식의 경로인데도 된다.
[주의] 다만 **자동 로드가 아니라 탐색**이다. 지시문이 이름을 대고 에이전트가 파일을 찾았다.
배달이 스킬을 체크아웃에 두므로 지금 배선 그대로 성립하지만, **「자동으로 실린다」고 적으면
안 된다.**

### ⓓ 계측 — 형태가 다르고 **비용이 없다**

`codex exec --json` 은 JSONL 이벤트 스트림이다(단일 JSON 이 아니다):

    thread.started   turn.started   item.completed   turn.completed

    item.completed  → {"item": {"type": "agent_message", "text": "…"}}     ← 본문
    turn.completed  → {"usage": {"input_tokens", "cached_input_tokens",
                                 "cache_write_input_tokens", "output_tokens",
                                 "reasoning_output_tokens"}}                ← 토큰

`Outcome` 이 요구하는 형태(`runner.py:105-118`)와의 매핑:

    input_tokens                 ← usage.input_tokens
    output_tokens                ← usage.output_tokens
    cache_creation_input_tokens  ← usage.cache_write_input_tokens
    cache_read_input_tokens      ← usage.cached_input_tokens
    total_cost_usd               ← 🔴 **없다** (`cost`/`usd` 문자열 0건)

🔴 [중요] **비용 부재를 0 으로 접으면 안 된다.** `Outcome.cost_usd` 는
`float(usage.get("total_cost_usd") or 0.0)` 이라 **미상이 「공짜」로 읽힌다.** 기존 계약은
*"비어 있으면 모른다는 뜻"*(`runner.py:105`)인데, codex 는 usage 가 **있으면서** 비용만 없다.
→ 변경안에서 `cost_unknown` 을 실어 0 과 미상을 가른다.

---

## 56.3 결론과 남은 것

**기본 실행·한글·스킬 준수는 확인됐다.** 남은 것은 셋이고, **하나도 실행 가능성 문제가 아니다**:

1. **권한 범위** — 무인 실행에 실제로 필요한 최소 샌드박스를 못 좁혔다
2. **계측 파서** — JSONL 갈래 + 비용 미상 표기
3. **실제 파견 통합** — 정상 파견에서 지휘자가 돌게 하는 것 (레인과의 관계 결정)

[주의] 초판에 *"기술적 장벽은 없다"* 라고 적었던 것은 과했다 — 기본 실행이 확인된 것이고,
스킬·인코딩·계측·파견 통합은 **그때 아직 안 잰 것**이었다(사용자 정정 2026-09-08).

→ 변경안: `docs/16-worker-orchestrator-mode.md`
