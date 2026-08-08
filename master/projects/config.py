"""프로젝트 레지스트리 — 루트 목록/`active` 와 프로젝트별 설정을 읽고 쓴다 (PLAN §5.5).

배치:

    <root>/projects.yaml            관리 중인 프로젝트 목록 + active   (gitignore)
    <root>/<Name>/config.yaml       추적 대상 git + 문서 갱신 워터마크 (gitignore)
    <root>/<Name>/context/          컨텍스트 문서
    <root>/<Name>/ontology/domains/ 온톨로지

🔴 루트는 `AX_PROJECTS_ROOT` 로 **명시 주입**하며 폴백이 없다. `task_queue` 이식 때
배운 대로다(§9.5.1) — 경로를 역산하면 잘못 잡아도 조용히 돌다가 재기동 후에야
"데이터가 사라졌다"로 발견된다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT_CONFIG = "projects.yaml"
PROJECT_CONFIG = "config.yaml"

# 디렉토리명으로 그대로 쓰이므로 경로 조작이 불가능한 형태만 허용한다.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# Gitea 저장소 ROOT — 표준 배치의 `data/` 세그먼트가 **없다** (실측 2026-08-08, §5.5.3).
GITEA_REPO_ROOT = Path(
    os.environ.get("AX_GITEA_REPO_ROOT", "/var/lib/gitea/gitea-repositories")
)


class ConfigError(RuntimeError):
    """설정이 없거나 어긋났다. 전부 fail-closed — 추측해서 진행하지 않는다."""


def projects_root() -> Path:
    raw = os.environ.get("AX_PROJECTS_ROOT", "").strip()
    if not raw:
        raise ConfigError(
            "AX_PROJECTS_ROOT 가 설정되지 않았다. 폴백은 없다 — "
            "systemd 유닛이나 셸에서 명시하라 (PLAN §5.5.3-④)."
        )
    root = Path(raw).expanduser()
    if not root.is_dir():
        raise ConfigError(f"AX_PROJECTS_ROOT 가 디렉토리가 아니다: {root}")
    return root


def validate_name(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise ConfigError(
            f"프로젝트명이 부적합하다: {name!r}. "
            "영숫자로 시작하고 [A-Za-z0-9_.-] 만 쓸 수 있다(디렉토리명이 되기 때문)."
        )
    return name


@dataclass
class ProjectConfig:
    """`<Name>/config.yaml` — 이 디렉토리가 무엇을 추적하고 어디까지 반영했는지."""

    name: str
    project_id: str = ""
    bare_path: str = ""
    clone_url: str = ""
    branch: str = "main"
    local_clone: str = "repo"
    engine: str = ""
    last_indexed_commit: str = ""
    last_indexed_at: str = ""
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        if not path.is_file():
            raise ConfigError(f"프로젝트 설정이 없다: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        track = data.get("track") or {}
        index = data.get("index") or {}
        return cls(
            name=str(data.get("name") or ""),
            project_id=str(track.get("project_id") or ""),
            bare_path=str(track.get("bare_path") or ""),
            clone_url=str(track.get("clone_url") or ""),
            branch=str(track.get("branch") or "main"),
            local_clone=str(track.get("local_clone") or "repo"),
            engine=str(data.get("engine") or ""),
            last_indexed_commit=str(index.get("last_indexed_commit") or ""),
            last_indexed_at=str(index.get("last_indexed_at") or ""),
            include=list(index.get("include") or []),
            exclude=list(index.get("exclude") or []),
            raw=data,
        )

    def to_yaml(self) -> str:
        data = dict(self.raw)
        data["version"] = data.get("version", 1)
        data["name"] = self.name
        data["track"] = {
            "project_id": self.project_id,
            "bare_path": self.bare_path,
            "clone_url": self.clone_url,
            "branch": self.branch,
            "local_clone": self.local_clone,
        }
        index = dict(data.get("index") or {})
        index.update(
            {
                "last_indexed_commit": self.last_indexed_commit,
                "last_indexed_at": self.last_indexed_at,
                "include": self.include,
                "exclude": self.exclude,
            }
        )
        data["index"] = index
        data["engine"] = self.engine
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


@dataclass
class Registry:
    """`projects.yaml` — 관리 중인 목록과 지금 가리키는 프로젝트."""

    root: Path
    active: str = ""
    names: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.root / ROOT_CONFIG

    @classmethod
    def load(cls, root: Path | None = None) -> "Registry":
        root = root or projects_root()
        path = root / ROOT_CONFIG
        if not path.is_file():
            raise ConfigError(f"루트 설정이 없다: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            root=root,
            active=str(data.get("active") or ""),
            names=[str(n) for n in (data.get("projects") or [])],
            raw=data,
        )

    def save(self) -> None:
        data = dict(self.raw)
        data["version"] = data.get("version", 1)
        data["active"] = self.active
        data["projects"] = list(self.names)
        self.raw = data
        _atomic_write(self.path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    def dir_of(self, name: str) -> Path:
        return self.root / validate_name(name)

    def config_of(self, name: str) -> ProjectConfig:
        return ProjectConfig.load(self.dir_of(name) / PROJECT_CONFIG)

    def check(self) -> list[str]:
        """3자 일치 검사 — 목록 ↔ 디렉토리 ↔ 각 config.yaml 의 name (§5.5.3-①).

        어긋난 항목을 문자열 목록으로 돌려준다. 빈 목록이면 정상.
        """
        problems: list[str] = []
        for name in self.names:
            d = self.dir_of(name)
            if not d.is_dir():
                problems.append(f"목록에 있으나 디렉토리가 없다: {name}")
                continue
            cfg_path = d / PROJECT_CONFIG
            if not cfg_path.is_file():
                problems.append(f"{name}: {PROJECT_CONFIG} 가 없다")
                continue
            cfg = ProjectConfig.load(cfg_path)
            if cfg.name != name:
                problems.append(f"{name}: config.yaml 의 name 이 {cfg.name!r} 이다")
        if self.active and self.active not in self.names:
            problems.append(f"active({self.active}) 가 목록에 없다")
        if not self.active:
            problems.append("active 가 비어 있다")
        return problems


def _atomic_write(path: Path, text: str) -> None:
    """같은 디렉토리에 임시 파일을 쓰고 rename — 중간에 죽어도 반쯤 쓴 설정이 남지 않는다."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_project_config(path: Path, cfg: ProjectConfig) -> None:
    _atomic_write(path, cfg.to_yaml())
