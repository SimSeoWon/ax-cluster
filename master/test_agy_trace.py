"""agy 대화 기록 판독기 (`#888` T1) — `master/agy_trace.py`.

검증하는 것:

    ① 합성 DB(같은 스키마)에서 턴 수·턴별 초·도구 호출·마지막 상태를 읽는다
    ② WAL 모드 DB 의 **체크포인트 안 된 행**도 읽는다 — 그리고 원본 파일을 바꾸지 않는다
    ③ 깨진 파일 · 없는 파일 · steps 표 없음 → `error` 만 채우고 던지지 않는다
    ④ `find_conversation` — 마커가 든 대화만 · `since` 이전은 무시 · 없으면 None · 오류면 None
    ⑤ 한 줄 표시(하트비트·요약)의 모양
    ⑥ 실측 사본 4건(있을 때만) — 턴 14/5/2/2 · read_file 14(고정 트리 13)/4/1/1

`.venv/bin/python master/test_agy_trace.py`
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master import agy_trace as T                                 # noqa: E402

PASS = FAIL = 0
# 실측 표본(2026-11-05 대화 4건의 `.db`·`.db-wal` 사본)이 든 디렉터리 — 없으면 건너뛴다.
# 세션 임시 경로를 박지 않는다: 표본은 세션과 함께 사라진다 (`#888`).
REAL = Path(os.environ.get("AX_AGY_TRACE_SAMPLES", "/nonexistent-ax-agy-trace-samples"))


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── protobuf 인코더(합성용) ────────────────────────────────────────────────

def _v(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def fv(f: int, n: int) -> bytes:
    return _v(f << 3) + _v(n)


def fb(f: int, b) -> bytes:
    if isinstance(b, str):
        b = b.encode()
    return _v((f << 3) | 2) + _v(len(b)) + b


def ts(sec: float) -> bytes:
    s = int(sec)
    return fv(1, s) + fv(2, int(round((sec - s) * 1e9)))


def meta(start: float, end: float, tool: tuple | None = None) -> bytes:
    """실측 모양: 1=생성 시각 · 6/7/8 · 26{1{1:k, 2:ts}} · 32 · (도구면) 4{1:id, 2:이름, 3:JSON}."""
    m = fb(1, ts(start)) + fb(6, ts(start)) + fb(7, ts(end)) + fb(8, ts(end))
    m += fb(26, fb(1, fv(1, 1) + fb(2, ts(start))) + fb(1, fv(1, 2) + fb(2, ts(end))))
    m += fb(32, ts(end))
    if tool:
        m += fb(4, fb(1, "call_1") + fb(2, tool[0]) + fb(3, tool[1]))
    return m


SCHEMA = ("CREATE TABLE `steps` (`idx` integer,`step_type` integer NOT NULL DEFAULT 0,"
          "`status` integer NOT NULL DEFAULT 0,`has_subtrajectory` numeric NOT NULL DEFAULT false,"
          "`metadata` blob,`error_details` blob,`permissions` blob,`task_details` blob,"
          "`render_info` blob,`step_payload` blob,`step_format` integer NOT NULL DEFAULT 0,"
          "PRIMARY KEY (`idx`))")
T0 = 1_793_883_681.0


def rows(brief: str):
    """사용자 입력 → 턴(4초) → read_file BRIEF → 턴(30초) → read_file 고정 트리 → 턴(5초, 끊김 status 8)."""
    tool1 = ("read_file", '{"Path":"%s/BRIEF.md"}' % brief)
    tool2 = ("read_file", '{"EndLine":815,"Path":"/tmp/ax-pinned-abc/tree/master/x.py",'
                          '"StartLine":780}')
    return [
        (0, 14, 3, meta(T0, T0), fb(1, f"see {brief}/BRIEF.md")),
        (1, 15, 3, meta(T0, T0 + 4), b"turn"),
        (2, 132, 3, meta(T0 + 4, T0 + 4, tool1), b"result"),
        (3, 15, 3, meta(T0 + 4, T0 + 34), b"turn"),
        (4, 132, 3, meta(T0 + 34, T0 + 34, tool2), b"result"),
        (5, 15, 8, meta(T0 + 34, T0 + 39), b"turn"),
    ]


def make_db(path: Path, data, *, wal: bool = False, keep_open: bool = False):
    c = sqlite3.connect(str(path))
    if wal:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute(SCHEMA)
    c.commit()
    c.executemany("INSERT INTO steps (idx, step_type, status, metadata, step_payload) "
                  "VALUES (?,?,?,?,?)", data)
    c.commit()
    if keep_open:
        return c
    c.close()
    return None


def test_합성_궤적():
    td = Path(tempfile.mkdtemp())
    db = td / "11111111-aaaa.db"
    make_db(db, rows("/tmp/ax-agy-zz1"))
    tr = T.read_trace(db)
    check("① 오류 없음", tr.error == "", tr.error)
    check("① id 는 파일 이름", tr.conversation == "11111111-aaaa", tr.conversation)
    check("① 단계 6 · 턴 3", (tr.steps, tr.turns) == (6, 3), f"{tr.steps} {tr.turns}")
    check("① 턴별 초", tr.turn_seconds == [4.0, 30.0, 5.0], str(tr.turn_seconds))
    check("① 도구 2건", [t.name for t in tr.tools] == ["read_file", "read_file"], str(tr.tools))
    last = tr.last_tool
    check("① 마지막 도구 경로·줄", last is not None and
          (last.path, last.start, last.end) == ("/tmp/ax-pinned-abc/tree/master/x.py", 780, 815),
          str(last))
    check("① 첫·끝 시각", (tr.first_ts, tr.last_ts) == (T0, T0 + 39), f"{tr.first_ts} {tr.last_ts}")
    check("① 마지막 상태", (tr.last_step_type, tr.last_status) == (15, 8))
    hb = T.heartbeat_line(42.7, tr)
    check("⑤ 하트비트 한 줄", hb == "[agy 하트비트] 경과 42초 · 턴 3 · 도구 2 · 마지막 "
          "read_file master/x.py:780-815", hb)
    check("⑤ 미발견 하트비트", T.heartbeat_line(20, None) == "[agy 하트비트] 경과 20초 · 대화 기록 미발견")
    sm = T.summary_line(tr, note="diff 잘림")
    check("⑤ 요약에 id·턴 초·도구 파일별", "대화 11111111-aaaa" in sm and "턴 3 (4,30,5초)" in sm
          and "read_file BRIEF.md×1" in sm and "read_file master/x.py×1" in sm
          and sm.endswith("· diff 잘림"), sm)
    check("⑤ 요약 미발견", T.summary_line(None, note="x") == "[agy 궤적] 대화 기록 미발견 · x")
    shutil.rmtree(td)


def test_WAL_미체크포인트():
    td = Path(tempfile.mkdtemp())
    db = td / "22222222-wal.db"
    conn = make_db(db, rows("/tmp/ax-agy-wal"), wal=True, keep_open=True)
    try:
        wal = db.with_name(db.name + "-wal")
        check("② 행이 WAL 에만 있다(전제)", wal.is_file() and wal.stat().st_size > 0)
        # 본 파일만으로는 안 보인다는 전제 — 본 파일만 따로 복사해 열면 표가 비어 있다
        solo = td / "solo.db"
        shutil.copyfile(db, solo)
        try:
            n = sqlite3.connect(str(solo)).execute("SELECT count(*) FROM steps").fetchone()[0]
        except sqlite3.Error:
            n = -1
        check("② 전제: 본 파일만으론 행이 안 보인다", n in (0, -1), str(n))
        before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                  for p in td.iterdir() if p.name.startswith("22222222")}
        tr = T.read_trace(db)
        check("② WAL 의 행을 읽는다", (tr.error, tr.steps, tr.turns) == ("", 6, 3),
              f"{tr.error} {tr.steps} {tr.turns}")
        found = T.find_conversation("/tmp/ax-agy-wal", since=time.time() - 60, root=td)
        check("② WAL 대화도 찾는다", found == db, str(found))
        after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                 for p in td.iterdir() if p.name.startswith("22222222")}
        check("② 원본 파일을 건드리지 않는다", before == after, f"{before} {after}")
        # 라이브 연결이 계속 쓸 수 있다
        conn.execute("INSERT INTO steps (idx, step_type, status) VALUES (6, 15, 3)")
        conn.commit()
        check("② 그 뒤에도 라이브 쓰기 정상", T.read_trace(db).steps == 7)
    finally:
        conn.close()
    shutil.rmtree(td)


def test_깨진_파일():
    td = Path(tempfile.mkdtemp())
    bad = td / "33333333-bad.db"
    bad.write_bytes(b"this is not sqlite" * 100)
    tr = T.read_trace(bad)
    check("③ 깨진 파일 → error", bool(tr.error) and tr.steps == 0, tr.error)
    check("③ 깨진 파일 요약도 한 줄", "읽기 실패" in T.summary_line(tr))
    tr = T.read_trace(td / "nope.db")
    check("③ 없는 파일 → error", bool(tr.error), tr.error)
    empty = td / "44444444-empty.db"
    sqlite3.connect(str(empty)).close()
    tr = T.read_trace(empty)
    check("③ steps 표 없음 → error", "no such table" in tr.error, tr.error)
    check("④ 깨진 파일만 있으면 None",
          T.find_conversation("/tmp/ax-agy-x", since=0, root=td) is None)
    check("④ 없는 루트 → None", T.find_conversation("/x", since=0, root=td / "none") is None)
    check("④ 빈 마커 → None", T.find_conversation("", since=0, root=td) is None)
    check("④ 이상한 인자에도 안 던진다", T.find_conversation("/x", since="bad", root=td) is None)
    shutil.rmtree(td)


def test_찾기():
    td = Path(tempfile.mkdtemp())
    a, b, old = td / "aaaa.db", td / "bbbb.db", td / "oldd.db"
    make_db(a, rows("/tmp/ax-agy-AAA"))
    make_db(b, rows("/tmp/ax-agy-BBB"))
    make_db(old, rows("/tmp/ax-agy-OLD"))
    past = time.time() - 3600
    os.utime(old, (past, past))
    now = time.time() - 60
    check("④ 마커로 고른다", T.find_conversation("/tmp/ax-agy-BBB", since=now, root=td) == b)
    check("④ 다른 마커", T.find_conversation("/tmp/ax-agy-AAA", since=now, root=td) == a)
    check("④ since 이전 대화는 무시",
          T.find_conversation("/tmp/ax-agy-OLD", since=now, root=td) is None)
    check("④ since 를 당기면 찾는다",
          T.find_conversation("/tmp/ax-agy-OLD", since=past - 1, root=td) == old)
    check("④ 맞는 게 없으면 None",
          T.find_conversation("/tmp/ax-agy-NONE", since=0, root=td) is None)
    shutil.rmtree(td)


REAL_EXPECT = {
    # id 앞부분: (턴, read_file 전체, 고정 트리 read_file, 마지막 단계 type, status)
    "a47ece33": (14, 14, 13, 132, 3),
    "0f89eab7": (5, 4, 1, 15, 3),
    "d97d2b3b": (2, 1, 0, 15, 3),
    "fe7e9ace": (2, 1, 0, 15, 8),
}


def test_실측_사본():
    if not REAL.is_dir():
        print("  [건너뜀] 실측 사본 없음 —", REAL)
        return
    for prefix, (turns, reads, pinned, ltype, lstatus) in REAL_EXPECT.items():
        dbs = list(REAL.glob(prefix + "*.db"))
        if not dbs:
            print(f"  [건너뜀] {prefix} 사본 없음")
            continue
        tr = T.read_trace(dbs[0])
        rf = [t for t in tr.tools if t.name == "read_file"]
        np_ = sum(1 for t in rf if t.path.startswith("/tmp/ax-pinned-"))
        check(f"⑥ {prefix} 턴·read_file·고정트리·끝 상태",
              (tr.error, tr.turns, len(rf), np_, tr.last_step_type, tr.last_status)
              == ("", turns, reads, pinned, ltype, lstatus),
              f"{tr.error} {tr.turns} {len(rf)} {np_} {tr.last_step_type} {tr.last_status}")
    d = list(REAL.glob("d97d2b3b*.db"))
    if d:
        tr = T.read_trace(d[0])
        check("⑥ d97d 마지막 턴 ≈224초(본문을 쓰던 턴)",
              tr.turn_seconds and 223 <= tr.turn_seconds[-1] <= 225, str(tr.turn_seconds))
    o = list(REAL.glob("0f89eab7*.db"))
    if o:
        tr = T.read_trace(o[0])
        exp = [4, 5, 27, 49, 122]
        check("⑥ 0f89 턴 초(±1)", len(tr.turn_seconds) == 5 and
              all(abs(x - y) <= 1 for x, y in zip(tr.turn_seconds, exp)), str(tr.turn_seconds))
        brief = T.find_conversation("/tmp/ax-agy-x33rrp15", since=0, root=REAL)
        check("⑥ 0f89 를 BRIEF 경로로 찾는다", brief is not None and brief.name.startswith("0f89eab7"),
              str(brief))


if __name__ == "__main__":
    for fn in (test_합성_궤적, test_WAL_미체크포인트, test_깨진_파일, test_찾기, test_실측_사본):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
