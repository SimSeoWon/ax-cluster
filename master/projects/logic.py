"""프로젝트 등록·전환 로직 (PLAN §5.5).

등록 순서는 **설정 파일 생성이 먼저다**:

    1. 디렉토리 생성            <root>/<Name>/
    2. config.yaml 작성         무엇을 추적하는지 — 이게 없으면 나머지가 의미가 없다
    3. 루트 목록 등록           projects.yaml 의 projects 에 추가
    4. .gitignore 한 줄         ax-cluster 에 커밋되지 않도록 (§5.5.3-① 유지보수 함정)
    5. git init                 원본(context/·ontology/)을 잠근다. 원격 없음·훅 없음

2 번이 실패하면 1 번에서 만든 빈 디렉토리를 되돌린다 — 목록에 없는 유령 디렉토리가
남으면 3자 일치 검사가 계속 걸린다.

🔴 5 번의 "원격 없음·훅 없음"은 취향이 아니라 **불변식**이다(§5.5.3-d). 색인 산출물이
훅 이벤트를 만들면 무한 재귀가 된다.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from .config import (
    GITEA_REPO_ROOT,
    PROJECT_CONFIG,
    ConfigError,
    ProjectConfig,
    Registry,
    validate_name,
    write_project_config,
)

DEFAULT_INCLUDE = ["Source/**/*.cpp", "Source/**/*.h", "Source/**/*.cs", "Config/**"]
# UE5 프로젝트는 용량의 대부분이 uasset 바이너리다 (ModularStage 실측: 1,021MB / 93%).
DEFAULT_EXCLUDE = ["Content/**"]

GITIGNORE = ".gitignore"


def resolve_bare_path(project_id: str, bare_path: str = "") -> str:
    """추적할 bare 저장소 경로를 확정한다. 존재하지 않으면 실패 — 추측하지 않는다."""
    if bare_path:
        p = Path(bare_path)
    else:
        if "/" not in project_id:
            raise ConfigError(
                f"project_id 는 '<owner>/<repo>' 형태여야 한다: {project_id!r}"
            )
        p = GITEA_REPO_ROOT / f"{project_id}.git"
    if not (p / "HEAD").is_file():
        raise ConfigError(
            f"bare 저장소가 아니다(또는 읽을 수 없다): {p}\n"
            "Gitea ROOT 는 /var/lib/gitea/gitea-repositories 이고 표준 배치의 "
            "'data/' 세그먼트가 없다. 읽기에는 sim 이 gitea 그룹에 있어야 한다."
        )
    return str(p)


def register_project(
    name: str,
    project_id: str,
    *,
    bare_path: str = "",
    clone_url: str = "",
    branch: str = "main",
    engine: str = "",
    registry: Registry | None = None,
) -> dict:
    """프로젝트를 새로 등록한다. 디지털 트윈 정보를 담을 디렉토리가 여기서 생긴다."""
    reg = registry or Registry.load()
    validate_name(name)

    if name in reg.names:
        raise ConfigError(f"이미 등록된 프로젝트다: {name}")
    target = reg.dir_of(name)
    if target.exists():
        raise ConfigError(f"디렉토리가 이미 있다: {target}")

    resolved_bare = resolve_bare_path(project_id, bare_path)

    # 1. 디렉토리
    target.mkdir(parents=True)
    created_dir = True
    try:
        # 2. config.yaml — 먼저 만든다
        cfg = ProjectConfig(
            name=name,
            project_id=project_id,
            bare_path=resolved_bare,
            clone_url=clone_url,
            branch=branch,
            engine=engine,
            include=list(DEFAULT_INCLUDE),
            exclude=list(DEFAULT_EXCLUDE),
        )
        write_project_config(target / PROJECT_CONFIG, cfg)
        (target / "context").mkdir(exist_ok=True)
        (target / "ontology" / "domains").mkdir(parents=True, exist_ok=True)
    except Exception:
        if created_dir:
            _rmtree_quiet(target)
        raise

    # 3. 루트 목록
    reg.names.append(name)
    if not reg.active:
        reg.active = name
    reg.save()

    # 4. .gitignore
    ignored = _ensure_gitignore(reg.root, name)

    # 5. 원본 잠금 (원격 없음 · 훅 없음)
    git_ok, git_note = _git_init_lock(target, name, project_id)

    return {
        "ok": True,
        "name": name,
        "dir": str(target),
        "config": str(target / PROJECT_CONFIG),
        "bare_path": resolved_bare,
        "active": reg.active,
        "gitignore_added": ignored,
        "git_locked": git_ok,
        "note": git_note,
        "next": "소스 클론과 최초 색인은 아직이다 — last_indexed_commit 이 비어 있다.",
    }


def set_active(name: str, *, registry: Registry | None = None) -> dict:
    """가리키는 프로젝트를 바꾼다. 디렉토리는 전부 남고 마운트 대상만 바뀐다."""
    reg = registry or Registry.load()
    validate_name(name)
    if name not in reg.names:
        raise ConfigError(
            f"등록되지 않은 프로젝트다: {name}. 등록된 것: {', '.join(reg.names) or '(없음)'}"
        )
    problems = _check_one(reg, name)
    if problems:
        raise ConfigError("전환할 수 없다 — " + " / ".join(problems))

    previous = reg.active
    reg.active = name
    reg.save()

    cfg = reg.config_of(name)
    return {
        "ok": True,
        "previous": previous,
        "active": name,
        "project_id": cfg.project_id,
        "branch": cfg.branch,
        "last_indexed_commit": cfg.last_indexed_commit,
        "note": (
            "가리키는 프로젝트가 다른 동안에는 이 프로젝트의 문서 갱신이 멈춰 있었다. "
            "재개하면 last_indexed_commit 부터 따라잡는다."
            if cfg.last_indexed_commit
            else "아직 한 번도 색인하지 않았다(last_indexed_commit 이 비어 있다)."
        ),
    }


def list_projects(*, registry: Registry | None = None) -> dict:
    reg = registry or Registry.load()
    items = []
    for name in reg.names:
        entry: dict = {"name": name, "active": name == reg.active}
        try:
            cfg = reg.config_of(name)
            entry.update(
                project_id=cfg.project_id,
                branch=cfg.branch,
                last_indexed_commit=cfg.last_indexed_commit,
                last_indexed_at=cfg.last_indexed_at,
            )
        except ConfigError as e:
            entry["error"] = str(e)
        items.append(entry)
    return {"active": reg.active, "projects": items, "problems": reg.check()}


# ─────────────────────────────────────────
# 내부
# ─────────────────────────────────────────

def _check_one(reg: Registry, name: str) -> list[str]:
    problems = []
    d = reg.dir_of(name)
    if not d.is_dir():
        problems.append(f"디렉토리가 없다: {d}")
    elif not (d / PROJECT_CONFIG).is_file():
        problems.append(f"{PROJECT_CONFIG} 가 없다")
    else:
        cfg = ProjectConfig.load(d / PROJECT_CONFIG)
        if cfg.name != name:
            problems.append(f"config.yaml 의 name 이 {cfg.name!r} 이다")
    return problems


def _ensure_gitignore(root: Path, name: str) -> bool:
    """`ax-cluster/.gitignore` 에 `/<Name>/` 한 줄을 넣는다. 이미 있으면 그대로 둔다."""
    path = root / GITIGNORE
    line = f"/{name}/"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if line in existing.splitlines():
        return False
    with path.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{line}\n")
    return True


def _git_init_lock(target: Path, name: str, project_id: str) -> tuple[bool, str]:
    """원본을 잠그는 로컬 저장소. **원격도 훅도 붙이지 않는다** (§5.5.3-d)."""
    try:
        (target / GITIGNORE).write_text(
            "# 파생 자산 — 재색인으로 복구된다 (PLAN §5.4.7)\n"
            "vector_db/\nbm25.db\nclass_graph.db\ndependency_graph.db\n\n"
            "# 소스 클론 — 원본은 Gitea 에 있다\nrepo/\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
        subprocess.run(["git", "add", "-A"], cwd=target, check=True)
        subprocess.run(
            [
                "git", "commit", "-q", "-m",
                f"등록: {name} ({project_id}) — 디지털 트윈 디렉토리 생성\n\n"
                f"생성 시각 {datetime.now().isoformat(timespec='seconds')}\n"
                "원격 없음 · 훅 없음 (PLAN §5.5.3-d 자기 유발 재귀 금지).",
            ],
            cwd=target,
            check=True,
        )
        return True, "원본 잠금 완료(로컬 git, 원격 없음·훅 없음)."
    except (OSError, subprocess.CalledProcessError) as e:
        return False, f"git 잠금 실패(등록 자체는 유효): {e}"


def _rmtree_quiet(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
