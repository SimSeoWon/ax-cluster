"""agy 대화 기록(SQLite)에서 한 호출의 궤적을 읽는다 (`#888` T1).

`agy` 는 대화마다 `~/.gemini/antigravity-cli/conversations/<uuid>.db` 를 남긴다(WAL 모드 —
`.db`·`.db-wal`·`.db-shm`, 최근 단계는 WAL 에만 있을 수 있다). 리뷰 큐의 퇴고가 시간 한도에
걸려도 「무엇을 하다 끊겼나」가 보이지 않아서, 하트비트와 끝 요약을 이 기록에서 만든다.

실측(2026-11-05)으로 정한 해석:

    steps.step_type  14 = 사용자 입력 · 15 = 모델 턴 · 132 = 도구 호출(+결과)
    steps.metadata   protobuf. 그 안의 `google.protobuf.Timestamp` 모양 하위 메시지
                     (필드 1 = 유닉스 초, 필드 2 = 나노초) 의 최소~최대가 그 단계의 시작~끝
    도구 호출         metadata 안의 하위 메시지 {2: 도구 이름, 3: JSON 인자}

🔴 [중요] **agy 의 라이브 파일을 열지 않는다.** 임시 디렉터리에 `.db`·`.db-wal` 을 복사해 그
사본을 연다. `.db-shm` 은 일부러 복사하지 않는다 — 두 파일 사이에 찢긴 공유 인덱스를 들고 오면
SQLite 가 그것을 믿을 수 있고, 없으면 복사한 WAL 에서 인덱스를 다시 짓는다(WAL 의 미체크포인트
행도 그래서 보인다). 사본은 끝나면 지운다.
[중요] **예외를 던지지 않는다** — 하트비트·요약은 관측일 뿐이고 호출을 죽이면 안 된다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".gemini" / "antigravity-cli" / "conversations"

STEP_USER = 14
STEP_MODEL = 15
STEP_TOOL = 132

# Timestamp 로 받아들일 초의 범위 — 2017 ~ 2039. 우연히 그 모양을 한 바이트열을 거른다.
_TS_MIN, _TS_MAX = 1_500_000_000, 2_200_000_000
_MAX_DEPTH = 6
# 마커를 찾을 때 볼 앞쪽 단계 수 — BRIEF 경로는 사용자 입력과 첫 read_file 에 있다.
_MARKER_STEPS = 8

_TOOL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_PINNED = re.compile(r"^/tmp/ax-pinned-[^/]+/tree/")
_BRIEF = re.compile(r"^/tmp/ax-agy-[^/]+/")


@dataclass
class ToolCall:
    name: str
    path: str = ""
    start: int | None = None
    end: int | None = None
    status: int = 0


@dataclass
class Trace:
    conversation: str = ""
    steps: int = 0
    turns: int = 0
    turn_seconds: list = field(default_factory=list)
    tools: list = field(default_factory=list)              # [ToolCall]
    first_ts: float | None = None
    last_ts: float | None = None
    last_status: int | None = None
    last_step_type: int | None = None
    error: str = ""

    @property
    def last_tool(self):
        return self.tools[-1] if self.tools else None


# ── protobuf (스키마 없이) ──────────────────────────────────────────────────

def _varint(b: bytes, i: int):
    v = s = 0
    while True:
        if i >= len(b) or s > 63:
            raise ValueError("varint")
        x = b[i]
        i += 1
        v |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return v, i


def _fields(b: bytes) -> list:
    """한 메시지의 `(필드, wire, 값)` 목록. 메시지로 읽히지 않으면 ValueError."""
    i, out = 0, []
    while i < len(b):
        key, i = _varint(b, i)
        f, w = key >> 3, key & 7
        if f == 0:
            raise ValueError("field 0")
        if w == 0:
            v, i = _varint(b, i)
        elif w == 1:
            v, i = b[i:i + 8], i + 8
        elif w == 5:
            v, i = b[i:i + 4], i + 4
        elif w == 2:
            n, i = _varint(b, i)
            if i + n > len(b):
                raise ValueError("length")
            v, i = b[i:i + n], i + n
        else:
            raise ValueError("wire")
        if i > len(b):
            raise ValueError("overrun")
        out.append((f, w, v))
    return out


def _walk(b: bytes, depth: int = 0):
    """`b` 를 메시지로 읽고 그 안의 모든 하위 메시지를 깊이 우선으로 낸다(자기 자신 포함)."""
    try:
        fs = _fields(b)
    except ValueError:
        return
    yield fs
    if depth >= _MAX_DEPTH:
        return
    for _f, w, v in fs:
        if w == 2 and len(v) >= 2:
            yield from _walk(v, depth + 1)


def _timestamp(fs) -> float | None:
    ids = {f for f, _w, _v in fs}
    if not ids or not ids <= {1, 2}:
        return None
    sec = [v for f, w, v in fs if f == 1 and w == 0]
    nano = [v for f, w, v in fs if f == 2 and w == 0]
    if len(sec) != 1 or not (_TS_MIN < sec[0] < _TS_MAX) or len(nano) > 1:
        return None
    if nano and nano[0] >= 1_000_000_000:
        return None
    return sec[0] + (nano[0] / 1e9 if nano else 0.0)


def step_times(meta: bytes | None) -> list:
    """metadata 안 Timestamp 들(초, 부동소수)."""
    if not meta:
        return []
    out = []
    for fs in _walk(bytes(meta)):
        t = _timestamp(fs)
        if t is not None:
            out.append(t)
    return out


def _text(v) -> str | None:
    try:
        s = bytes(v).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s


def tool_call(*blobs) -> ToolCall | None:
    """도구 단계의 metadata/payload 에서 `{2: 이름, 3: JSON 인자}` 하위 메시지를 찾는다."""
    for blob in blobs:
        if not blob:
            continue
        for fs in _walk(bytes(blob)):
            names = [_text(v) for f, w, v in fs if f == 2 and w == 2]
            args = [_text(v) for f, w, v in fs if f == 3 and w == 2]
            if len(names) != 1 or len(args) != 1 or not names[0] or not args[0]:
                continue
            if not _TOOL_NAME.match(names[0]) or not args[0].lstrip().startswith("{"):
                continue
            try:
                a = json.loads(args[0])
            except ValueError:
                continue
            if not isinstance(a, dict):
                continue
            tc = ToolCall(name=names[0])
            p = a.get("Path") or a.get("AbsolutePath") or a.get("path") or ""
            tc.path = p if isinstance(p, str) else ""
            for key, attr in (("StartLine", "start"), ("EndLine", "end")):
                if isinstance(a.get(key), int):
                    setattr(tc, attr, a[key])
            return tc
    return None


# ── 파일 다루기 ──────────────────────────────────────────────────────────

class _Copy:
    """`.db`(+`.db-wal`) 를 임시 디렉터리에 복사해 연 연결. 나가면 지운다."""

    def __init__(self, db_path):
        self.src = Path(db_path)
        self.td = None
        self.conn = None

    def __enter__(self):
        self.td = tempfile.mkdtemp(prefix="ax-agytrace-")
        try:
            dst = Path(self.td) / self.src.name
            shutil.copyfile(self.src, dst)
            wal = self.src.with_name(self.src.name + "-wal")
            try:
                shutil.copyfile(wal, dst.with_name(dst.name + "-wal"))
            except FileNotFoundError:
                pass
            self.conn = sqlite3.connect(str(dst), timeout=1)
        except BaseException:
            # `#888` R241-2 — 여기서 던지면 `__exit__` 가 불리지 않는다. 임시 디렉터리를 직접 지운다.
            shutil.rmtree(self.td, ignore_errors=True)
            self.td = None
            raise
        return self.conn

    def __exit__(self, *exc):
        try:
            if self.conn is not None:
                self.conn.close()
        finally:
            shutil.rmtree(self.td, ignore_errors=True)
        return False


def _mtime(p: Path) -> float:
    best = 0.0
    for q in (p, p.with_name(p.name + "-wal")):
        try:
            best = max(best, q.stat().st_mtime)
        except OSError:
            pass
    return best


def find_conversation(marker: str, *, since: float, root=DEFAULT_ROOT) -> Path | None:
    """`since`(유닉스 초) 이후 바뀐 대화 중 앞쪽 단계에 `marker` 가 든 것. 없거나 오류면 None.

    `marker` 는 호출마다 새로 만든 BRIEF 디렉터리 경로다(`layer2_verify.agy_brief`).
    여럿이 맞으면 가장 최근에 바뀐 것을 고른다.
    """
    try:
        if not marker:
            return None
        needle = marker.encode("utf-8")
        cands = []
        for p in Path(root).glob("*.db"):
            m = _mtime(p)
            if m >= since:
                cands.append((m, p))
        for _m, p in sorted(cands, reverse=True):
            try:
                with _Copy(p) as c:
                    row = c.execute(
                        "SELECT 1 FROM (SELECT step_payload FROM steps ORDER BY idx LIMIT ?) "
                        "WHERE instr(step_payload, ?) > 0 LIMIT 1",
                        (_MARKER_STEPS, needle)).fetchone()
                if row:
                    return p
            except Exception:                                # noqa: BLE001
                continue
    except Exception:                                        # noqa: BLE001
        return None
    return None


def read_trace(db_path) -> Trace:
    """대화 하나의 궤적. 읽지 못하면 `error` 만 채워 돌려준다(던지지 않는다)."""
    p = Path(db_path)
    tr = Trace(conversation=p.stem)
    try:
        with _Copy(p) as c:
            rows = c.execute("SELECT idx, step_type, status, metadata, step_payload "
                             "FROM steps ORDER BY idx").fetchall()
    except Exception as e:                                    # noqa: BLE001
        tr.error = f"{type(e).__name__}: {e}"
        return tr
    stamps = []
    for _idx, kind, status, meta, payload in rows:
        tr.steps += 1
        tr.last_status, tr.last_step_type = status, kind
        ts = step_times(meta)
        stamps += ts
        if kind == STEP_MODEL:
            tr.turns += 1
            tr.turn_seconds.append(round(max(ts) - min(ts), 1) if ts else None)
        elif kind == STEP_TOOL:
            tc = tool_call(meta, payload) or ToolCall(name="?")
            tc.status = status
            tr.tools.append(tc)
    if stamps:
        tr.first_ts, tr.last_ts = min(stamps), max(stamps)
    return tr


# ── 표시 ────────────────────────────────────────────────────────────────

def short_path(path: str) -> str:
    """`/tmp/ax-pinned-*/tree/x` → `x` · `/tmp/ax-agy-*/BRIEF.md` → `BRIEF.md`."""
    if not path:
        return ""
    return _BRIEF.sub("", _PINNED.sub("", path))


def tool_label(tc) -> str:
    if tc is None:
        return "없음"
    s = tc.name
    if tc.path:
        s += " " + short_path(tc.path)
        if tc.start is not None or tc.end is not None:
            s += f":{'' if tc.start is None else tc.start}-{'' if tc.end is None else tc.end}"
    return s


def _secs(v) -> str:
    if v is None:
        return "?"
    return str(int(round(v)))


def heartbeat_line(elapsed: float, trace: Trace | None) -> str:
    """하트비트 한 줄. `trace` 가 없으면 「대화 기록 미발견」."""
    head = f"[agy 하트비트] 경과 {int(elapsed)}초"
    if trace is None:
        return head + " · 대화 기록 미발견"
    if trace.error:
        return head + f" · 대화 {trace.conversation[:8]} 읽기 실패 ({trace.error[:80]})"
    return (head + f" · 턴 {trace.turns} · 도구 {len(trace.tools)}"
            f" · 마지막 {tool_label(trace.last_tool)}")


def summary_line(trace: Trace | None, *, note: str = "") -> str:
    """끝 요약 한 줄 — 대화 id · 턴(초) · 도구를 파일별로 묶은 수."""
    tail = f" · {note}" if note else ""
    if trace is None:
        return "[agy 궤적] 대화 기록 미발견" + tail
    if trace.error:
        return f"[agy 궤적] 대화 {trace.conversation} · 읽기 실패 ({trace.error[:120]})" + tail
    turns = ",".join(_secs(s) for s in trace.turn_seconds)
    span = ""
    if trace.first_ts is not None and trace.last_ts is not None:
        span = f" · 기록 {int(round(trace.last_ts - trace.first_ts))}초"
    by = Counter()
    for tc in trace.tools:
        by[(tc.name, short_path(tc.path))] += 1
    tools = ", ".join(f"{n} {p}×{k}" if p else f"{n}×{k}" for (n, p), k in by.items()) or "없음"
    return (f"[agy 궤적] 대화 {trace.conversation} · 단계 {trace.steps} · 턴 {trace.turns} "
            f"({turns}초){span} · 마지막 단계 type={trace.last_step_type} status={trace.last_status}"
            f" · 도구 {len(trace.tools)}: {tools}" + tail)


def _main(argv=None) -> int:
    import sys
    for a in (argv if argv is not None else sys.argv[1:]):
        print(summary_line(read_trace(a)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
