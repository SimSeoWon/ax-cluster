"""층2 검증 — 상용 모델로 로컬 LLM 작성분을 검사한다. **fail-closed** (PLAN.md §4.3 · §8.3 · §9.4.3).

AgentTest `worker/claude_spawn.py:syntax_check` 의 이식판이되 판정 계약이 다르다:

| | AgentTest `syntax_check` | 여기 |
|---|---|---|
| 응답 형식 | 아무 데서나 `{"ok":...}` JSON 탐색 | 마지막 줄 `VERDICT: ...` (`verdict.py`) |
| 파싱 실패 | `None` → 호출자가 **통과 처리** | **차단** |
| 백엔드 부재 | `checked=False, ok=True` → **통과** | **차단** |

백엔드 순서는 `agy` → `claude`. 둘 다 상용이라 **교차 계열 조건**(리뷰어는 작성자와 다른 계열)이
작성자가 BC-250 로컬 LLM 일 때 자동으로 만족된다.

사용:
    from layer2_verify import verify_files
    v = verify_files([("Combat.cpp", src)])
    if v.blocked: ...     # v.failure 가 있으면 계약 위반, 없으면 실제 지적
"""
from __future__ import annotations

import os
import shutil
import time
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from verdict import Verdict, contract_text, parse_verdict  # noqa: E402

TIMEOUT_SEC = int(os.environ.get("AX_LAYER2_TIMEOUT", "300"))
MAX_FILE_CHARS = 16000


def build_prompt(files: list[tuple[str, str]], *, declarations: str = "") -> str:
    """UE5/C++ 문법 검사 프롬프트 + 판정 계약.

    AgentTest 와 같은 범위를 본다 — **컴파일을 깨뜨리는 것만**. 로직·스타일·설계는 보지 않는다
    (그건 층3 빌드/RunTests 와 사람의 몫이다).

    [중요] **`declarations` 가 검출력을 갈랐다** (실측 2026-08-12, 소 2.2.1). 같은 표본을 후보 5개에
    돌렸더니 **넷이 "없는 열거값"(`EMissionType::None`, 실제 멤버는 `Main`/`Sub`)을 놓쳤다** —
    파일만 주면 그 열거형의 정의를 모르니 추측할 수밖에 없다. 선언부를 함께 준 변형에서는
    `agy`·`sonnet`·`opus`·35B 가 **전부 잡았다.**

    즉 **차이를 만드는 것은 모델이 아니라 grounding 이다** — 골조 게이트에서 배운 것과 같다
    (*"이름만 대고 내용을 안 줬더니 열거값을 지어냈다"*, 리포트 12 §6.3 ③). 층2 도 같은 재료를
    받아야 같은 부류를 잡는다. [주의] 안 주면 문법만 보는 검사기가 된다.
    """
    parts = [
        "You are a strict C++/Unreal Engine 5 SYNTAX checker.",
        "Report ONLY problems that would BREAK COMPILATION:",
        "- C++ syntax: unbalanced braces/parens, missing semicolons, malformed declarations, obvious type errors",
        "- UE5 reflection macros: malformed/misused UCLASS/USTRUCT/UENUM/UFUNCTION/UPROPERTY/GENERATED_BODY",
        "- leftover markdown fences (```), leftover [PSEUDO]/[FEEDBACK] placeholders, truncated/empty bodies",
        "Do NOT comment on logic, style, naming, design, or performance.",
        "",
        contract_text(),
        "",
    ]
    if (declarations or "").strip():
        # [중요] **선언부를 파일보다 앞에** 둔다 — 뒤에 둘 이유가 없다. 판정 대상(파일)이 지시에
        #    가까워야 하고, 선언부는 *대조표*라서 먼저 읽혀야 한다.
        parts += ["=== DECLARATIONS FROM INCLUDED HEADERS (authoritative) ===",
                  "These are the REAL definitions. Any member/enum value not listed here "
                  "does not exist. Report it as a compile error.",
                  declarations.strip(),
                  "=== END DECLARATIONS ===", ""]
    for rel, content in files:
        body = content if len(content) <= MAX_FILE_CHARS else content[:MAX_FILE_CHARS] + "\n...(truncated)"
        parts += [f"=== {rel} ===", body, ""]
    return "\n".join(parts)


