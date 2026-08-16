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
from master.projects.config import (  # noqa: E402
    ConfigError,
    ProjectConfig,
    Registry,
    normalize_project_id,
    project_id_disk_path,
)
from master.projects.logic import (  # noqa: E402
    list_projects,
    list_workshops,
    register_project,
    remove_workshop,
    resolve_bare_path,
    set_active,
    set_workshop,
)

cfgmod.GITEA_REPO_ROOT = _TMP / "gitea"

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


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

    print("\n[10] 워크숍 등록 (§5.5.4)")
    # [8] 이 ModularStage 를 지웠으므로 깨끗한 레지스트리를 새로 만든다.
    root2 = _TMP / "root2"
    root2.mkdir(parents=True, exist_ok=True)
    (root2 / "projects.yaml").write_text(
        "version: 1\nactive: ''\nprojects: []\n", encoding="utf-8"
    )
    os.environ["AX_PROJECTS_ROOT"] = str(root2)
    make_bare("sim/modularstage")
    register_project("ModularStage", "sim/modularstage")
    set_active("ModularStage")

    WIN_PATH = r"E:\trunk\ModularStage"

    out = set_workshop(
        "ModularStage", "192.168.0.2", driven="ssh", user="janus", path=WIN_PATH
    )
    check("ssh 워크숍 등록", out["ok"] and out["drivable"], str(out))
    out = set_workshop("ModularStage", "192.168.0.33", driven="interactive")
    check("interactive 는 path 없이 등록됨", out["ok"] and not out["drivable"], str(out))

    print("\n[11] [중요] 윈도우 경로 백슬래시 round-trip")
    # YAML 이 `E:\trunk` 를 double-quote 로 감싸면 \t 가 **탭**으로 해석된다.
    # 경로가 조용히 깨지는 종류의 사고라 반드시 원문 대조한다.
    cfg = Registry.load(root2).config_of("ModularStage")
    got = cfg.workshops["192.168.0.2"].path
    check("경로가 원문 그대로", got == WIN_PATH, f"기대 {WIN_PATH!r} / 실제 {got!r}")
    check("탭으로 깨지지 않음", "\t" not in got, repr(got))
    raw = (root2 / "ModularStage" / "config.yaml").read_text(encoding="utf-8")
    check("파일에도 역슬래시가 남아 있음", r"E:\trunk" in raw)

    print("\n[12] 워크숍 검증 — fail-closed")
    raises(
        "ssh 인데 path 없으면 거부",
        set_workshop, "ModularStage", "10.0.0.9", driven="ssh", user="x",
    )
    raises(
        "ssh 인데 user 없으면 거부",
        set_workshop, "ModularStage", "10.0.0.9", driven="ssh", path="C:\\x",
    )
    raises(
        "driven 값이 이상하면 거부",
        set_workshop, "ModularStage", "10.0.0.9", driven="rdp",
    )
    raises("host 가 비면 거부", set_workshop, "ModularStage", "   ")
    raises("등록되지 않은 프로젝트 거부", set_workshop, "NoSuch", "10.0.0.9")
    cfg = Registry.load(root2).config_of("ModularStage")
    check("거부된 항목이 파일에 남지 않음", "10.0.0.9" not in cfg.workshops, str(cfg.workshops))

    print("\n[13] 같은 host 재등록은 병합이 아니라 교체")
    out = set_workshop("ModularStage", "192.168.0.2", driven="interactive")
    check("교체됨 — driven 변경", out["workshop"]["driven"] == "interactive", str(out))
    check("이전 값 보고", out["replaced"] and out["replaced"]["driven"] == "ssh", str(out))
    cfg = Registry.load(root2).config_of("ModularStage")
    shop = cfg.workshops["192.168.0.2"]
    check("예전 path 가 남지 않음", shop.path == "", repr(shop.path))
    check("예전 user 가 남지 않음", shop.user == "", repr(shop.user))

    print("\n[14] 목록 · 해제")
    set_workshop("ModularStage", "192.168.0.2", driven="ssh", user="janus", path=WIN_PATH)
    out = list_workshops()
    check("active 프로젝트를 기본으로 본다", out["project"] == "ModularStage", str(out))
    check("워크숍 2건", len(out["workshops"]) == 2, str(out))
    check("drivable 은 .2 뿐", out["drivable_hosts"] == ["192.168.0.2"], str(out))
    check(
        "list_projects 에도 실린다",
        "192.168.0.2" in list_projects()["projects"][0]["workshops"],
        str(list_projects()),
    )
    out = remove_workshop("ModularStage", "192.168.0.33")
    check("해제됨", out["ok"], str(out))
    check("목록에서 빠짐", len(list_workshops()["workshops"]) == 1)
    raises("없는 워크숍 해제 거부", remove_workshop, "ModularStage", "192.168.0.33")

    print("\n[15] [중요] project_id 대소문자 — 표시 이름 vs 동일성 (§5.5.4-④)")
    # Gitea DB 실측: owner_name/name = 'Sim/ModularStage' (훅이 싣는 값),
    #                lower_name      = 'modularstage'     (디스크 · 동일성).
    check("normalize 는 casefold", normalize_project_id("Sim/ModularStage") == "sim/modularstage")
    check("공백도 제거", normalize_project_id("  Sim/ModularStage  ") == "sim/modularstage")
    check("빈 값은 빈 값", normalize_project_id("") == "")
    check(
        "디스크 경로는 소문자로 접힌다",
        project_id_disk_path("Sim/ModularStage") == "sim/modularstage",
    )

    # 정규 표시값으로 저장해도 bare 경로는 소문자로 찾아야 한다 —
    # 이걸 안 접으면 gitea-repositories/Sim/ModularStage.git 을 찾다 실패한다.
    got = resolve_bare_path("Sim/ModularStage")
    check(
        "resolve_bare_path 가 대문자 project_id 로도 찾는다",
        got.endswith("sim/modularstage.git"),
        got,
    )

    print("\n[16] 훅 페이로드 → 프로젝트 조회는 대소문자를 무시한다")
    root3 = _TMP / "root3"
    root3.mkdir(parents=True, exist_ok=True)
    (root3 / "projects.yaml").write_text(
        "version: 1\nactive: ''\nprojects: []\n", encoding="utf-8"
    )
    os.environ["AX_PROJECTS_ROOT"] = str(root3)
    register_project("ModularStage", "Sim/ModularStage")   # 정규 표시값으로 등록
    reg3 = Registry.load(root3)
    check(
        "config 에는 정규 표시값이 그대로 남는다",
        reg3.config_of("ModularStage").project_id == "Sim/ModularStage",
        reg3.config_of("ModularStage").project_id,
    )
    check("훅이 정규값으로 와도 찾는다", reg3.find_by_project_id("Sim/ModularStage") == "ModularStage")
    check("소문자로 와도 찾는다", reg3.find_by_project_id("sim/modularstage") == "ModularStage")
    check("대소문자 rename 후에도 찾는다", reg3.find_by_project_id("SIM/MODULARSTAGE") == "ModularStage")
    check("없는 저장소는 빈 문자열", reg3.find_by_project_id("Sim/Other") == "")
    check("빈 입력은 빈 문자열", reg3.find_by_project_id("") == "")

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
