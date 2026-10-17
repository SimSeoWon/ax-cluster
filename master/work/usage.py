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
             (재실측 2026-10-04, agy 1.2.16: 최상위 `conversation_id`·`status`·`response`·
              `duration_seconds`·`num_turns`·`usage` + usage 에 `thinking_tokens` 추가.
              [주의] **모델 이름 키가 없다** — 그래서 기록의 model 은 비운다)
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
from datetime import datetime, timedelta
from pathlib import Path

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
    reasoning_tokens: int | None = None  # agy `thinking_tokens` (출력의 부분집합으로 보인다)
    cache_create: int | None = None     # claude `cache_creation_input_tokens` (`#733`)
    session_id: str = ""                # codex `thread.started.thread_id` (`#726`) — 모르면 빈 값

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


def _run(cmd, *, timeout: int, input: str | None = None, cwd: str | None = None) -> tuple:
    """`(stdout, 사유)`. 🔴 프롬프트는 `input`(표준 입력)으로 넘긴다 — 명령줄 인자는 리눅스에서
    하나당 128KB 가 상한이라 큰 골조가 `E2BIG` 로 죽는다(2026-10-10 실측)."""
    stdin_kw = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd, **stdin_kw)
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
    out, why = _run(cmd, timeout=timeout, input=prompt)
    if out is None:
        return Call(error=why)
    parsed = parse_claude_json(out)
    if parsed is None:
        return Call(text=out, usage=Usage(lane="claude", note="JSON 파싱 실패(claude 봉투 아님)"))
    text, u, _is_error, _model = parsed
    return Call(text=text, usage=u)


def parse_claude_json(stdout: str) -> tuple | None:
    """`claude -p --output-format json` 봉투 → `(본문, Usage, is_error, model)`. 아니면 `None`.

    [중요] **형식 지식은 이 모듈 한 곳이 갖는다** — 레인(`call_claude`)과 층2·리뷰 공용
    진입(`layer2_verify.call_claude_why`)이 같은 파서를 쓴다(`#733`, agy 의 `parse_agy_json` 과 같은 결).
    [주의] **`result` 키(또는 `type: result`)가 있는 dict 만 봉투로 본다** — 플래그가 안 먹어 모델 답
    자체가 JSON 이면 그것을 봉투로 오인해 본문을 버리게 된다.
    [주의] claude 는 합계를 안 준다 — **더해서 만들지 않는다**(캐시 읽기를 어떻게 셀지는 과금
    정책이라 우리가 정할 값이 아니다). 필요한 쪽이 항목으로 계산한다.
    """
    try:
        d = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(d, dict) or not ("result" in d or d.get("type") == "result"):
        return None
    text = d.get("result")
    text = text if isinstance(text, str) else ""
    raw = d.get("usage") if isinstance(d.get("usage"), dict) else {}

    def _int(key):
        v = raw.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    cost = d.get("total_cost_usd")
    u = Usage(lane="claude", input_tokens=_int("input_tokens"),
              output_tokens=_int("output_tokens"), cache_read=_int("cache_read_input_tokens"),
              cache_create=_int("cache_creation_input_tokens"),
              cost_usd=(float(cost) if isinstance(cost, (int, float))
                        and not isinstance(cost, bool) else None))
    if not u.known:
        u.note = "usage 키 없음"
    # `modelUsage` 는 모델별 dict 다 — 보조 모델이 섞이면 출력이 가장 많은 쪽을 쓴다
    model = ""
    mu = d.get("modelUsage")
    if isinstance(mu, dict) and mu:
        model = max(mu, key=lambda k: (mu[k] or {}).get("outputTokens") or 0
                    if isinstance(mu[k], dict) else 0)
    return text, u, bool(d.get("is_error")), str(model or "")


def call_agy(prompt: str, *, timeout: int = TIMEOUT) -> Call:
    exe = shutil.which("agy")
    if not exe:
        return Call(error="agy 가 없다")
    # 🔴 BRIEF 파일 방식 — 공용 진입과 **같은 모양**(`layer2_verify.agy_cmd`, 2026-10-10 `E2BIG`)
    try:
        from .. import layer2_verify as L2
    except ImportError as e:        # `#763` — 요청자 배달본엔 없다(파서만 쓴다). 레인 호출은 마스터 전용
        return Call(error=f"layer2_verify 없음 — 레인 호출은 마스터 전용: {e}")
    with L2.agy_brief(prompt) as brief_dir:
        out, why = _run(L2.agy_cmd(exe, brief_dir), timeout=timeout)
    if out is None:
        return Call(error=why)
    parsed = parse_agy_json(out)
    if parsed is None:
        return Call(text=out, usage=Usage(lane="agy", note="JSON 파싱 실패(agy 봉투 아님)"))
    text, u, _status, _model = parsed
    return Call(text=text, usage=u)