# ── 백엔드 ──────────────────────────────────────────────────
# 각 백엔드는 성공 시 응답 텍스트, 실패 시 None 을 돌린다. None 은 verdict.parse_verdict 가
# fail-closed 로 받는다 — 여기서 임의로 통과시키지 않는다.

def _run(cmd: list[str], *, timeout: int) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout if (r.stdout and r.stdout.strip()) else None


def call_agy(prompt: str, *, timeout: int = TIMEOUT_SEC) -> str | None:
    """`agy` 호출. [주의] `-p` 는 **반드시 프롬프트 직전**에 둔다 — 앞에 두면 다음 토큰을
    프롬프트 값으로 먹는다(2026-08-08 실측)."""
    exe = shutil.which("agy")
    if not exe:
        return None
    return _run([exe, "--dangerously-skip-permissions", "-p", prompt], timeout=timeout)


def call_claude(prompt: str, *, timeout: int = TIMEOUT_SEC, model: str = "") -> str | None:
    """`claude -p` 호출. `model` 을 주면 `--model` 로 넘긴다(별칭 `opus`·`sonnet` 실측 통과).

    [중요] **층2 는 model 을 주지 않는다** — 검증기 모델을 여기서 고정하면 소 2.2.1(모델 선정)이
    코드에 박히는 셈이다. 지정은 호출자 몫이다.
    """
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "-p"]
    if (model or "").strip():
        cmd += ["--model", model.strip()]
    return _run(cmd + [prompt], timeout=timeout)


# [중요] **순서를 실측으로 확인했다** (2026-08-12, 소 2.2.1 · `bench_layer2.py`).
#   표본 7개(양성 5 · 음성 2, 전부 이 프로젝트에서 실제로 났던 실패)로 후보 5개를 재 봤다:
#
#     agy            검출 4/5 · 오탐 0 · 78초     ← 같은 점수에 가장 싸다 → **1순위**
#     claude:sonnet  검출 4/5 · 오탐 0 · 91초     ← 동점 → 폴백
#     claude:opus    검출 4/5 · 오탐 0 · 76초     ← 동점. 비싼 값을 할 이유가 없다
#     qwen 14b       검출 3/5 · 오탐 0 · 50초     [중요] 선언부를 줘도 열거값을 못 잡았다
#     35B            검출 4/5 · [중요] **오탐 2** · 380초  [중요] **정상 코드를 둘 다 막았다** → 탈락
#
# [중요] 상용 셋이 **동점**이라 검출력으로 고를 이유가 없다 → 싸고 빠른 쪽을 먼저 쓴다. 그리고
#   로컬은 층2 에 못 쓴다는 것이 실측으로 확인됐다 — *"검증에만 상용 토큰"* 모토가 추측이
#   아니라 근거를 갖게 됐다. [주의] 35B 처럼 **정상 작업을 막는 게이트는 통과시키는 게이트보다
#   나쁘다** — 그 판단은 사실 게이트에서 이미 내렸다.
BACKENDS = [("agy", call_agy), ("claude", call_claude)]


