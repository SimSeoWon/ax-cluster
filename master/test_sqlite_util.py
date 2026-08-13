"""SQLite 동시성 PRAGMA (소 3.5.3) — 🔴 **세 DB 전부** 걸려 있는지 잰다.

이 테스트가 존재하는 이유: 2026-08-14 에 `graph/db.py`·`graph/dependency.py` 에는 걸려 있고
**`context_search/bm25.py` 만 빠져 있는 것**이 발견됐다. `graph/db.py` 스스로 *"프로세스 간에는
WAL + busy_timeout 이 담당한다"* 고 적어 두고도 형제 모듈에서 빠뜨렸다 — **값이 흩어지면 어긋난다.**

⚠️ 실측 정정(2026-08-14): 원전은 *"기본 `busy_timeout=0`"* 이라 적었는데 그건 **raw SQLite** 기준이고
Python `sqlite3.connect` 는 `timeout=5.0` 기본값이라 **5000** 이 걸린다. 실제 갭은 **WAL 부재**였다 —
WAL 이 없으면 읽기↔쓰기가 서로 막아 타임아웃에 닿을 확률이 크게 오른다.

`.venv/bin/python master/test_sqlite_util.py`
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import sqlite_util as S      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def test_apply_sets_both():
    with tempfile.TemporaryDirectory() as td:
        c = sqlite3.connect(str(Path(td) / "t.db"))
        got = S.check(c)
        check("적용 전에는 WAL 이 아니다", got["journal_mode"] != "wal", str(got))
        S.apply(c)
        got = S.check(c)
        check("WAL 이 걸린다", got["journal_mode"] == "wal", str(got))
        check(f"busy_timeout 이 {S.BUSY_TIMEOUT_MS}", got["busy_timeout"] == S.BUSY_TIMEOUT_MS, str(got))
        check("같은 연결을 돌려준다", S.apply(c) is c)


def test_synchronous_optional():
    with tempfile.TemporaryDirectory() as td:
        c = sqlite3.connect(str(Path(td) / "t.db"))
        before = c.execute("PRAGMA synchronous").fetchone()[0]
        S.apply(c)
        check("기본은 synchronous 를 건드리지 않는다",
              c.execute("PRAGMA synchronous").fetchone()[0] == before)
        S.apply(c, synchronous="NORMAL")
        check("주면 건다", c.execute("PRAGMA synchronous").fetchone()[0] == 1)


def test_value_is_single_owner():
    """🔴 값이 코드에 다시 박혀 있지 않은지 — 흩어지면 어긋난다."""
    root = Path(__file__).resolve().parent
    offenders = []
    for f in list((root / "graph").glob("*.py")) + list((root / "context_search").glob("*.py")):
        if f.name.startswith("test_"):
            continue
        t = f.read_text(encoding="utf-8")
        # 주석은 허용, 실제 execute 로 박은 것만 잡는다
        for ln in t.splitlines():
            st = ln.strip()
            if st.startswith("#"):
                continue
            if "busy_timeout" in st and "execute" in st:
                offenders.append(f"{f.name}: {st[:60]}")
    check("busy_timeout 을 직접 execute 하는 곳이 없다", not offenders, "; ".join(offenders))


def test_three_dbs_wired():
    """세 연결 지점이 헬퍼를 쓰는가 (import 존재로 확인)."""
    root = Path(__file__).resolve().parent
    for rel in ("graph/db.py", "graph/dependency.py", "context_search/bm25.py"):
        t = (root / rel).read_text(encoding="utf-8")
        check(f"{rel} 이 헬퍼를 쓴다", "sqlite_util.apply(" in t)


def main() -> int:
    for fn in (test_apply_sets_both, test_synchronous_optional,
               test_value_is_single_owner, test_three_dbs_wired):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_sqlite_util: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