def parse_agy_json(stdout: str) -> tuple | None:
    """`agy --output-format json` 봉투 → `(본문, Usage, status, model)`. 봉투가 아니면 `None`.

    [중요] **형식 지식은 이 모듈 한 곳이 갖는다** — 레인(`call_agy`)과 층2·리뷰 공용 진입
    (`layer2_verify.call_agy_why`)이 같은 파서를 쓴다(`#728`).
    [주의] **`response` 키가 있는 dict 만 봉투로 본다.** 플래그가 먹지 않아 모델 답 자체가
    JSON 이면(예: `{"ok": true}`) 그것을 봉투로 오인해 본문을 버리게 된다.
    [주의] 못 읽은 토큰은 `None` 이다 — 0 을 지어내지 않는다.
    """
    try:
        d = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(d, dict) or "response" not in d:
        return None
    text = d.get("response")
    text = text if isinstance(text, str) else ""
    raw = d.get("usage") if isinstance(d.get("usage"), dict) else {}

    def _int(key):
        v = raw.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    u = Usage(lane="agy", input_tokens=_int("input_tokens"), output_tokens=_int("output_tokens"),
              cache_read=_int("cache_read_tokens"), total_tokens=_int("total_tokens"),
              reasoning_tokens=_int("thinking_tokens"))
    if not u.known:
        u.note = "usage 키 없음"
    # 2026-10-04 실측에는 모델 키가 없다 — 생기면 쓴다(대시보드가 gemini-* 로 분류한다)
    model = d.get("model")
    return text, u, str(d.get("status") or ""), (model if isinstance(model, str) else "")


def agy_envelope_error(stdout: str) -> str:
    """`agy --output-format json` 봉투의 `error` 문자열. 봉투가 아니거나 없으면 `""`.

    [주의] `status` 가 `ERROR` 여도 `response` 가 차 있을 수 있다 — 실측 2026-10-09:
    *"API error (attempt 1): UNAVAILABLE (code 503): No capacity available for model …"* 와 함께
    본문 5,401자가 왔다. 판정은 부르는 쪽이 한다 — 여기서는 사실만 꺼낸다(`parse_agy_json` 의
    4-튜플 계약은 레인·층2 가 쓰므로 바꾸지 않는다).
    """
    try:
        d = json.loads(stdout)
    except ValueError:
        return ""
    err = d.get("error") if isinstance(d, dict) else None
    return err if isinstance(err, str) else ""


_AGY_RETRY = re.compile(r"Run: attempt (\d+) failed \((.*)\), retrying in (\S+)")
_AGY_FAIL = re.compile(r"Run: attempt (\d+) failed \((.*)\)(?!, retrying)")
_AGY_LABEL = re.compile(r'Propagating selected model override to backend: label="([^"]+)"')
_AGY_GENERATE = "streamGenerateContent"


def agy_model_id(label: str) -> str:
    """`Gemini 3.6 Flash (High)` → `gemini-3.6-flash-high` (`agy models` 의 id 모양)."""
    return re.sub(r"\s+", "-", re.sub(r"[()]", "", label).strip()).lower()


