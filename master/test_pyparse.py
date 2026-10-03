"""파이썬 그래프 테스트 (`#712`). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_pyparse.py

[중요] 지키는 불변식:
   1. **클래스·부모·메서드**를 C++ 파서와 같은 모양으로 낸다
   2. **겹치는 이름만 모듈명** — 짧은 이름으로 어느 쪽인지 고르지 않는다(사용자 결정 2026-10-03)
   3. **테스트 파일은 클래스 그래프에서 뺀다** — import 의존에는 들어간다
   4. **import 는 저장소에 실재하는 파일로만** 푼다 — 외부 패키지는 버린다, 지어내지 않는다
   5. 🔴 **파이썬 간선은 경로 전체로 대조한다** — `__init__.py` 가 패키지마다 있어 basename 으로
      묶으면 한 간선이 모든 패키지에 걸린다(실측 2026-10-03)
   6. **UE 기본 경계는 종전 그대로** — `.py` 를 선언하지 않으면 그래프는 C++ 만 읽는다
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import DEFAULT_SCOPE, ProjectPaths, SourceScope  # noqa: E402
from master.graph import class_graph as cg, dependency as dep, pyparse             # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "from .util import helper\n"
        "from . import extra\n"
        "import os\n"
        "import requests\n"
        "class Base:\n    def a(self): pass\n"
        "class Child(Base, Generic[T]):\n    async def b(self): pass\n"
        "class Report:\n    pass\n"
        "def free(): pass\n"
    ),
    "pkg/util.py": "def helper(): pass\nclass Report:\n    pass\n",
    "pkg/extra.py": "from pkg.core import Base\n",
    "pkg/sub/__init__.py": "",
    "pkg/sub/deep.py": "from ..util import helper\nfrom ...nowhere import x\n",
    "pkg/test_core.py": "from .core import Child\nclass P:\n    pass\n",
}


def _repo(tmp: Path) -> ProjectPaths:
    repo = tmp / "repo"
    for rel, body in FILES.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "r1"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return ProjectPaths(name="PY", root=tmp, scope=SourceScope(roots=("pkg",), exts=(".py",)))


def main() -> int:
    print("① 파서 — 클래스·부모·메서드")
    cls = {c["name"]: c for c in pyparse.parse_source(FILES["pkg/core.py"])}
    check("모듈 최상위 클래스 셋", set(cls) == {"Base", "Child", "Report"}, str(set(cls)))
    check("부모: 이름만, Generic[T] 는 Generic", cls["Child"]["parents"] == ["Base", "Generic"],
          str(cls["Child"]["parents"]))
    check("async 메서드도 센다", [m["name"] for m in cls["Child"]["methods"]] == ["b"])
    check("함수는 클래스가 아니다", "free" not in cls)
    check("C++ 파서와 같은 키", set(cls["Base"]) == {"name", "parents", "line", "prefix", "kind", "methods"})
    check("문법 오류는 빈 목록", pyparse.parse_source("class (:\n") == [])

    print("② import 해석 — 실재 파일로만")
    known = set(FILES)
    got = pyparse.resolve_imports("pkg/core.py", FILES["pkg/core.py"], known)
    check("상대 import → 모듈 파일", "pkg/util.py" in got, str(got))
    check("`from . import extra` 는 하위 모듈", "pkg/extra.py" in got, str(got))
    check("[중요] 외부 패키지(os·requests)는 버린다", not any("os" in g or "requests" in g for g in got), str(got))
    check("절대 import", pyparse.resolve_imports("pkg/extra.py", FILES["pkg/extra.py"], known)
          == ["pkg/core.py"])
    deep = pyparse.resolve_imports("pkg/sub/deep.py", FILES["pkg/sub/deep.py"], known)
    check("두 단계 위 + 저장소 밖은 지어내지 않는다", deep == ["pkg/util.py"], str(deep))

    print("③ 이름 겹침 — 겹치는 것만 모듈명")
    entries = [("Report", {"file": "pkg/core.py"}), ("Report", {"file": "pkg/util.py"}),
               ("Base", {"file": "pkg/core.py"}), ("UThing", {"file": "Source/A.h"}),
               ("UThing", {"file": "Source/B.h"})]
    out, dup = pyparse.disambiguate(entries)
    names = [n for n, _ in out]
    check("겹친 파이썬 이름은 둘 다 모듈명", {"pkg.core.Report", "pkg.util.Report"} <= set(names), str(names))
    check("[중요] 짧은 이름 Report 는 남지 않는다 (고르지 않는다)", "Report" not in names)
    check("유일한 이름은 그대로", "Base" in names)
    check("C++ 은 종전대로 손대지 않는다", names.count("UThing") == 2)
    check("겹친 이름 목록", dup == ["Report"], str(dup))

    print("④ 실물 git — 클래스 그래프·의존 그래프 빌드")
    tmp = Path(tempfile.mkdtemp(prefix="ax-pyparse-"))
    try:
        p = _repo(tmp)
        gf = cg.graph_files(p)
        check("[중요] 테스트 파일은 클래스 그래프에서 빠진다", "pkg/test_core.py" not in gf, str(gf))
        st = cg.build_full(p)
        conn = cg.db.connect(p)
        rows = {r["name"]: r["file"] for r in conn.execute("SELECT name, file FROM classes")}
        conn.close()
        check("클래스가 들어갔다", {"Base", "Child", "pkg.core.Report", "pkg.util.Report"} <= set(rows),
              str(rows))
        check("테스트 보조 클래스 P 는 없다", "P" not in rows)
        check("요약에 겹침이 보인다", "모듈명 붙임" in st.summary, st.summary)
        # 조상 탐색은 다중 상속을 펼친다(`parents_json`) — `Generic` 도 나오는 것이 종전 규칙이다
        check("상속이 탄다", cg.find_ancestors(p, "Child") == ["Base", "Generic"],
              str(cg.find_ancestors(p, "Child")))
        d = dep.build_full(p)
        check("간선이 생긴다 (종전 0)", d.edges >= 4, str(d.edges))
        deps = dep.dependencies(p, "pkg/core.py", depth=1)
        # `from . import extra` 는 패키지 `__init__.py` 도 실행한다 — 의존에 드는 것이 맞다
        check("정방향 의존", set(deps) == {"pkg/__init__.py", "pkg/util.py", "pkg/extra.py"}, str(deps))
        check("테스트 파일의 import 는 의존에 들어간다",
              "pkg/test_core.py" in dep.dependents(p, "pkg/core.py", depth=1))
        init_users = dep.dependents(p, "pkg/sub/__init__.py", depth=1)
        check("🔴 `__init__.py` 를 basename 으로 묶지 않는다", init_users == [], str(init_users))
        ue = ProjectPaths(name="UE", root=tmp, scope=DEFAULT_SCOPE)
        check("[중요] UE 기본 경계는 .py 를 그래프로 안 읽는다", ".py" not in cg._parse_exts(ue))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_pyparse: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
