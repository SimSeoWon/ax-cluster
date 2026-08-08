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


# 워크숍 구동 방식 (§5.5.4-②). 머신마다 다른 것이 우연이 아니라 기록할 사실이다.
DRIVEN_SSH = "ssh"                  # 마스터가 SSH 로 밀어넣는다
DRIVEN_INTERACTIVE = "interactive"  # 사람이 앉아서 작업한다 — 마스터가 몰지 않는다
DRIVEN_MODES = (DRIVEN_SSH, DRIVEN_INTERACTIVE)


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
class Workshop:
    """작업장 한 대의 체크아웃 (§5.5.4).

    🔴 **마스터가 경로를 아는 것은 파일을 소유하는 것이 아니다** — §2.1 위반이 아니라
    라우팅 메타데이터다. 마스터는 이 디렉토리를 읽지도 쓰지도 않는다.

    `driven` 이 이 스키마의 핵심이다. `.2` 는 SSH 가 열려 있어 마스터가 밀어넣을 수 있고,
    `.33` 은 RDP 뿐이라 몰 수 없다 — 그 차이를 주석이 아니라 필드로 남긴다.
    """

    host: str
    driven: str = DRIVEN_INTERACTIVE
    path: str = ""
    user: str = ""
    note: str = ""

    @property
    def drivable(self) -> bool:
        """마스터가 원격으로 작업을 밀어넣을 수 있는가."""
        return self.driven == DRIVEN_SSH

    def validate(self) -> None:
        if not self.host.strip():
            raise ConfigError("워크숍 host 가 비어 있다.")
        if self.driven not in DRIVEN_MODES:
            raise ConfigError(
                f"driven 은 {' | '.join(DRIVEN_MODES)} 중 하나여야 한다: {self.driven!r}"
            )
        if self.driven == DRIVEN_SSH:
            # 밀어넣겠다고 선언했는데 어디로·누구로 넣을지가 없으면 선언이 거짓이 된다.
            missing = [k for k, v in (("path", self.path), ("user", self.user)) if not v]
            if missing:
                raise ConfigError(
                    f"driven={DRIVEN_SSH} 인 워크숍({self.host})에는 "
                    f"{'·'.join(missing)} 가 필요하다. 마스터가 밀어넣을 대상을 특정할 수 없다."
                )

    @classmethod
    def from_dict(cls, host: str, data: Any) -> "Workshop":
        d = data or {}
        if not isinstance(d, dict):
            raise ConfigError(f"워크숍 {host} 항목이 매핑이 아니다: {type(d).__name__}")
        return cls(
            host=str(host),
            driven=str(d.get("driven") or DRIVEN_INTERACTIVE),
            path=str(d.get("path") or ""),
            user=str(d.get("user") or ""),
            note=str(d.get("note") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"driven": self.driven}
        # 빈 값을 쓰지 않는다 — interactive 워크숍에 빈 path 가 남으면 "미설정"과
        # "설정했는데 비었다"가 구분되지 않는다.
        for key, val in (("user", self.user), ("path", self.path), ("note", self.note)):
            if val:
                out[key] = val
        return out


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
    workshops: dict[str, Workshop] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        if not path.is_file():
            raise ConfigError(f"프로젝트 설정이 없다: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        track = data.get("track") or {}
        index = data.get("index") or {}
        shops = data.get("workshops") or {}
        if not isinstance(shops, dict):
            raise ConfigError(f"workshops 는 매핑이어야 한다: {type(shops).__name__}")
        return cls(
            workshops={h: Workshop.from_dict(h, v) for h, v in shops.items()},
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
        if self.workshops:
            data["workshops"] = {h: w.to_dict() for h, w in self.workshops.items()}
        else:
            data.pop("workshops", None)
        # 🔴 default_flow_style=False 를 유지할 것. 윈도우 경로(`E:\trunk\...`)가
        #    플로우 스타일에서 따옴표에 갇히면 `\t` 가 탭으로 해석될 위험이 있다.
        #    round-trip 은 test_projects.py 가 검사한다.
        return yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False, default_flow_style=False
        )


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