def parse_agy_log(text: str) -> dict:
    """agy `--log-file` 로그 → `{model, retries, last_error, recovered, final_failure}`.

    🔴 [중요] **재시도 판정은 로그로만 한다** (사용자 결정 2026-10-09 A). 실측 2026-10-09: 봉투
    `status=ERROR` · `error="API error (attempt 1): UNAVAILABLE (code 503) …"` 인데 로그에는
    `Run: attempt 1 failed (…), retrying in 4s` 뒤 `streamGenerateContent` 요청이 2번 더 이어지고
    정상 종료했다 — 봉투의 status 는 **첫 시도의 기록**이었다.
    `recovered` = 재시도 줄이 있고 · 마지막 재시도 **뒤에** 생성 요청이 있고 · 「재시도 없는 실패」 줄이
    없다. 하나라도 어긋나면 `False` — 모르면 회복으로 보지 않는다.
    [주의] 모델은 로그의 마지막 label 이다(봉투에는 모델 키가 없다).
    """
    lines = (text or "").splitlines()
    retries, last_retry_at, final_failure, labels = [], -1, "", []
    for i, line in enumerate(lines):
        m = _AGY_RETRY.search(line)
        if m:
            retries.append(m.group(2))
            last_retry_at = i
            continue
        m = _AGY_FAIL.search(line)
        if m:
            final_failure = m.group(2)
        m = _AGY_LABEL.search(line)
        if m:
            labels.append(m.group(1))
    after = any(_AGY_GENERATE in l for l in lines[last_retry_at + 1:]) if last_retry_at >= 0 else False
    return {"model": agy_model_id(labels[-1]) if labels else "",
            "retries": len(retries), "last_error": retries[-1] if retries else "",
            "recovered": bool(retries) and after and not final_failure,
            "final_failure": final_failure}


def parse_codex_jsonl(stdout: str, *, error_lines: set[str] | None = None) -> tuple | None:
    """`codex exec --json` 의 이벤트 스트림 → `(본문, 계측)`. 이벤트가 없으면 `None`.

    [중요] **형식 지식은 이 모듈이 갖는다** — `call_codex` 가 이미 같은 이벤트를 읽고 있어서
    파서를 또 만들지 않는다(`#385` 검증 ⓒ). 지휘자 경로(`runner._unwrap`)가 이걸 부른다.

        thread.started  → {"thread_id": "<uuid>"}                         세션 id (`#726`)
        item.completed  → {"item": {"type": "agent_message", "text": …}}   본문
        turn.completed  → {"usage": {input_tokens, cached_input_tokens,
                                     cache_write_input_tokens, output_tokens,
                                     reasoning_output_tokens}}             토큰
        error / turn.failed → message / error.message                     실패 원인

    🔴 `#726` (사용자 결정 2026-10-09 (가) 「읽을 때 잇는다」): `thread_id` 를 meta 의
    `session_id` 로 싣는다. 실측 2026-10-09: 이 uuid 가 워커 rollout 파일 이름
    `rollout-<ts>-<uuid>.jsonl` 의 uuid 와 같다 — 대시보드가 그것으로 수집된 사본을 찾는다.
    [주의] 없으면 키를 만들지 않는다(옛 기록과 같은 모양).

    `error_lines`가 주어지면 읽은 오류 이벤트의 원문 줄도 돌려준다. 사람 보고에서
    같은 이벤트를 일반 오류 줄로 다시 요약하지 않기 위한 선택적 수집이다.

    계측은 **`Outcome` 이 읽는 이름으로** 옮긴다(`runner.py:113-118`):

        cache_creation_input_tokens  ← cache_write_input_tokens
        cache_read_input_tokens      ← cached_input_tokens

    🔴 [중요] **비용은 codex 가 주지 않는다.** `total_cost_usd` 키를 **만들지 않고**
    `cost_unknown=True` 를 싣는다 — 0 으로 적으면 「공짜」로 읽히고, 그것이 이 저장소가
    반복해 치른 「조용한 0」이다(이 모듈 머리말과 같은 규칙).
    """
    text, raw, errors, sid = "", None, [], ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("type") == "thread.started":
            sid = sid or _thread_id(d)
        elif d.get("type") == "item.completed":
            item = d.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") == "agent_message" and item.get("text"):
                text = str(item["text"])          # 마지막 것이 남는다
        elif d.get("type") == "turn.completed" and isinstance(d.get("usage"), dict):
            raw = d["usage"]
        elif d.get("type") in ("error", "turn.failed"):
            error = d.get("error") if d.get("type") == "turn.failed" else d
            message = error.get("message") if isinstance(error, dict) else None
            if isinstance(message, str) and message.strip():
                if error_lines is not None:
                    error_lines.add(line)
                if message not in errors:
                    errors.append(message)
    if not text and raw is None and not errors:
        # [주의] `thread.started` 하나만으로는 codex 결과로 보지 않는다(`#726`) — 종전처럼 원문을
        #    본문으로 돌려야 일찍 죽은 실행의 꼬리가 실패 사유에 남는다.
        return None                                # codex 이벤트가 아니다
    meta = {"source": "codex", "cost_unknown": True}
    if sid:
        meta["session_id"] = sid
    if errors:
        meta["errors"] = errors
    if raw is not None:
        meta["usage"] = {
            "input_tokens": raw.get("input_tokens"),
            "output_tokens": raw.get("output_tokens"),
            "cache_creation_input_tokens": raw.get("cache_write_input_tokens"),
            "cache_read_input_tokens": raw.get("cached_input_tokens"),
            "reasoning_output_tokens": raw.get("reasoning_output_tokens"),
        }
    return text, meta


