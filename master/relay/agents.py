"""에이전트 호출부 (`#942` T3) — claude·codex·agy 를 비대화로 실행하고 이벤트를 공통 형식으로 바꾼다.

옵션과 이벤트 형식은 2026-11-14 실측(리포트 180 T1 절)을 따른다:

    claude   claude -p --output-format stream-json --verbose --dangerously-skip-permissions
             새 세션 `--session-id <uuid>`(호출자가 정한다) · 이어가기 `--resume <uuid>`
    codex    codex exec --json --dangerously-bypass-approvals-and-sandbox <입력>
             이어가기 `codex exec resume … <id> <입력>` · 세션 ID 는 `thread.started.thread_id`
    agy      agy --output-format stream-json --dangerously-skip-permissions [--conversation <id>] -p=<입력>
             [주의] `-p` 는 바로 뒤 인자를 입력으로 먹는다 — 반드시 `-p=<입력>` 으로 붙인다

공통 이벤트 `{"kind", "text", "data"}`:

    system        세션 시작(세션 ID·권한 모드 등)
    agent_text    에이전트의 말
    tool_call     도구 호출 (text = 도구 이름 또는 명령)
    tool_result   도구 결과
    result        한 차례의 끝 (text = 최종 응답, data = usage 등)
    error         에이전트가 알린 실패
    delta         말의 조각 — 화면 표시용이며 로그에 남기지 않는다
    meta          진행 표시·한도 알림 등 — 화면에 내지 않는다
    raw           모르는 이벤트 — 버리지 않고 원문을 data 에 싣는다

[중요] 모르는 이벤트·해석 못 한 줄을 버리지 않는다 — `raw` 로 남기고 `dbg` 로 찍는다.
[주의] 표준 입력은 닫는다 — codex 는 열려 있으면 추가 입력을 기다린다(실측).
실행 파일은 `AX_RELAY_<에이전트>_BIN`, agy 모델은 `AX_RELAY_AGY_MODEL` 로 바꾼다(없으면 CLI 기본값).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

AGENTS = ("claude", "codex", "agy")
RESULT_CAP = 20000          # 도구 결과 한 건을 로그에 싣는 최대 글자 수 — 넘으면 잘랐다고 표시한다
STDERR_CAP = 4000           # 디버그 로그에 싣는 오류 출력 최대 글자 수


@dataclass
class Result:
    agent: str
    rc: int
    session: str = ""
    text: str = ""
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    error: str = ""
    interrupted: bool = False
    events: int = 0
    unparsed: int = 0

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.error and not self.interrupted


def exe(agent: str) -> str:
    return os.environ.get(f"AX_RELAY_{agent.upper()}_BIN", "").strip() or agent


def _safe(prompt: str) -> str:
    """입력이 `-` 로 시작하면 옵션으로 읽힐 수 있다 — 앞에 빈칸을 둔다."""
    return (" " + prompt) if prompt.startswith("-") else prompt


def build_cmd(agent: str, prompt: str, session: str = "") -> tuple:
    """(명령, 새로 정한 세션 ID). claude 만 새 세션 ID 를 호출자가 정한다."""
    if agent == "claude":
        base = [exe(agent), "-p", "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions"]
        if session:
            return base + ["--resume", session, _safe(prompt)], ""
        sid = str(uuid.uuid4())
        return base + ["--session-id", sid, _safe(prompt)], sid
    if agent == "codex":
        opts = ["--json", "--dangerously-bypass-approvals-and-sandbox"]
        if session:
            return [exe(agent), "exec", "resume", *opts, session, _safe(prompt)], ""
        return [exe(agent), "exec", *opts, _safe(prompt)], ""
    if agent == "agy":
        cmd = [exe(agent), "--output-format", "stream-json", "--dangerously-skip-permissions"]
        model = os.environ.get("AX_RELAY_AGY_MODEL", "").strip()
        if model:
            cmd += ["--model", model]
        if session:
            cmd += ["--conversation", session]
        return cmd + ["-p=" + prompt], ""
    raise ValueError(f"모르는 에이전트: {agent!r}")


def _cap(s) -> tuple:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    if len(s) > RESULT_CAP:
        return s[:RESULT_CAP], {"truncated": True, "full_chars": len(s)}
    return s, {}


def _ev(kind, text="", data=None) -> dict:
    return {"kind": kind, "text": text or "", "data": data if data is not None else {}}


def _text_of(content) -> str:
    """claude 의 content — 문자열이거나 블록 목록이다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text") if isinstance(b.get("text"), str) else json.dumps(b, ensure_ascii=False))
            else:
                out.append(str(b))
        return "\n".join(out)
    return "" if content is None else json.dumps(content, ensure_ascii=False)


