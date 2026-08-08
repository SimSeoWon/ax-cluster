"""프로젝트 레지스트리 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_projects.py

실제 Gitea 저장소를 건드리지 않도록 `AX_GITEA_REPO_ROOT` 를 임시 디렉토리로 돌린다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ax-projects-test-"))
os.environ["AX_GITEA_REPO_ROOT"] = str(_TMP / "gitea")
os.environ["AX_PROJECTS_ROOT"] = str(_TMP / "root")

from master.projects import config as cfgmod  # noqa: E402
from master.projects.config import ConfigError, ProjectConfig, Registry  # noqa: E402
from master.projects.logic import (  # noqa: E402
    list_projects,
    register_project,
    resolve_bare_path,
    set_active,
)

cfgmod.GITEA_REPO_ROOT = _TMP / "gitea"

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def raises(label: str, fn, *a, **kw) -> None:
    try:
        fn(*a, **kw)
    except ConfigError as e:
        check(label, True)
        return
    check(label, False, "예외가 나지 않았다")


def make_bare(project_id: str) -> Path:
    p = _TMP / "gitea" / f"{project_id}.git"
    p.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", str(p)], check=True)
    return p


def fresh_root() -> Path:
    root = _TMP / "root"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    (root / "projects.yaml").write_text(
        "version: 1\nactive: ''\nprojects: []\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text("# test\n", encoding="utf-8")
    return root


def main() -> int:
    make_bare("sim/modularstage")
    make_bare("sim/other")

    print("\n[1] 루트 주입 — 폴백 없이 실패한다")
    saved = os.environ.pop("AX_PROJECTS_ROOT")
    raises("AX_PROJECTS_ROOT 없으면 ConfigError", cfgmod.projects_root)
    os.environ["AX_PROJECTS_ROOT"] = saved

    print("\n[2] 프로젝트명 검증 — 디렉토리명이 되므로 경로 조작을 막는다")
    for bad in ("../evil", "a/b", "", ".hidden", "has space"):
        raises(f"{bad!r} 거부", cfgmod.validate_name, bad)
    check("ModularStage 허용", cfgmod.validate_name("ModularStage") == "ModularStage")

    print("\n[3] bare 경로 해석 — 존재하지 않으면 추측하지 않는다")
    check(
        "project_id 로 해석",
        resolve_bare_path("sim/modularstage").endswith("sim/modularstage.git"),
    )
    raises("없는 저장소는 거부", resolve_bare_path, "sim/nope")
    raises("owner 없는 id 거부", resolve_bare_path, "modularstage")

    print("\n[4] 등록 — config.yaml 이 먼저 생기고 목록·gitignore·잠금이 따라온다")
    root = fresh_root()
    reg = Registry.load(root)
    res = register_project(
        "ModularStage", "sim/modularstage", branch="main", engine="5.8.1", registry=reg
    )
    d = root / "ModularStage"
    check("config.yaml 생성", (d / "config.yaml").is_file())
    check("context/ 생성", (d / "context").is_dir())
    check("ontology/domains/ 생성", (d / "ontology" / "domains").is_dir())
    check("목록 등록", "ModularStage" in Registry.load(root).names)
    check("첫 등록이 active 가 된다", Registry.load(root).active == "ModularStage")
    check("gitignore 한 줄", "/ModularStage/" in (root / ".gitignore").read_text())
    check("원본 잠금", (d / ".git").is_dir(), res.get("note", ""))
    check("워터마크는 비어 있다", ProjectConfig.load(d / "config.yaml").last_indexed_commit == "")

    print("\n[5] 중복 등록 거부")
    raises("같은 이름 재등록 거부", register_project, "ModularStage", "sim/other",
           registry=Registry.load(root))

    print("\n[6] 등록 실패 시 빈 디렉토리를 남기지 않는다")
    before = sorted(p.name for p in root.iterdir())
    raises("없는 저장소로 등록 거부", register_project, "Ghost", "sim/nope",
           registry=Registry.load(root))
    check("유령 디렉토리 없음", sorted(p.name for p in root.iterdir()) == before)

    print("\n[7] 전환")
    reg = Registry.load(root)
    register_project("Other", "sim/other", registry=reg)
    check("등록 후에도 active 는 그대로", Registry.load(root).active == "ModularStage")
    out = set_active("Other")
    check("전환됨", Registry.load(root).active == "Other", str(out))
    check("이전 값 보고", out["previous"] == "ModularStage")
    raises("등록되지 않은 이름 거부", set_active, "Nope")

    print("\n[8] 3자 일치 검사")
    check("정상 상태에서 문제 없음", Registry.load(root).check() == [])
    (root / "Other" / "config.yaml").write_text(
        "version: 1\nname: WrongName\n", encoding="utf-8"
    )
    problems = Registry.load(root).check()
    check("name 불일치 검출", any("WrongName" in p for p in problems), str(problems))
    shutil.rmtree(root / "ModularStage")
    problems = Registry.load(root).check()
    check("디렉토리 소실 검출", any("디렉토리가 없다" in p for p in problems), str(problems))

    print("\n[9] list_projects 는 깨진 항목도 보고한다")
    out = list_projects()
    check("목록 2건", len(out["projects"]) == 2, str(out))
    check("문제 보고", bool(out["problems"]))

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