def _thread_id(d: dict) -> str:
    """`thread.started` 이벤트의 `thread_id`. 문자열이 아니면 빈 값(`#726`)."""
    v = d.get("thread_id")
    return v.strip() if isinstance(v, str) else ""


def input_split(family: str, input_tokens, cache_read, cache_create=None) -> tuple | None:
    """입력을 `(비캐시, 캐시 읽기)` 로 나눈다 (`#726`). 계열을 모르거나 값이 없으면 `None`.

    🔴 [중요] **계열마다 `input` 의 뜻이 다르다** (`usage_dashboard._ACCOUNTING` 과 같은 결):
        codex          input 이 **캐시를 포함**한다 → 비캐시 = input − cache_read
        claude         input 이 캐시를 **뺀** 값이다 → 비캐시 = input + cache_create
        agy·gemini·local  input 이 캐시를 뺀 값으로 본다 → 비캐시 = input
                       (agy 실측: cache_read 81,518 > input 70,543 — 포함일 수 없다)
    [주의] 합계 정의는 바꾸지 않는다 — 이것은 **나눠 보기**일 뿐이다.
    """
    name = (family or "").casefold().partition(":")[0]
    if not isinstance(input_tokens, int) or not isinstance(cache_read, int):
        return None
    if name == "codex":
        return max(0, input_tokens - cache_read), cache_read
    if name == "claude":
        return input_tokens + (cache_create if isinstance(cache_create, int) else 0), cache_read
    if name in ("agy", "gemini", "local"):
        return input_tokens, cache_read
    return None


def call_codex(prompt: str, *, timeout: int = TIMEOUT, reasoning: str = "") -> Call:
    """`.33` 원격 CLI. **`--json` 이벤트에서 항목별 사용량**을 읽는다 (2026-09-05 실측).

        turn.completed → usage {input_tokens, cached_input_tokens,
                                cache_write_input_tokens, output_tokens,
                                reasoning_output_tokens}

    [주의] 종전에는 텍스트의 `tokens used` 한 줄(합계)만 읽었다 — 항목이 없어 agy/claude 와
    같은 축으로 비교할 수 없었다.

    🔴 [중요] **여기서는 공용 진입의 기록을 끈다**(`#733`). 이 함수의 소비자는 레인(`lanes.run_one`)
    이고, 그 `Call.usage` 는 파견이 `record(paths.usage_log, …)` 로 **직접** 남긴다(`infer.py`).
    `call_codex_why` 가 감싼 구간에서 한 줄을 더 쓰면 같은 호출이 두 번 세진다.
    """
    try:
        from .. import layer2_verify as L2
    except ImportError as e:        # `#763` — 위 `call_agy` 와 같은 이유
        return Call(error=f"layer2_verify 없음 — 레인 호출은 마스터 전용: {e}")
    with _suppressed():
        text, events, why = L2.call_codex_why(
            prompt, timeout=timeout, reasoning=(reasoning or L2.CODEX_REASONING))
    if text is None:
        return Call(error=why)
    return Call(text=text, usage=usage_from_codex_events(events, text))