class Parser:
    """한 번의 실행 동안 이벤트 줄을 공통 형식으로 바꾼다. 세션 ID·최종 응답·usage 를 모은다."""

    def __init__(self, agent: str):
        if agent not in AGENTS:
            raise ValueError(f"모르는 에이전트: {agent!r}")
        self.agent = agent
        self.session = ""
        self.text = ""
        self.usage: dict = {}
        self.error = ""
        self._agy_buf: dict = {}

    def feed(self, obj: dict) -> list:
        return getattr(self, "_" + self.agent)(obj)

    # ── claude ──
    def _claude(self, e: dict) -> list:
        t = e.get("type")
        if t == "system":
            if e.get("subtype") == "init":
                self.session = e.get("session_id") or self.session
                mcp = [f"{m.get('name')}:{m.get('status')}" for m in e.get("mcp_servers") or [] if isinstance(m, dict)]
                return [_ev("system", "세션 시작", {"session": self.session,
                                                   "permission": e.get("permissionMode"), "mcp": mcp})]
            return [_ev("meta", str(e.get("subtype") or "system"), e)]
        if t == "assistant":
            out = []
            for b in (e.get("message") or {}).get("content") or []:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text" and b.get("text"):
                    out.append(_ev("agent_text", b["text"]))
                elif bt == "tool_use":
                    out.append(_ev("tool_call", str(b.get("name") or ""), {"input": b.get("input"), "id": b.get("id")}))
                elif bt in ("thinking", "redacted_thinking"):
                    out.append(_ev("meta", "thinking"))
                else:
                    out.append(_ev("raw", f"assistant.{bt}", b))
            return out
        if t == "user":
            out = []
            content = (e.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    txt, extra = _cap(_text_of(b.get("content")))
                    out.append(_ev("tool_result", txt, {"id": b.get("tool_use_id"),
                                                        "is_error": bool(b.get("is_error")), **extra}))
            return out or [_ev("meta", "user")]
        if t == "result":
            self.session = e.get("session_id") or self.session
            self.usage = e.get("usage") or {}
            self.text = e.get("result") if isinstance(e.get("result"), str) else self.text
            if e.get("is_error"):
                self.error = f"claude result is_error ({e.get('subtype')}): {str(e.get('result'))[:500]}"
                return [_ev("error", self.error, {"subtype": e.get("subtype")})]
            return [_ev("result", self.text, {"usage": self.usage, "turns": e.get("num_turns")})]
        if t == "rate_limit_event":
            return [_ev("meta", "rate_limit_event", e)]
        return [_ev("raw", f"claude.{t}", e)]

    # ── codex ──
    def _codex(self, e: dict) -> list:
        t = e.get("type")
        if t == "thread.started":
            self.session = e.get("thread_id") or self.session
            return [_ev("system", "세션 시작", {"session": self.session})]
        if t == "turn.started":
            return [_ev("meta", t)]
        if t in ("item.started", "item.updated", "item.completed"):
            it = e.get("item") if isinstance(e.get("item"), dict) else {}
            it_type = it.get("type")
            done = t == "item.completed"
            if it_type == "agent_message":
                if not done:
                    return [_ev("meta", t)]
                self.text = it.get("text") or ""
                return [_ev("agent_text", self.text)]
            if it_type == "reasoning":
                return [_ev("meta", "reasoning")]
            if it_type == "command_execution":
                if t == "item.started":
                    return [_ev("tool_call", str(it.get("command") or ""), {"id": it.get("id")})]
                if not done:
                    return [_ev("meta", t)]
                txt, extra = _cap(it.get("aggregated_output") or "")
                return [_ev("tool_result", txt, {"id": it.get("id"), "exit_code": it.get("exit_code"),
                                                 "is_error": it.get("exit_code") not in (0, None), **extra})]
            if it_type == "error":
                self.error = f"codex item error: {str(it.get('message') or it)[:500]}"
                return [_ev("error", self.error, it)]
            # 그 밖의 항목(file_change·mcp_tool_call·web_search …) — 종류를 이름으로, 원문을 data 로 남긴다
            if t == "item.started":
                return [_ev("tool_call", str(it_type), it)]
            if done:
                return [_ev("tool_result", str(it_type), it)]
            return [_ev("meta", t)]
        if t == "turn.completed":
            self.usage = e.get("usage") or {}
            return [_ev("result", self.text, {"usage": self.usage})]
        if t in ("turn.failed", "error"):
            msg = (e.get("error") or {}).get("message") if isinstance(e.get("error"), dict) else e.get("message")
            self.error = f"codex {t}: {str(msg or e)[:500]}"
            return [_ev("error", self.error, e)]
        return [_ev("raw", f"codex.{t}", e)]

    # ── agy ──
    def _agy(self, e: dict) -> list:
        ev = e.get("event")
        if ev == "init":
            self.session = e.get("conversation_id") or self.session
            init = e.get("init") if isinstance(e.get("init"), dict) else {}
            return [_ev("system", "세션 시작", {"session": self.session, "model": init.get("model"),
                                               "permission": init.get("permission_mode")})]
        if ev == "step_update":
            s = e.get("step_update") if isinstance(e.get("step_update"), dict) else {}
            self.session = s.get("conversation_id") or self.session
            st, idx, state = s.get("step_type"), s.get("step_index"), s.get("state")
            if st == "agent_response":
                delta = s.get("text_delta") or ""
                self._agy_buf[idx] = self._agy_buf.get(idx, "") + delta
                out = [_ev("delta", delta)] if delta else []
                if state == "DONE":
                    full = self._agy_buf.pop(idx, "").strip()
                    if full:
                        out.append(_ev("agent_text", full))
                return out or [_ev("meta", "agent_response")]
            if st == "tool":
                info = s.get("tool_info") if isinstance(s.get("tool_info"), dict) else {}
                name = str(s.get("tool_name") or info.get("name") or "")
                if state == "DONE":
                    txt, extra = _cap(info.get("output") if info.get("output") is not None else "")
                    return [_ev("tool_result", txt, {"tool": name, "index": idx, **extra})]
                return [_ev("tool_call", name, {"input": info.get("parameters"), "index": idx})]
            if st in ("user_input", "system_message"):
                return [_ev("meta", str(st))]
            return [_ev("raw", f"agy.step.{st}", s)]
        if ev == "result":
            r = e.get("result") if isinstance(e.get("result"), dict) else {}
            self.session = r.get("conversation_id") or self.session
            self.usage = r.get("usage") or {}
            self.text = r.get("response") or self.text
            if r.get("status") != "SUCCESS":
                self.error = f"agy result status={r.get('status')}: {str(r.get('response') or r)[:500]}"
                return [_ev("error", self.error, r)]
            return [_ev("result", self.text.strip(), {"usage": self.usage, "turns": r.get("num_turns")})]
        return [_ev("raw", f"agy.{ev}", e)]


def _kill(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()


def run(agent: str, prompt: str, *, cwd: str, session: str = "", on_event=None, dbg=None,
        raw_sink=None, popen=subprocess.Popen) -> Result:
    """에이전트를 한 차례 실행한다. 이벤트는 오는 대로 `on_event(ev)` 로 넘긴다.

    `dbg(where, msg)` 는 디버그 로그, `raw_sink(line)` 은 받은 줄 원문 보관이다. Ctrl-C 는 프로세스 그룹을
    끝내고 `interrupted=True` 로 돌려준다. 실패해도 다시 시도하지 않는다 — 판단은 호출자 몫이다.
    """
    dbg = dbg or (lambda where, msg: None)
    on_event = on_event or (lambda ev: None)
    cmd, new_sid = build_cmd(agent, prompt, session)
    shown = cmd[:-1] + [f"<입력 {len(prompt)}자>"]
    dbg("agents.run", f"{agent} 실행 — cwd={cwd} 세션={'이어감 ' + session if session else '새로 ' + (new_sid or '(CLI 가 정함)')} "
                      f"명령={json.dumps(shown, ensure_ascii=False)}")
    parser = Parser(agent)
    res = Result(agent=agent, rc=-1, session=session or new_sid)
    t0 = time.time()
    try:
        proc = popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     text=True, encoding="utf-8", errors="replace", start_new_session=True)
    except OSError as e:
        res.error = f"실행하지 못했다: {type(e).__name__}: {e}"
        res.seconds = time.time() - t0
        dbg("agents.run", f"{agent} 기동 실패 — {res.error}")
        return res
    err_chunks: list = []
    th = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    th.start()
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if raw_sink:
                raw_sink(line)
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("객체가 아니다")
            except ValueError as e:
                res.unparsed += 1
                dbg("agents.parse", f"{agent} 해석 못 한 줄({e}): {line[:300]}")
                on_event(_ev("raw", f"{agent}.unparsed", {"line": line[:RESULT_CAP]}))
                continue
            try:
                evs = parser.feed(obj)
            except Exception as e:                      # noqa: BLE001 — 변환 실패로 대화를 끊지 않는다
                res.unparsed += 1
                dbg("agents.parse", f"{agent} 변환 예외 {type(e).__name__}: {e} — 줄: {line[:300]}")
                evs = [_ev("raw", f"{agent}.convert_error", obj)]
            for ev in evs:
                res.events += 1
                if ev["kind"] == "raw":
                    dbg("agents.parse", f"{agent} 모르는 이벤트 {ev['text']}")
                on_event(ev)
        proc.wait()
    except KeyboardInterrupt:
        res.interrupted = True
        dbg("agents.run", f"{agent} 중단 요청(Ctrl-C) — 프로세스 그룹 {proc.pid} 종료")
        _kill(proc)
    th.join(timeout=5)
    stderr = "".join(c for c in err_chunks if c)
    res.rc = proc.returncode if proc.returncode is not None else -1
    res.session = parser.session or res.session
    res.text, res.usage, res.seconds = parser.text, parser.usage, time.time() - t0
    res.error = parser.error
    if res.rc != 0 and not res.error and not res.interrupted:
        res.error = f"{agent} 종료 코드 {res.rc}: {stderr.strip()[-500:] or '(오류 출력 없음)'}"
    dbg("agents.run", f"{agent} 끝 — rc={res.rc} {res.seconds:.1f}초 이벤트={res.events} 해석실패={res.unparsed} "
                      f"세션={res.session or '(없음)'} 중단={res.interrupted} usage={json.dumps(res.usage, ensure_ascii=False)}")
    if stderr.strip():
        dbg("agents.stderr", f"{agent} 오류 출력({len(stderr)}자): {stderr.strip()[-STDERR_CAP:]}")
    if res.error:
        dbg("agents.run", f"{agent} 실패 — {res.error}")
    return res