# ── 소 2.2.3 쿨다운 — [중요] 죽은 백엔드를 조각마다 다시 두드리지 않는다 ────────────
#
# 층2 는 **조각마다** 돈다. 상용 CLI 가 쿼터로 죽었으면 조각 N개 × 타임아웃(기본 300초)을
# 그대로 버린다 — 실패가 확실한 호출에 시간을 쓰는 것이다. 한 번 실패한 백엔드는 잠시 건너뛴다.
#
# [중요] **쿨다운은 통과 사유가 아니다.** 전부 쿨다운이면 `no_backend` 로 **차단**된다 —
#   "확인하지 못했다" 를 "괜찮다" 로 바꾸는 순간 이 게이트는 없는 것과 같다(§9.4.4).
#   [주의] 그 차단이 값싼 이유는 **스풀이 응답을 들고 있어서**다(소 1.3.3) — 나중에 다시 돌리면
#   추론을 다시 사지 않는다. fail-closed 의 비용이 재시도 한 번인 구조라 막아도 된다.

COOLDOWN_SEC = int(os.environ.get("AX_LAYER2_COOLDOWN", "600"))
_cooldown: dict[str, float] = {}


def cooldown_state() -> dict:
    """`{백엔드: 남은 초}`. 관측용 — 왜 건너뛰는지 사람이 볼 수 있게."""
    now = time.time()
    return {k: round(v - now, 1) for k, v in _cooldown.items() if v > now}


def clear_cooldown() -> None:
    _cooldown.clear()


def verify_files(files: list[tuple[str, str]], *, timeout: int = TIMEOUT_SEC,
                 backends=None, declarations: str = "",
                 cooldown_sec: int = COOLDOWN_SEC) -> Verdict:
    """층2 검증 실행. `files=[(상대경로, 내용)]`.

    백엔드를 순서대로 시도하되 **"응답이 없는 것"과 "판정을 못 낸 것"을 구분한다:**
    응답 자체가 없으면 다음 백엔드로 넘어가고, 응답은 왔는데 계약을 어겼으면 **거기서 차단**한다
    (계약을 어기는 검증기를 다음 백엔드로 덮어주면 fail-open 이 되살아난다).
    """
    prompt = build_prompt(files, declarations=declarations)
    attempted: list[str] = []
    skipped: list[str] = []
    now = time.time()
    # `backends or BACKENDS` 로 쓰면 안 된다 — 빈 목록이 falsy 라 "백엔드 없음"이 조용히
    # 기본 체인으로 바뀐다. 호출자가 백엔드를 동적으로 계산해 빈 목록이 나온 경우 fail-open 이다.
    for name, fn in (BACKENDS if backends is None else backends):
        until = _cooldown.get(name, 0.0)
        if until > now:
            skipped.append(f"{name}(쿨다운 {until - now:.0f}초)")
            continue
        raw = fn(prompt, timeout=timeout)
        attempted.append(name)
        if raw is None:
            # [중요] 미가용을 기억한다 — 다음 조각에서 같은 타임아웃을 또 쓰지 않는다
            if cooldown_sec > 0:
                _cooldown[name] = time.time() + cooldown_sec
            continue
        _cooldown.pop(name, None)         # 되살아났으면 쿨다운을 푼다
        v = parse_verdict(raw, backend=name)
        v.warnings.append(f"backend={name}")
        if skipped:
            v.warnings.append("건너뜀: " + ", ".join(skipped))
        return v
    warn = [f"시도한 백엔드: {', '.join(attempted) or '없음'}"]
    if skipped:
        warn.append("건너뜀: " + ", ".join(skipped))
    return Verdict(approved=False, failure="no_backend", warnings=warn)


if __name__ == "__main__":
    _BROKEN = """void AFoo::Tick(float Dt) {
    Super::Tick(Dt)
    if (IsValid(Target) {
        Target->Ping();
    }
"""
    _OK = """void AFoo::Tick(float Dt)
{
    Super::Tick(Dt);
    if (IsValid(Target))
    {
        Target->Ping();
    }
}
"""
    for label, src in [("문법 오류 있음", _BROKEN), ("정상 코드", _OK)]:
        v = verify_files([("Foo.cpp", src)])
        print(f"\n[{label}] → {v.summary()}")
        for f in v.findings:
            print(f"    · {f}")
        if v.warnings:
            print(f"    (warn: {'; '.join(v.warnings)})")
