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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from verdict import Verdict, contract_text, parse_verdict  # noqa: E402

TIMEOUT_SEC = int(os.environ.get("AX_LAYER2_TIMEOUT", "300"))
MAX_FILE_CHARS = 16000


def build_prompt(files: list[tuple[str, str]]) -> str:
    """UE5/C++ 문법 검사 프롬프트 + 판정 계약.

    AgentTest 와 같은 범위를 본다 — **컴파일을 깨뜨리는 것만**. 로직·스타일·설계는 보지 않는다
    (그건 층3 빌드/RunTests 와 사람의 몫이다).
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
    """`agy` 호출. ⚠️ `-p` 는 **반드시 프롬프트 직전**에 둔다 — 앞에 두면 다음 토큰을
    프롬프트 값으로 먹는다(2026-08-08 실측)."""
    exe = shutil.which("agy")
    if not exe:
        return None
    return _run([exe, "--dangerously-skip-permissions", "-p", prompt], timeout=timeout)


def call_claude(prompt: str, *, timeout: int = TIMEOUT_SEC) -> str | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    return _run([exe, "-p", prompt], timeout=timeout)


BACKENDS = [("agy", call_agy), ("claude", call_claude)]


def verify_files(files: list[tuple[str, str]], *, timeout: int = TIMEOUT_SEC,
                 backends=None) -> Verdict:
    """층2 검증 실행. `files=[(상대경로, 내용)]`.

    백엔드를 순서대로 시도하되 **"응답이 없는 것"과 "판정을 못 낸 것"을 구분한다:**
    응답 자체가 없으면 다음 백엔드로 넘어가고, 응답은 왔는데 계약을 어겼으면 **거기서 차단**한다
    (계약을 어기는 검증기를 다음 백엔드로 덮어주면 fail-open 이 되살아난다).
    """
    prompt = build_prompt(files)
    attempted: list[str] = []
    # `backends or BACKENDS` 로 쓰면 안 된다 — 빈 목록이 falsy 라 "백엔드 없음"이 조용히
    # 기본 체인으로 바뀐다. 호출자가 백엔드를 동적으로 계산해 빈 목록이 나온 경우 fail-open 이다.
    for name, fn in (BACKENDS if backends is None else backends):
        raw = fn(prompt, timeout=timeout)
        attempted.append(name)
        if raw is None:
            continue                       # 백엔드 미가용 — 다음으로
        v = parse_verdict(raw, backend=name)
        v.warnings.append(f"backend={name}")
        return v
    return Verdict(approved=False, failure="no_backend",
                   warnings=[f"시도한 백엔드: {', '.join(attempted) or '없음'}"])


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