def usage_from_codex_events(events: str, text: str = "") -> Usage:
    """`codex exec --json` 이벤트 → `Usage` (`turn.completed` 의 마지막 usage).

    [중요] 레인(`call_codex`)과 공용 진입(`layer2_verify.call_codex_why`)이 **같은 해석**을 쓴다
    (`#733`). 이벤트가 없으면 본문의 `tokens used` 합계로 물러서고, 그것도 없으면 미상이다.
    """
    u = Usage(lane="codex")
    last = None
    sid = ""
    for line in (events or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("type") == "thread.started":
            sid = sid or _thread_id(d)                # `#726` — 세션 사본과 잇는 열쇠
        if (d.get("type") == "turn.completed") and isinstance(d.get("usage"), dict):
            last = d["usage"]
    u.session_id = sid
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
    return u


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


# ─────────────────────────────────────────────────────────────────────────────
# 계측 기록·집계 (`#387`) — 원전 `watcher/common.py:607` `_record_token_usage` 이식
#
# 원전은 호출마다 한 줄 남기고(`token_usage.jsonl`) `get_token_summary(days=N)` 이
# 기간·제공자별로 합산했다. 그 두 겹을 그대로 옮긴다. **바꾼 것은 둘이다**:
#   ⑴ 저장 위치 — 트윈마다(`paths.usage_log`). 다중 프로젝트 축이라 「누가 태웠나」가
#      합계만큼 중요하고, 파견 유닛이 큐 루트를 모른다. 합계는 읽기에서 모은다.
#   ⑵ 🔴 **`cost_known`** — 원전에 없던 칸이다. 원전은 claude 하나만 셌지만 우리는 codex 도
#      쓰고, codex 는 **토큰은 주고 USD 는 안 준다**. 0 으로 적으면 「공짜」가 된다.
# ─────────────────────────────────────────────────────────────────────────────

import threading as _threading

_LOG_LOCK = _threading.Lock()


def meta_from_usage(u) -> dict:
    """`Usage`(레인) → `runner.Outcome` 이 읽는 meta 모양.

    [중요] **레인과 지휘자를 같은 모양으로 만든다.** 형태가 둘이면 집계가 둘이 되고, 그때
    「lane 이 싼가 codex 가 싼가」를 못 잰다 — 이 일감이 서는 이유가 그 비교다.
    [주의] 모르는 값은 **키를 만들지 않는다.** `None` 을 0 으로 적으면 「안 썼다」가 된다.
    """
    if u is None:
        return {}
    inner, meta = {}, {"source": getattr(u, "lane", "") or "lane"}
    for key, attr in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                      ("cache_read_input_tokens", "cache_read")):
        v = getattr(u, attr, None)
        if v is not None:
            inner[key] = int(v)
    total = getattr(u, "total_tokens", None)
    if total is not None:
        inner["total_tokens"] = int(total)
    reasoning = getattr(u, "reasoning_tokens", None)
    if reasoning is not None:
        inner["reasoning_output_tokens"] = int(reasoning)
    create = getattr(u, "cache_create", None)
    if create is not None:
        inner["cache_creation_input_tokens"] = int(create)
    if inner:
        meta["usage"] = inner
    cost = getattr(u, "cost_usd", None)
    if cost is None:
        meta["cost_unknown"] = True                 # 🔴 0 으로 접지 않는다
    else:
        meta["total_cost_usd"] = float(cost)
    if getattr(u, "note", ""):
        meta["note"] = u.note
    sid = getattr(u, "session_id", "")
    if isinstance(sid, str) and sid:
        meta["session_id"] = sid                   # `#726` — 없으면 키를 만들지 않는다
    return meta


def envelope(body: str, meta: dict) -> str:
    """`runner._unwrap` 이 되읽는 봉투 — `claude --output-format json` 과 **같은 모양**.

    🔴 [중요] **이것이 파싱 경로를 하나로 만든다.** 레인 갈래는 종전에
    `"RESULT: DONE (lane=agy)"` 라는 **합성 문자열**만 돌려줘서 계측이 그 자리에서 사라졌다
    (`#387` 증상). 봉투에 실어 보내면 지휘자 갈래와 **같은 `_unwrap` 한 번**으로 풀린다 —
    받는 쪽(`wcommit`)에 갈래를 만들지 않는다.
    """
    return json.dumps({"result": body, **(meta or {})}, ensure_ascii=False)


def normalize(meta: dict, *, lane: str = "", seconds: float = 0.0) -> dict:
    """meta → 집계 레코드 필드. 원전 record 모양 + `cost_known`.

    [주의] `cost_known=False` 와 `cost_usd=0.0` 은 **다른 사실**이다 — 전자는 모른다,
    후자는 안 썼다. 집계가 둘을 섞으면 codex 가 공짜로 보인다.
    """
    meta = meta or {}
    inner = meta.get("usage") or {}
    known = bool(meta) and not meta.get("cost_unknown")
    return {
        "lane": lane or str(meta.get("source") or ""),
        "input_tokens": int(inner.get("input_tokens") or 0),
        "output_tokens": int(inner.get("output_tokens") or 0),
        "cache_read": int(inner.get("cache_read_input_tokens") or 0),
        "cache_create": int(inner.get("cache_creation_input_tokens") or 0),
        "reasoning_tokens": int(inner.get("reasoning_output_tokens") or 0),
        "cost_usd": float(meta.get("total_cost_usd") or 0.0),
        "cost_known": known,
        "measured": bool(inner),                    # 토큰을 실제로 읽었나
        "seconds": round(float(seconds or 0.0), 1),
    }


