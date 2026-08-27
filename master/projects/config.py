"""프로젝트 레지스트리 — 루트 목록/`active` 와 프로젝트별 설정을 읽고 쓴다 (PLAN §5.5).

배치:

    <root>/projects.yaml            관리 중인 프로젝트 목록 + active   (gitignore)
    <root>/<Name>/config.yaml       추적 대상 git + 문서 갱신 워터마크 (gitignore)
    <root>/<Name>/context/          컨텍스트 문서
    <root>/<Name>/ontology/domains/ 온톨로지

[중요] 루트는 `AX_PROJECTS_ROOT` 로 **명시 주입**하며 폴백이 없다. `task_queue` 이식 때
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


def normalize_project_id(project_id: str) -> str:
    """`project_id` 의 **동일성 키**. 대소문자를 접는다 (§5.5.4-④).

    [중요] Gitea 는 이름을 두 벌로 들고 있다 — DB 실측 (2026-08-08):

        owner_name / name  = `Sim/ModularStage`   ← 표시용. **훅 페이로드가 싣는 값**
        lower_name         = `modularstage`       ← 디스크 경로 · 동일성 판정

    저장은 표시용 정규값으로 하고(사람과 로그가 읽는 이름), **비교는 여기를 통과시킨다.**
    Gitea 가 `lower_name` 컬럼을 따로 두는 이유가 그것이다 — 표시 이름은 라벨이고
    동일성은 소문자다. 이 구분을 지키지 않으면 Gitea 에서 대소문자만 바꾸는 rename
    한 번에 훅이 조용히 전부 거부된다([주의] 형태는 409 가 아니라 소비자의 **건너뛰기**다).
    """
    return (project_id or "").strip().casefold()


def project_id_disk_path(project_id: str) -> str:
    """`project_id` → 디스크상의 상대 경로. **소문자로 접는다.**

    `Sim/ModularStage` 를 그대로 경로에 쓰면
    `/var/lib/gitea/gitea-repositories/Sim/ModularStage.git` 가 되는데 **그런 디렉토리는
    없다** — Gitea 는 `lower_name` 으로 저장한다.
    """
    return normalize_project_id(project_id)


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


ROLE_WORKER = "worker"          # 큐에서 claim 해 처리한다
ROLE_REQUESTER = "requester"    # 요청만 한다 — 사람의 기계. [중요] 파견 대상이 아니다
ROLES = (ROLE_WORKER, ROLE_REQUESTER)

# [중요] **파견 여부는 `role` 과 다른 축이다** (`#317` 미결 ④ · `#321`, 사용자 결정 2026-08-27).
#    `role` 하나가 세 가지를 겸했다 — 파견 여부 · 배달 내용물(`bundle.PAYLOAD_BY_ROLE`) ·
#    토큰 스코프(`auth.WORKER_SCOPE`). 그래서 `.33` 을 파견 대상으로 만들려고 role 을 바꾸면
#    검수·머지에 필요한 `review`·`coordinator` 를 잃고 쓰기가 403 이 된다. 축을 갈랐다.
#
# [중요] **이 필드는 「좁히기 전용」이다** (사용자 보완 2026-08-27: *"플래그는 분리하고, 해당
#    값이 있더라도 롤을 체크해서 작업 요청하는 메인 작업 PC면 무시하면 되겠네"*).
#    **워커를 일시적으로 뺄 수는 있어도 요청자를 켤 수는 없다** — 사람이 편집 중인 트리에서
#    파이프라인이 브랜치를 다루는 것 자체가 위험이라는 판단이다.
#
# 값이 **문자열**인 이유: 나중에 「사람이 없을 때만」 같은 조건이 필요해지면 값만 늘리면 된다.
#    boolean 이면 그때 스키마를 또 바꾼다.
DISPATCH_UNSET = ""             # 미지정 — `role` 에서 유도한다 (기존 레지스트리 무변경 동작)
DISPATCH_ALWAYS = "always"      # 파견 대상 — [주의] role 이 worker 일 때만 유효하다
DISPATCH_NEVER = "never"        # 파견에서 뺀다 (점검 중·자원 부족 등)
DISPATCH_MODES = (DISPATCH_UNSET, DISPATCH_ALWAYS, DISPATCH_NEVER)


@dataclass
class Workshop:
    """작업장 한 대의 체크아웃 (§5.5.4).

    [중요] **마스터가 경로를 아는 것은 파일을 소유하는 것이 아니다** — §2.1 위반이 아니라
    라우팅 메타데이터다. 마스터는 이 디렉토리를 읽지도 쓰지도 않는다.

    `driven` 이 이 스키마의 핵심이다. `.2` 는 SSH 가 열려 있어 마스터가 밀어넣을 수 있고,
    `.33` 은 RDP 뿐이라 몰 수 없다 — 그 차이를 주석이 아니라 필드로 남긴다.

    [중요] **`role` 은 `driven` 과 다른 축이다** (사용자 확정 2026-08-09). `driven` 은 *닿을 수
    있나*, `role` 은 *무엇을 시켜도 되나* 다. `.33` 은 SSH 가 열려 **닿을 수는 있지만**
    사람의 메인 작업 PC라 **일감을 파견하면 안 된다** — 사람이 편집 중인 트리에서 에이전트가
    브랜치를 만들고 파일을 고치는 것이 더티 체크가 막으려던 바로 그 사고다.

        requester  일감을 **요청**하고 온톨로지를 등록한다. 큐에서 집지 않는다
        worker     큐에서 claim 해 처리하고 제출한다

    [중요] **`dispatch` 는 세 번째 축이다** (`#321`, 2026-08-27) — *지금 보내도 되나*.
    `role` 은 **자격**(무엇을 시켜도 되나), `dispatch` 는 **가용성**(지금 보낼까)이다. 점검
    중이거나 자원이 모자란 워커를 **잠시 빼는** 자리이고, [중요] **요청자를 켜는 자리가
    아니다** — `role != worker` 면 값이 있어도 무시한다.
    """

    host: str
    driven: str = DRIVEN_INTERACTIVE
    path: str = ""
    user: str = ""
    role: str = ROLE_WORKER
    note: str = ""
    dispatch: str = DISPATCH_UNSET

    @property
    def dispatch_resolved(self) -> bool:
        """지금 파견해도 되나 — **미지정이면 `role` 에서 유도**한다 (`#321`).

        [중요] 미지정이 `role` 유도인 덕분에 **기존 레지스트리가 한 글자도 안 바뀌고** 그대로
        돈다. 명시하면 그것이 이기지만, 이기는 방향은 **좁히는 쪽뿐**이다 — `drivable` 이
        `role == worker` 를 따로 본다.
        """
        if not self.dispatch:
            return self.role == ROLE_WORKER
        return self.dispatch == DISPATCH_ALWAYS

    @property
    def drivable(self) -> bool:
        """마스터가 원격으로 **일감을 파견**할 수 있는가.

        [중요] 닿을 수 있는 것과 시켜도 되는 것은 다르다 — `requester` 는 SSH 가 열려 있어도
        파견 대상이 아니다. 이 문장은 `#321` 이후에도 **그대로 유효하다**(사용자 보완
        2026-08-27): `dispatch` 는 좁히기 전용이라 요청자를 켜지 못한다.

            drivable = (driven == ssh) and (role == worker) and dispatch_resolved
        """
        return (self.driven == DRIVEN_SSH and self.role == ROLE_WORKER
                and self.dispatch_resolved)

    @property
    def reachable(self) -> bool:
        """마스터가 SSH 로 닿을 수 있는가 (번들 배달 등 읽기·설정 작업)."""
        return self.driven == DRIVEN_SSH

    def validate(self) -> None:
        if not self.host.strip():
            raise ConfigError("워크숍 host 가 비어 있다.")
        if self.role not in ROLES:
            raise ConfigError(f"role 은 {' | '.join(ROLES)} 중 하나여야 한다: {self.role!r}")
        if self.dispatch not in DISPATCH_MODES:
            raise ConfigError(
                f"dispatch 는 {' | '.join(repr(m) for m in DISPATCH_MODES)} 중 하나여야 한다: "
                f"{self.dispatch!r}"
            )
        # [주의] **모순을 조용히 넘기지 않는다** — 요청자에 `always` 를 적어 두면 「켰다」고
        #    믿게 된다. 무시하는 것이 설계지만, 무시한다는 사실은 **말해야** 한다.
        if self.dispatch == DISPATCH_ALWAYS and self.role != ROLE_WORKER:
            raise ConfigError(
                f"dispatch={DISPATCH_ALWAYS!r} 는 role={ROLE_WORKER!r} 에만 쓸 수 있다 "
                f"({self.host} 는 role={self.role!r}). 이 필드는 **좁히기 전용**이다 — "
                f"워커를 빼는 데 쓰고, 요청자를 켜는 데 쓰지 않는다 (`#321`)"
            )
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
            role=str(d.get("role") or ROLE_WORKER),
            note=str(d.get("note") or ""),
            dispatch=str(d.get("dispatch") or DISPATCH_UNSET),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"driven": self.driven, "role": self.role}
        # 빈 값을 쓰지 않는다 — interactive 워크숍에 빈 path 가 남으면 "미설정"과
        # "설정했는데 비었다"가 구분되지 않는다.
        for key, val in (("user", self.user), ("path", self.path), ("note", self.note),
                         ("dispatch", self.dispatch)):
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
    # [중요] **분석 커서** — 「어디까지 커밋을 걸었나」 (`#278`, 사용자 지시 2026-08-23).
    #    `last_indexed_commit` 과 **다른 값이다**: 저쪽은 *"이 커밋까지 트윈에 반영됐다"* 는
    #    완료 주장이라 미합성 그룹이 있으면 전진하지 못한다(`#274`). 이쪽은 커밋을 하나씩
    #    걸으며 **그 커밋의 문서가 끝날 때마다** 전진하는 재개 지점이다. 한 값에 둘을 담으면
    #    부분 완료가 「완료」로 보고되고, 그것이 `#274` 가 고친 바로 그 거짓 보고다.
    analyzed_commit: str = ""
    analyzed_at: str = ""
    # [중요] **이 프로젝트의 일감이 등재될 레드마인 프로젝트** (`#293`). 비어 있으면 **폴백하지
    #    않는다** — 조용히 남의 프로젝트로 떨어지면 그것이 오염이다(`#257` 이 태그에서 내린 것과
    #    같은 판단). [주의] **AX 인프라 이슈는 이 값과 무관하다** — 그것은 사용자 확정
    #    (2026-08-09)대로 `ModularStage` 에 둔다. 여기 값은 *게임 소스 일감*의 자리다.
    redmine_project: str = ""
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
            analyzed_commit=str(index.get("analyzed_commit") or ""),
            analyzed_at=str(index.get("analyzed_at") or ""),
            redmine_project=str((data.get("redmine") or {}).get("project") or ""),
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
                "analyzed_commit": self.analyzed_commit,
                "analyzed_at": self.analyzed_at,
                "include": self.include,
                "exclude": self.exclude,
            }
        )
        data["index"] = index
        data["engine"] = self.engine
        # [주의] `redmine:` 절은 값이 있을 때만 쓴다 — 빈 절을 만들면 "설정했는데 비었다" 와
        #    "아직 안 정했다" 가 구별되지 않는다.
        if self.redmine_project:
            data["redmine"] = {"project": self.redmine_project}
        # [중요] **`init:`(초기화 사양 오버레이, #266)을 `engine:` 뒤로 보낸다.** `dict(self.raw)`
        #    로 시작하므로 그대로 두면 `version:` 보다 **앞에** 찍힌다 — 사람이 읽는 파일이라
        #    순서가 내용이다. 모르는 키의 통과는 그대로 두고(그것이 raw 의 값이다) **우리가 쓰는
        #    키 하나만** 자리를 정한다.
        if "init" in data:
            data["init"] = data.pop("init")
        if self.workshops:
            data["workshops"] = {h: w.to_dict() for h, w in self.workshops.items()}
        else:
            data.pop("workshops", None)
        # [중요] default_flow_style=False 를 유지할 것. 윈도우 경로(`E:\trunk\...`)가
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

    def find_by_project_id(self, project_id: str) -> str:
        """훅 페이로드의 `project_id` 로 프로젝트명을 찾는다. **대소문자 무시** (§5.5.4-④).

        훅은 `Sim/ModularStage` 를 싣고 config 에도 그 값이 있지만, Gitea 에서 대소문자만
        바꾸는 rename 이 일어나면 두 값이 갈린다. 동일성은 casefold 로 판정한다.
        찾지 못하면 빈 문자열 — 호출자가 fail-closed 로 처리한다. [주의] 그 형태는 **409 가
        아니다**: 훅 경로의 호출자는 `events/consumer.py` 이고 **건너뛰고 사유를 남긴다**
        (HTTP 응답이 없는 경로다). 요청 표면의 거절 형태는 `200 + ok:false`(§12.5-c).
        """
        want = normalize_project_id(project_id)
        if not want:
            return ""
        for name in self.names:
            try:
                if normalize_project_id(self.config_of(name).project_id) == want:
                    return name
            except ConfigError:
                continue  # 깨진 항목은 check() 가 따로 보고한다
        return ""

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
