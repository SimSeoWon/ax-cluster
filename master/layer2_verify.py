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
#
# [중요] **실패 사유는 버리지 않는다 — 이식 누락 복구** (`#285`, 사용자 지적 2026-08-23).
#   원전 `master_orchestrator/common.call_agy` 는 반환 계약 자체가 사유를 실어 보낸다
#   (*"정상 텍스트 / `AgyCooldown: …` / `Error …`"*) 그리고 실패마다 `_mo_log` 를 남긴다 —
#   실행파일 없음(**PATH 미등록**) · PTY 실패 · 쿼터 · rc≠0(stderr 앞 200자)를 **처음부터
#   갈라 놨다**. 우리 이식은 그것을 `None` 하나로 접었다.
#   실측된 대가: NS 리뷰 26건이 *"응답 없음"* 으로 기록됐는데 진짜 원인은 **systemd 유닛에
#   PATH 가 없어 `which` 가 실패**한 것이었다. 사유가 틀리면 고칠 곳도 틀린다 —
#   「서비스가 죽었나」를 파게 된다. 없는 로그보다 **틀린 로그가 더 비싸다.**
#   [주의] 그래서 `None` 은 유지하되(호출부의 fail-closed 계약) **사유를 함께** 돌려준다.

_LOGF = None            # 주입 자리. 없으면 stderr — 저널에 실린다(유닛이 그것을 잡는다)


def _log(msg: str) -> None:
    """실패 사유를 **반드시 어딘가에 남긴다.** 원전 `_mo_log` 대응."""
    if _LOGF is not None:
        try:
            _LOGF(msg)
            return
        except Exception:                                    # noqa: BLE001
            pass
    print(f"[layer2] {msg}", file=sys.stderr, flush=True)


def _run(cmd: list[str], *, timeout: int) -> tuple:
    """`(출력, 사유)`. 성공이면 `(텍스트, "")`, 실패면 `(None, 사유)`.

    [중요] 네 갈래를 **가른다** — 종전에는 전부 `None` 이었다. 특히 `rc != 0` 에서 **stderr 를
    버렸다**: CLI 가 무엇이라 말했는지가 사라져 원인 추적이 불가능했다(원전은 앞 200자를 싣는다).
    """
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"타임아웃 {timeout}초"
    except OSError as e:
        return None, f"실행 실패 — {type(e).__name__}: {e}"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip().replace("\n", " ")
        return None, f"rc={r.returncode}: {err[:200] or '(출력 없음)'}"
    if not (r.stdout and r.stdout.strip()):
        return None, "빈 출력 (rc=0)"
    return r.stdout, ""


def call_agy(prompt: str, *, timeout: int = TIMEOUT_SEC) -> str | None:
    """`agy` 호출. [주의] `-p` 는 **반드시 프롬프트 직전**에 둔다 — 앞에 두면 다음 토큰을
    프롬프트 값으로 먹는다(2026-08-08 실측)."""
    out, why = call_agy_why(prompt, timeout=timeout)
    return out


def call_agy_why(prompt: str, *, timeout: int = TIMEOUT_SEC) -> tuple:
    """`(출력, 사유)`. 사유는 실패했을 때만 채워진다."""
    exe = shutil.which("agy")
    if not exe:
        why = MISSING_EXE                      # [중요] 쿨다운 대상이 아니다 — 설정 오류다
        _log(f"[agy] {missing_exe_hint('agy')}")
        return None, why
    out, why = _run([exe, "--dangerously-skip-permissions", "-p", prompt], timeout=timeout)
    if out is None:
        _log(f"[agy] 실패 — {why}")
    return out, why


def call_claude(prompt: str, *, timeout: int = TIMEOUT_SEC, model: str = "") -> str | None:
    """`claude -p` 호출. `model` 을 주면 `--model` 로 넘긴다(별칭 `opus`·`sonnet` 실측 통과).

    [중요] **층2 는 model 을 주지 않는다** — 검증기 모델을 여기서 고정하면 소 2.2.1(모델 선정)이
    코드에 박히는 셈이다. 지정은 호출자 몫이다.
    """
    out, why = call_claude_why(prompt, timeout=timeout, model=model)
    return out


def call_claude_why(prompt: str, *, timeout: int = TIMEOUT_SEC, model: str = "") -> tuple:
    """`(출력, 사유)`."""
    exe = shutil.which("claude")
    if not exe:
        why = MISSING_EXE
        _log(f"[claude] {missing_exe_hint('claude')}")
        return None, why
    cmd = [exe, "-p"]
    if (model or "").strip():
        cmd += ["--model", model.strip()]
    out, why = _run(cmd + [prompt], timeout=timeout)
    if out is None:
        _log(f"[claude] 실패 — {why}")
    return out, why


# [중요] **실행파일 부재는 다른 부류다.** 쿨다운(600초)을 걸어도 600초 뒤에 생기지 않는다 —
#   고칠 곳이 코드가 아니라 **환경**(PATH · 설치)이다. 그래서 사유를 상수로 두고 호출부가
#   구별할 수 있게 한다.
#
# [중요] **사유에 OS 를 박지 않는다** (사용자 정정 2026-08-23). 이 모듈은 마스터(리눅스)와
#   작업장 `.2`·`.33`(윈도우) **양쪽에서 돈다** — 층2 판정·리뷰가 그렇다. 첫 구현은
#   *"systemd 유닛은 PATH 를 상속하지 않는다"* 를 상수에 박았는데, 윈도우에는 systemd 가
#   없으므로 그 문장은 **거기서 거짓이고 엉뚱한 곳을 파게 만든다.** 「없는 로그보다 틀린 로그가
#   비싸다」를 적어 놓고 같은 것을 만든 자리다. 원인도 OS 마다 다르다:
#
#     리눅스   서비스가 로그인 셸을 안 거쳐 `~/.local/bin` 이 PATH 에 없다
#              → 해법은 실행 파일을 시스템 경로에 두는 것(`/usr/local/bin` 심링크)
#     윈도우   작업 스케줄러·세션 0 의 환경이 사용자 셸과 다르고, `PATHEXT`(`.cmd`/`.exe`)도
#              걸린다 → 심링크 해법은 **여기 적용되지 않는다**(머신 문서에서 따로 판단)
MISSING_EXE = "실행파일 없음 — PATH 에서 찾지 못했다"


def missing_exe_hint(name: str = "") -> str:
    """부재 사유에 붙일 **플랫폼별 힌트.** 사실만 적고 처방은 머신 문서로 넘긴다."""
    what = f"`{name}` " if name else ""
    if sys.platform.startswith("win"):
        return (f"{what}실행파일을 PATH 에서 찾지 못했다 — 윈도우: 서비스·작업 스케줄러의 "
                "환경은 사용자 셸과 다르다 (PATHEXT 도 확인)")
    return (f"{what}실행파일을 PATH 에서 찾지 못했다 — 리눅스: 서비스는 로그인 셸을 거치지 "
            "않으므로 `~/.local/bin` 이 PATH 에 없다 (시스템 경로에 두는 것이 해법)")

WHY_BACKENDS = [("agy", call_agy_why), ("claude", call_claude_why)]


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