def record(path, meta: dict, *, lane: str = "", task_id: str = "", work_id: str = "",
           worker: str = "", rc: int = 0, seconds: float = 0.0, mode: str = "",
           source: str = "dispatch", model: str = "", note: str = "") -> dict:
    """한 줄 추가하고 그 레코드를 돌려준다. [중요] **실패해도 파이프라인을 막지 않는다.**

    원전도 `except: pass` 다 — 계측이 작업을 죽이면 안 된다. 다만 원전과 달리 **무엇을
    못 썼는지는 돌려준다**(`{"error": …}`), 부르는 쪽이 로그에 남길 수 있게.
    [중요] **rc≠0 도 기록한다** — 실패한 실행도 토큰은 태웠다(사용자 지적 2026-09-08).
    """
    rec = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "work_id": work_id, "task_id": task_id, "worker": worker,
           "mode": mode, "rc": int(rc), "source": source, "model": model,
           **normalize(meta, lane=lane, seconds=seconds)}
    if note:
        rec["note"] = note          # 값이 있을 때만 — 기존 레코드 모양은 그대로다 (ax-gemini 경고·실패 사유)
    # 🔴 `#726` — codex 세션 id(`thread.started.thread_id`). 대시보드가 읽을 때 수집된 rollout
    #    사본과 잇는다(사용자 결정 2026-10-09 (가)). [주의] 없으면 칸을 만들지 않는다.
    sid = (meta or {}).get("session_id") if isinstance(meta, dict) else None
    if isinstance(sid, str) and sid.strip():
        rec["session_id"] = sid.strip()
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK:
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:                                       # noqa: BLE001
        return {**rec, "error": f"{type(e).__name__}: {e}"}
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# 브로커 호출 기록 지점 (`#713` ①, 2026-10-03)
#
# 🔴 [중요] **감싼 구간만 기록한다.** `with sink(paths.usage_log, source="synth"):` 안에서 일어난
#    `call_broker` 는 그 트윈의 `usage_log.jsonl` 에 한 줄씩 남는다. 감싸지 않은 호출은 남지 않는다 —
#    워커 파견(`infer.py`)처럼 **이미 따로 세는 경로**를 두 번 세지 않기 위해서다.
#    경로를 함수 인자로 끝까지 내리지 않는 이유: 온톨로지는 `refresh_domain → _lane → generate →
#    call_broker` 로 네 겹이다. 스레드 풀로 넘길 때는 `contextvars.copy_context()` 로 같이 넘긴다.
# [중요] 로컬 모델은 **비용 0 이 확정**이다(`cost_known=True`) — CLI 의 「모름」과 다르다.
# ─────────────────────────────────────────────────────────────────────────────

import contextvars as _cv
from contextlib import contextmanager as _contextmanager

_SINK: "_cv.ContextVar[dict | None]" = _cv.ContextVar("ax_usage_sink", default=None)


@_contextmanager
def sink(log_path, *, source: str, work_id: str = "", task_id: str = ""):
    """이 구간의 브로커 호출을 `log_path` 에 `source` 로 기록한다."""
    tok = _SINK.set({"path": Path(log_path), "source": source,
                     "work_id": work_id, "task_id": task_id, "cli": []})
    try:
        yield
    finally:
        _SINK.reset(tok)


@_contextmanager
def _suppressed():
    """이 구간의 공용 진입 기록을 끈다 — **호출자가 따로 세는 경로**에서만 쓴다(`call_codex`)."""
    tok = _SINK.set(None)
    try:
        yield
    finally:
        _SINK.reset(tok)


