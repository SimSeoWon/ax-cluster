"""레인 토큰 계측 — **어느 모델이 얼마를 썼나**를 실측으로 남긴다 (사용자 결정 2026-09-05).

## 왜 필요한가

사용자 물음: *"클로드는 오케스트레이션만 담당하고 코덱스가 실제 작업을 처리하면 클로드의 토큰
사용량을 크게 줄일 수 있을까? 아니면 불필요하게 인바운드 토큰을 양쪽에 낭비하는걸까?"*

**추정으로 답할 수 없는 질문이다.** 코딩 세션의 비용은 출력이 아니라 **입력(읽기)** 이고,
위임하면 같은 맥락을 양쪽이 읽는다. 그래서 「줄었다」는 **양쪽 토큰을 같이 재야만** 말할 수 있다.

## [중요] 여기서 재는 것과 못 재는 것

    잰다      레인 CLI 호출 — `claude -p` · `agy -p` · `codex exec` (본문 작성 · 골조 생성)
    못 잰다   `.33` 의 **대화형 세션** — 사람과 주고받는 그 자리는 마스터가 볼 수 없다

[주의] 못 재는 쪽이 오늘 실측의 병목(골조 작성 65%)이다. 그래서 A/B 는 **CLI 로 생성한 골조**로
해야 비교가 성립한다 — 대화형 세션과 CLI 를 섞어 재면 두 변수가 한꺼번에 움직인다.

## 형식이 셋 다 다르다 (실측 2026-09-05)

    claude   `--output-format json` → {"result": 본문, "usage": {input_tokens, output_tokens,
             cache_read_input_tokens, …}, "total_cost_usd": 0.0215}
    agy      `--output-format json` → {"response": 본문, "usage": {input_tokens, output_tokens,
             cache_read_tokens, total_tokens}}   ← 키 이름이 claude 와 다르다
    codex    텍스트 안에 `tokens used\\n5,022` 로 찍힌다 (JSON 출력 없음)

[중요] **못 읽으면 0 이 아니라 `None` 이다.** 0 으로 적으면 「안 썼다」로 읽히고, 그것이
이 저장소가 반복해 치른 「조용한 0」이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field

TIMEOUT = 1800
_CODEX_TOKENS = re.compile(r"tokens used\s*\n\s*([\d,]+)")


@dataclass
class Usage:
    """한 번의 CLI 호출이 쓴 것. [중요] 모르는 값은 `None` — 0 과 구분한다."""

    lane: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    note: str = ""                      # 왜 못 읽었나

    @property
    def known(self) -> bool:
        return self.total_tokens is not None or self.input_tokens is not None

    def summary(self) -> str:
        if not self.known:
            return f"{self.lane} 토큰 미상({self.note or '형식 불명'})"
        parts = []
        if self.input_tokens is not None:
            parts.append(f"입력 {self.input_tokens:,}")
        if self.output_tokens is not None:
            parts.append(f"출력 {self.output_tokens:,}")
        if self.cache_read:
            parts.append(f"캐시읽기 {self.cache_read:,}")
        if self.total_tokens is not None:
            parts.append(f"합계 {self.total_tokens:,}")
        if self.cost_usd is not None:
            parts.append(f"${self.cost_usd:.4f}")
        return f"{self.lane} " + " · ".join(parts)

    def as_dict(self) -> dict:
        return {"lane": self.lane, "input": self.input_tokens, "output": self.output_tokens,
                "cache_read": self.cache_read, "total": self.total_tokens,
                "cost_usd": self.cost_usd, "note": self.note}


@dataclass
class Call:
    text: str = ""
    usage: Usage = field(default_factory=Usage)
    error: str = ""


def _run(cmd, *, timeout: int) -> tuple:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"시간 초과 ({timeout}초)"
    except OSError as e:                                         # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        return None, ((r.stderr or "") + (r.stdout or ""))[-300:]
    return r.stdout, ""


def call_claude(prompt: str, *, model: str = "", timeout: int = TIMEOUT) -> Call:
    exe = shutil.which("claude")
    if not exe:
        return Call(error="claude 가 없다")
    cmd = [exe, "-p", "--output-format", "json"]
    if (model or "").strip():
        cmd += ["--model", model.strip()]
    out, why = _run(cmd + [prompt], timeout=timeout)
    if out is None:
        return Call(error=why)
    u = Usage(lane="claude")
    try:
        d = json.loads(out)
        text = d.get("result") or ""
        raw = d.get("usage") or {}
        u.input_tokens = raw.get("input_tokens")
        u.output_tokens = raw.get("output_tokens")
        u.cache_read = raw.get("cache_read_input_tokens")
        u.cost_usd = d.get("total_cost_usd")
        # [주의] claude 는 합계를 안 준다 — **더해서 만들지 않는다**(캐시 읽기를 어떻게 셀지는
        #    과금 정책이라 우리가 정할 값이 아니다). 필요한 쪽이 항목으로 계산한다.
    except ValueError as e:                                      # noqa: BLE001
        return Call(text=out, usage=Usage(lane="claude", note=f"JSON 파싱 실패: {e}"))
    return Call(text=text, usage=u)


def call_agy(prompt: str, *, timeout: int = TIMEOUT) -> Call:
    exe = shutil.which("agy")
    if not exe:
        return Call(error="agy 가 없다")
    # [주의] `-p` 는 **반드시 프롬프트 직전**이다 (2026-08-08 실측 — 앞에 두면 다음 토큰을 먹는다)
    out, why = _run([exe, "--dangerously-skip-permissions", "--output-format", "json",
                     "-p", prompt], timeout=timeout)
    if out is None:
        return Call(error=why)
    u = Usage(lane="agy")
    try:
        d = json.loads(out)
        text = d.get("response") or ""
        raw = d.get("usage") or {}
        u.input_tokens = raw.get("input_tokens")
        u.output_tokens = raw.get("output_tokens")
        u.cache_read = raw.get("cache_read_tokens")
        u.total_tokens = raw.get("total_tokens")
    except ValueError as e:                                      # noqa: BLE001
        return Call(text=out, usage=Usage(lane="agy", note=f"JSON 파싱 실패: {e}"))
    return Call(text=text, usage=u)


def call_codex(prompt: str, *, timeout: int = TIMEOUT, reasoning: str = "") -> Call:
    """`.33` 원격 CLI. **`--json` 이벤트에서 항목별 사용량**을 읽는다 (2026-09-05 실측).

        turn.completed → usage {input_tokens, cached_input_tokens,
                                cache_write_input_tokens, output_tokens,
                                reasoning_output_tokens}

    [주의] 종전에는 텍스트의 `tokens used` 한 줄(합계)만 읽었다 — 항목이 없어 agy/claude 와
    같은 축으로 비교할 수 없었다.
    """
    from .. import layer2_verify as L2
    text, events, why = L2.call_codex_why(
        prompt, timeout=timeout, reasoning=(reasoning or L2.CODEX_REASONING))
    if text is None:
        return Call(error=why)
    u = Usage(lane="codex")
    last = None
    for line in (events or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if (d.get("type") == "turn.completed") and isinstance(d.get("usage"), dict):
            last = d["usage"]
    if last:
        u.input_tokens = last.get("input_tokens")
        u.output_tokens = last.get("output_tokens")
        u.cache_read = last.get("cached_input_tokens")
        # [주의] **합계를 지어내지 않는다** — 캐시 입력을 어떻게 셀지는 과금 정책이다
    else:
        m = _CODEX_TOKENS.search(text or "")
        if m:
            u.total_tokens = int(m.group(1).replace(",", ""))
            u.note = "이벤트가 없어 텍스트 합계를 읽었다(항목 미상)"
        else:
            u.note = "`turn.completed` 이벤트를 못 찾았다"
    return Call(text=text, usage=u)


def call(lane: str, prompt: str, *, timeout: int = TIMEOUT) -> Call:
    """레인 이름으로 고른다. **CLI 레인만** — 로컬 모델은 브로커가 따로 답한다."""
    name, _, sub = (lane or "").partition(":")
    if name == "claude":
        return call_claude(prompt, model=sub, timeout=timeout)
    if name == "agy":
        return call_agy(prompt, timeout=timeout)
    if name == "codex":
        return call_codex(prompt, timeout=timeout)
    return Call(error=f"계측 대상 레인이 아니다: {lane}")


CLI_LANES = ("claude", "agy", "codex")


def is_cli_lane(lane: str) -> bool:
    return (lane or "").partition(":")[0] in CLI_LANES
