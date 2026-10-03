"""색인·합성 경계 `SourceScope` (`#693`) — 비UE 프로젝트를 `Source/` 밖에서 색인한다.

재는 것:
  ① 기본 경계는 종전과 **글자까지 같다** (`Source/` · C++ · `ls-files -- Source`)
  ② `config.yaml` 의 `source:` 해석 — 깨진 선언은 예외(기본값으로 접지 않는다)
  ③ 🔴 **진짜 git + 진짜 서브모듈**로 목록·제외·확장자가 맞는가 (흉내로는 `--recurse-submodules`
     계약이 빠진다)
  ④ 🔴 포인터 변경(gitlink)을 서브모듈 안 변경 파일로 **펼친다** — 안 펼치면 원본을 따라간
     커밋이 「소스 밖 변경」으로 접혀 문서가 영영 안 갱신된다
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_search.paths import (DEFAULT_SCOPE, ProjectPaths, SourceScope,  # noqa: E402
                                         scope_of)
from master.events import consumer as C  # noqa: E402
from master.graph import class_graph as cg  # noqa: E402
from master.projects.config import ConfigError  # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def git(cwd, *a):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    p = subprocess.run(["git", "-c", "protocol.file.allow=always", "-C", str(cwd), *a],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, (a, p.stderr)
    return p.stdout.strip()


KIMODO = SourceScope(roots=("webui", "scripts", "vendor/eng"), exclude=("vendor/eng/ggml",),
                     exts=(".py", ".h", ".cpp"), submodules=("vendor/eng",))


def test_default_is_unchanged():
    print("\n① 기본 경계는 종전과 같다")
    check("roots = Source", DEFAULT_SCOPE.roots == ("Source",))
    check("Source/ 의 C++ 는 안", DEFAULT_SCOPE.contains("Source/A/B.cpp", (".cpp", ".h")))
    check("Content/ 는 밖", not DEFAULT_SCOPE.contains("Content/A.uasset", (".cpp",)))
    check("[주의] 접두만 같은 이름은 밖 (SourceX/)", not DEFAULT_SCOPE.contains("SourceX/a.cpp", (".cpp",)))
    p = ProjectPaths(name="M", root=Path("/t/M"))
    check("[중요] ls-files 인자가 종전과 글자까지 같다",
          cg.ls_files_args(p) == ["ls-files", "--", "Source"], str(cg.ls_files_args(p)))


def test_contains_rules():
    print("\n② 제외·확장자")
    check("루트 안 .py", KIMODO.contains("webui/server.py"))
    check("[중요] 제외(ggml) 는 밖", not KIMODO.contains("vendor/eng/ggml/src/x.cpp"))
    check("서브모듈 본체는 안", KIMODO.contains("vendor/eng/src/a.cpp"))
    check("선언 안 한 확장자는 밖", not KIMODO.contains("webui/static/app.js"))
    check("루트 밖은 밖", not KIMODO.contains("docs/x.py"))


def test_scope_of(tmp: Path):
    print("\n③ config.yaml `source:` 해석")
    (tmp / "config.yaml").write_text("name: K\n", encoding="utf-8")
    check("절이 없으면 기본값", scope_of(tmp) == DEFAULT_SCOPE)
    (tmp / "config.yaml").write_text(
        "name: K\nsource:\n  roots: [webui, vendor/eng/]\n  exclude: [vendor/eng/ggml]\n"
        "  exts: [.py]\n  submodules: [vendor/eng]\n", encoding="utf-8")
    sc = scope_of(tmp)
    check("roots·exclude·exts·submodules 를 읽는다 (끝 슬래시는 뗀다)",
          sc.roots == ("webui", "vendor/eng") and sc.exclude == ("vendor/eng/ggml",)
          and sc.exts == (".py",) and sc.submodules == ("vendor/eng",), repr(sc))
    for bad, txt in (("모르는 키", "source:\n  root: [x]\n"),
                     ("roots 가 비었다", "source:\n  exts: [.py]\n"),
                     ("문자열 하나", "source:\n  roots: webui\n")):
        (tmp / "config.yaml").write_text("name: K\n" + txt, encoding="utf-8")
        try:
            scope_of(tmp)
            check(f"[중요] 깨진 선언은 예외 — {bad}", False, "예외가 안 났다")
        except ConfigError:
            check(f"[중요] 깨진 선언은 예외 — {bad}", True)


def _make_repo(tmp: Path):
    """진짜 저장소 + 진짜 서브모듈(안에 ggml 흉내 디렉토리)을 만든다."""
    eng = tmp / "eng"
    eng.mkdir()
    git(eng, "init", "-q", "-b", "main")
    (eng / "src").mkdir()
    (eng / "src" / "a.cpp").write_text("int a;\n")
    (eng / "ggml").mkdir()
    (eng / "ggml" / "g.cpp").write_text("int g;\n")
    git(eng, "add", "-A")
    git(eng, "commit", "-qm", "e1")
    e1 = git(eng, "rev-parse", "HEAD")
    root = tmp / "root"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "webui").mkdir()
    (root / "webui" / "server.py").write_text("x = 1\n")
    (root / "docs").mkdir()
    (root / "docs" / "n.py").write_text("y = 1\n")
    git(root, "submodule", "add", "-q", str(eng), "vendor/eng")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "r1")
    r1 = git(root, "rev-parse", "HEAD")
    return eng, root, e1, r1


def test_real_git_listing_and_gitlink_expansion(tmp: Path):
    print("\n④ 🔴 진짜 git — 목록과 포인터 펼치기")
    eng, root, e1, r1 = _make_repo(tmp)
    p = ProjectPaths(name="K", root=tmp, clone_dir="root", scope=KIMODO)
    files = cg.list_source_files(p)
    check("루트의 .py 가 나온다", "webui/server.py" in files, str(files))
    check("[중요] 서브모듈 안 파일이 나온다 (--recurse-submodules)", "vendor/eng/src/a.cpp" in files, str(files))
    check("[중요] 제외(ggml)는 안 나온다", not any("ggml" in f for f in files), str(files))
    check("루트 밖(docs/)은 안 나온다", "docs/n.py" not in files, str(files))
    # 🔴 `#712`(사용자 결정 2026-10-03) — 그래프는 **경계가 선언한 `.py` 도** 읽는다(종전 `#693`: C++ 만).
    #    테스트 파일은 뺀다. 선언 안 한 기본 경계(UE)는 종전 그대로 C++ 만이다.
    check("graph_files 는 C++ + 선언된 .py", sorted(cg.graph_files(p)) == ["vendor/eng/src/a.cpp", "webui/server.py"],
          str(cg.graph_files(p)))

    # 원본을 따라간 것처럼 서브모듈을 한 칸 전진시키고 루트에서 포인터를 커밋한다
    (eng / "src" / "b.cpp").write_text("int b;\n")
    (eng / "ggml" / "g.cpp").write_text("int g2;\n")
    git(eng, "add", "-A")
    git(eng, "commit", "-qm", "e2")
    sub = root / "vendor" / "eng"
    git(sub, "fetch", "-q", "origin")
    git(sub, "checkout", "-q", "origin/main")
    git(root, "add", "vendor/eng")
    git(root, "commit", "-qm", "r2 bump")
    r2 = git(root, "rev-parse", "HEAD")
    touched = git(root, "diff", "--name-only", r1, r2, "--", *KIMODO.roots).splitlines()
    check("루트 diff 는 포인터 한 줄만 안다", touched == ["vendor/eng"], str(touched))
    out, why = C._expand_gitlinks(p, r1, r2, touched, C._git)
    check("[중요] 펼치면 서브모듈 안 변경 파일이 된다", "vendor/eng/src/b.cpp" in out, f"{out} {why}")
    check("  사유 없음", why == "", why)
    changed = C._source_only(out, p)
    check("[중요] 제외(ggml) 변경은 경계에서 떨어진다", changed == ["vendor/eng/src/b.cpp"], str(changed))
    out0, why0 = C._expand_gitlinks(p, C.EMPTY_TREE, r1, ["vendor/eng", "webui/server.py"], C._git)
    check("첫 커밋(빈 트리 기준)은 서브모듈 전체를 펼친다",
          "vendor/eng/src/a.cpp" in out0 and "webui/server.py" in out0, f"{out0} {why0}")


def test_mount_gate_has_no_exception():
    print("\n⑤ 🔴 마운트 게이트 — 예외 없음 (사용자: 마운트 된것만 갱신)")
    src = Path(C.__file__).read_text(encoding="utf-8")
    check("비마운트는 타입과 무관하게 막는다", "    if name != mounted:\n" in src)
    check("  index_only 예외가 없다", "not index_only" not in src)


def test_search_routes_only_mounted():
    print("\n⑥ 🔴 검색은 마운트된 것만")
    from master.webui.app import search_paths

    class P:
        def __init__(self, n): self.name = n
    ns = P("NS")
    check("태그 없음 → 마운트", search_paths(ns, "")[0] is ns)
    check("태그 == 마운트 → 마운트", search_paths(ns, "NS")[0] is ns)
    for tag in ("KimodoMotion_WebUI", "ModularStage"):
        got, why = search_paths(ns, tag)
        check(f"🔴 비마운트 태그({tag}) → 거절 (색인 전용도 예외 없음)", got is None and "not_mounted" in why, why)
    src = (Path(__file__).resolve().parents[1] / "client" / "runtime" / "client_mcp.py").read_text(encoding="utf-8")
    i = src.index("def projects_api(")
    check("클라 8103 호출자가 태그를 싣는다", '"project": project' in src[i:i + 1400])


def main() -> int:
    test_default_is_unchanged()
    test_contains_rules()
    d = Path(tempfile.mkdtemp())
    try:
        (d / "a").mkdir()
        test_scope_of(d / "a")
        (d / "b").mkdir()
        test_real_git_listing_and_gitlink_expansion(d / "b")
    finally:
        shutil.rmtree(d)
    test_mount_gate_has_no_exception()
    test_search_routes_only_mounted()
    print(f"{'OK' if not FAIL else 'FAIL'} test_source_scope: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