def emit_broker(model: str, used: dict, *, seconds: float = 0.0, rc: int = 0) -> dict | None:
    """`call_broker` 가 부른다. 감싼 구간이 아니면 아무것도 안 한다(`None`).

    `used` 는 `call_broker(usage=…)` 모양(`in`·`out`·`ms`). 노드가 안 준 값은 키가 없다 —
    그러면 `measured=False` 로 남는다(0 을 지어내지 않는다).
    """
    s = _SINK.get()
    if s is None:
        return None
    inner = {}
    if "in" in used:
        inner["input_tokens"] = int(used["in"])
    if "out" in used:
        inner["output_tokens"] = int(used["out"])
    meta = {"source": "local", "total_cost_usd": 0.0}
    if inner:
        meta["usage"] = inner
    return record(s["path"], meta, lane=f"local:{model}", work_id=s["work_id"],
                  task_id=s["task_id"], rc=rc, seconds=seconds, source=s["source"], model=model)


def emit_cli(lane: str, u=None, *, seconds: float = 0.0, rc: int = 0,
             model: str = "") -> dict | None:
    """상용 CLI 공용 진입(`layer2_verify.call_agy_why` · `#733` 부터 `call_claude_why` ·
    `call_codex_why`)이 부른다 (`#728`). `emit_broker` 와 같은
    계약 — **감싼 구간이 아니면 아무것도 안 한다**(`None`).

    🔴 [중요] 실패한 호출도 한 줄 남긴다(rc≠0) — 토큰을 못 읽었으면 `measured=False` 다.
    [주의] **기록 실패가 호출을 죽이지 않는다** — 예외를 삼키고 `{"error": …}` 로 돌려준다.
    """
    s = _SINK.get()
    if s is None:
        return None
    try:
        meta = meta_from_usage(u if u is not None else Usage(lane=lane))
        rec = record(s["path"], meta, lane=lane, work_id=s["work_id"], task_id=s["task_id"],
                     rc=rc, seconds=seconds, source=s["source"], model=model or "")
        s.setdefault("cli", []).append(rec)
        return rec
    except Exception as e:                                       # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def sink_cli_tokens() -> dict:
    """이 구간에서 기록한 상용 CLI 호출의 토큰 — `{"in": …, "out": …}`, 못 쟀으면 빈 dict (`#751`).

    호출자가 로그 줄에 쓰는 값이다. [중요] 0 을 지어내지 않는다 — 측정된 줄이 없으면 비운다.
    """
    s = _SINK.get()
    recs = [r for r in (s or {}).get("cli", []) if r.get("measured") and not r.get("error")]
    if not recs:
        return {}
    return {"in": sum(int(r.get("input_tokens") or 0) for r in recs),
            "out": sum(int(r.get("output_tokens") or 0) for r in recs)}


def summarize(paths_or_files, *, days: int = 1) -> dict:
    """기간 합계 — 원전 `get_token_summary` 와 같은 결. 트윈 하나 또는 여러 개를 받는다.

    🔴 [중요] **미상을 따로 센다.** `cost_usd` 합계는 **`cost_known` 인 것만** 더하고,
    모르는 호출 수를 `cost_unknown_calls` 로 함께 낸다 — 그래야 *"codex 가 얼마나 비싼가"* 에
    「USD 는 모른다, 토큰은 이만큼」이라고 정확히 답할 수 있다.
    [주의] 토큰 합계는 미상 여부와 무관하다 — codex 도 토큰은 준다.
    """
    files = paths_or_files if isinstance(paths_or_files, (list, tuple)) else [paths_or_files]
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    out = {"period_days": days, "calls": 0, "input_tokens": 0, "output_tokens": 0,
           "cache_read": 0, "cache_create": 0, "reasoning_tokens": 0,
           "cost_usd": 0.0, "cost_unknown_calls": 0, "unmeasured_calls": 0,
           "seconds": 0.0, "failed_calls": 0, "by_lane": {}, "by_mode": {}, "by_source": {},
           "files": 0}
    for f in files:
        p = Path(f)
        if not p.exists():
            continue
        out["files"] += 1
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue                                 # [주의] 깨진 줄은 건너뛴다 — 세지 않는다
            if str(r.get("ts") or "") < cutoff:
                continue
            out["calls"] += 1
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_create",
                      "reasoning_tokens"):
                out[k] += int(r.get(k) or 0)
            out["seconds"] += float(r.get("seconds") or 0.0)
            if int(r.get("rc") or 0) != 0:
                out["failed_calls"] += 1
            if not r.get("measured"):
                out["unmeasured_calls"] += 1
            if r.get("cost_known"):
                out["cost_usd"] += float(r.get("cost_usd") or 0.0)
            else:
                out["cost_unknown_calls"] += 1
            for axis, key in (("by_lane", "lane"), ("by_mode", "mode"), ("by_source", "source")):
                # 옛 기록(`#713` ① 전)은 `source` 칸이 없다 — 그때는 워커 파견만 기록했다
                name = str(r.get(key) or ("dispatch" if key == "source" else "?"))
                b = out[axis].setdefault(name, {"calls": 0, "tokens": 0, "cost_usd": 0.0,
                                                "cost_unknown_calls": 0})
                b["calls"] += 1
                b["tokens"] += int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0)
                if r.get("cost_known"):
                    b["cost_usd"] += float(r.get("cost_usd") or 0.0)
                else:
                    b["cost_unknown_calls"] += 1
    out["seconds"] = round(out["seconds"], 1)
    out["cost_usd"] = round(out["cost_usd"], 4)
    return out


def render(s: dict) -> str:
    """집계 → 사람이 읽는 블록. 🔴 [중요] **미상을 숨기지 않는다.**

    이 표면이 답해야 할 질문은 *"codex 가 얼마나 비싼가"* 이고, 정직한 답은 종종
    「USD 는 모른다, 토큰은 이만큼」이다. 모르는 것을 0 으로 적으면 그 답이 **거짓**이 된다.
    """
    L = [f"[계측] 최근 {s['period_days']}일 · 호출 {s['calls']}건"
         + (f" (실패 {s['failed_calls']})" if s.get("failed_calls") else "")
         + (f" · 로그 {s['files']}개" if s.get("files", 0) > 1 else "")]
    if not s["calls"]:
        return L[0] + " — 기록이 없다"
    L.append(f"  토큰  입력 {s['input_tokens']:,} · 출력 {s['output_tokens']:,}"
             + (f" · 추론 {s['reasoning_tokens']:,}" if s.get("reasoning_tokens") else "")
             + (f" · 캐시읽기 {s['cache_read']:,}" if s.get("cache_read") else ""))
    cost = f"  비용  ${s['cost_usd']:.4f}"
    if s["cost_unknown_calls"]:
        cost += (f"  [주의] **{s['cost_unknown_calls']}건은 비용 미상** — 합계에 안 들어갔다"
                 f" (0 이 아니라 모른다)")
    L.append(cost)
    if s.get("unmeasured_calls"):
        L.append(f"  [주의] 토큰조차 못 읽은 호출 {s['unmeasured_calls']}건")
    for axis, label in (("by_mode", "지휘자"), ("by_lane", "레인")):
        rows = sorted((s.get(axis) or {}).items(), key=lambda kv: -kv[1]["tokens"])
        if not rows:
            continue
        L.append(f"  {label}별")
        for name, b in rows:
            line = f"    {name or '?':10} 호출 {b['calls']:3}  토큰 {b['tokens']:>9,}"
            line += (f"  ${b['cost_usd']:.4f}" if not b["cost_unknown_calls"]
                     else f"  비용 미상 {b['cost_unknown_calls']}건")
            L.append(line)
    return "\n".join(L)


def logs_for(root) -> list:
    """`AX_PROJECTS_ROOT` 아래 모든 트윈의 계측 로그. [주의] 없는 것은 조용히 빠진다."""
    try:
        return sorted(p for p in Path(root).glob("*/usage_log.jsonl") if p.is_file())
    except Exception:                                            # noqa: BLE001
        return []


def main(argv=None) -> int:
    """`python -m master.work.usage [--days N] [프로젝트]` — 사람이 부르는 자리."""
    import argparse, os                                          # noqa: PLC0415
    ap = argparse.ArgumentParser(description="파견 계측 집계 (#387)")
    ap.add_argument("project", nargs="?", default="", help="생략하면 트윈 전부")
    ap.add_argument("--days", type=int, default=1)
    a = ap.parse_args(argv)
    root = os.environ.get("AX_PROJECTS_ROOT")
    if not root:
        print("[중요] AX_PROJECTS_ROOT 미설정 — 폴백은 없다 (명시하라)")
        return 2
    files = ([Path(root) / a.project / "usage_log.jsonl"] if a.project else logs_for(root))
    print(render(summarize(files, days=a.days)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
