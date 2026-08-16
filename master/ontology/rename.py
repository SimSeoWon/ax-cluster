"""개명 cascade — 원전 `ontology_manage_rename.py` 이식 (소 3.6.1 · `#167`).

[중요] **왜 cascade 인가**: 도메인·클래스 이름이 **디렉토리·파일명·YAML 값·다른 도메인의 참조**에
그대로 박힌다. 한 곳만 고치면 나머지가 옛 이름을 가리키고, 그 상태는 조용하다 —
뷰어 링크가 죽고 검색이 빗나가는데 아무도 오류를 보지 않는다.

## [중요] 원전과 다르게 둔 것 하나 — **DB 를 건드리지 않는다**

원전 `_rename_db` 는 `class_graph.db` 의 `domains`/`class_ontology` 행을 옮긴다. 우리는 **안
옮긴다.** 근거는 이 저장소가 이미 내려 둔 결정이다(마일스톤 4 함정 목록):

    우리 SSOT 는 **YAML 하나**다. `class_ontology`·`domains` 표는 스키마만 있고 **행이 0**,
    쓰는 코드도 0건 — 그 구조가 **DB↔YAML 이중 소스 드리프트를 원천 제거**했다.
    [중요] 원전의 DB 쓰기 경로를 옮기면 **그 드리프트를 되살린다.**

[주의] 이것은 「안 옮기는 판단」이고, 재범위 규약대로 **닫지 않는다** — DB 를 SSOT 로 쓰기 시작하면
그때 되살린다.

## [중요] 되돌릴 수 없다 — 그래서 기본이 계획이다

트윈은 git 밖이라 **백업이 유일한 되돌리기**다(리포트 17). `apply=False` 가 기본이고, 계획은
무엇이 어디로 가는지 전부 적는다. 사람이 보고 나서 실행한다.

## [주의] 잠금은 이름을 따라간다

`verified_by_user`·`protected` 는 항목 안에 있으므로 파일이 통째로 움직이면 같이 간다.
[중요] **다시 만들지 않는다** — 개명은 이동이지 재생성이 아니다(재생성하면 잠금이 날아간다).

## 색인은 여기서 안 만진다

원전은 개명 끝에 도메인 인덱스를 재빌드한다. [중요] 우리 색인기는 **별도 프로세스**(`ax-indexer`)라
웹도 이 모듈도 재색인을 트리거하지 않는다(webui 가 같은 이유로 명령만 안내한다). 대신 개명이
지문을 바꾸므로 다음 동기에서 잡힌다 — 계획에 그 사실을 적는다.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import yaml_io

_SAFE = re.compile(r"[\\/:*?\"<>|\s]+")


def safe_name(name: str) -> str:
    return _SAFE.sub("_", (name or "").strip()).strip("_")


@dataclass
class RenamePlan:
    old: str = ""
    new: str = ""
    kind: str = "domain"                      # domain | class
    moves: list = field(default_factory=list)   # (from, to)
    edits: list = field(default_factory=list)   # (path, 무엇을)
    notes: list = field(default_factory=list)
    error: str = ""
    applied: bool = False

    @property
    def ok(self) -> bool:
        return not self.error

    def summary(self) -> str:
        if self.error:
            return f"[중요] {self.error}"
        return (f"{self.kind} 개명 {self.old} → {self.new} — "
                f"이동 {len(self.moves)}건 · 수정 {len(self.edits)}건"
                + (" (적용됨)" if self.applied else " (계획만)"))


def _domain_pkg(paths, name: str) -> Path:
    return Path(paths.ontology) / "domains" / name


def _domain_md(paths, name: str) -> Path:
    return Path(paths.context) / "_domains" / f"{name}.md"


def plan_domain(paths, old: str, new: str) -> RenamePlan:
    """도메인 개명 계획. [중요] **아무것도 쓰지 않는다.**"""
    p = RenamePlan(old=old, new=safe_name(new), kind="domain")
    if not p.new:
        p.error = "새 이름이 비었다"
        return p
    if not p.new.isascii():
        # 디렉토리·URL·도구 인자에 박히므로 여기서 막는다 (원전 규칙 그대로)
        p.error = "새 이름에 비ASCII — 영문·무공백이 필요하다"
        return p
    if p.new == old:
        p.error = "old == new"
        return p

    old_pkg, new_pkg = _domain_pkg(paths, old), _domain_pkg(paths, p.new)
    if not old_pkg.is_dir():
        p.error = f"그 도메인이 없다: {old_pkg}"
        return p
    if new_pkg.exists():
        p.error = f"새 이름이 이미 있다 — 충돌: {new_pkg}"
        return p
    p.moves.append((str(old_pkg), str(new_pkg)))

    man = old_pkg / "domain.yaml"
    if man.is_file():
        p.edits.append((str(man), "manifest 의 `domain:` 값"))

    old_md, new_md = _domain_md(paths, old), _domain_md(paths, p.new)
    if old_md.is_file():
        if new_md.exists():
            p.error = f"새 이름의 사람 편집 MD 가 이미 있다 — 충돌: {new_md}"
            return p
        p.moves.append((str(old_md), str(new_md)))

    # [중요] 다른 도메인의 참조 — 여기가 cascade 의 핵심이다. 안 고치면 링크가 조용히 죽는다.
    for other in sorted((Path(paths.ontology) / "domains").glob("*/domain.yaml")):
        if other.parent.name in (old, p.new):
            continue
        try:
            if old in other.read_text(encoding="utf-8"):
                p.edits.append((str(other), f"`{old}` 참조"))
        except OSError:
            continue
    for md in sorted((Path(paths.context) / "_domains").glob("*.md")):
        if md.stem in (old, p.new) or md.name.startswith("_"):
            continue
        try:
            if re.search(rf"(?m)^(parent_domain:\s*|\s*-\s*){re.escape(old)}\s*$",
                         md.read_text(encoding="utf-8")):
                p.edits.append((str(md), "parent_domain / 협력 도메인 항목"))
        except OSError:
            continue

    p.notes.append("[중요] class_graph DB 는 건드리지 않는다 — 우리 SSOT 는 YAML 이고 그 표는 0행이다 "
                   "(옮기면 DB↔YAML 드리프트가 되살아난다)")
    p.notes.append("색인은 여기서 안 만진다 — 지문이 바뀌므로 다음 동기가 잡는다 (`ax-indexer`)")
    p.notes.append("[주의] 트윈은 git 밖이다 — 적용 전에 백업할 것")
    return p


def _rewrite_refs(path: Path, old: str, new: str) -> bool:
    """참조 문자열 치환. [중요] **경계를 준다** — 부분 일치는 다른 이름을 삼킨다.

    실측된 사고가 근거다(`#167` 노트 정정): `%EditorView_MissionTask%` 같은 부분 일치가
    **현존하는 정상 클래스** `…MissionTaskDetailBase` 를 「옛이름」으로 잡아 stale 을
    4건이나 잘못 보고했다. 정확한 패턴으로 다시 재니 stale 은 **0건**이었다.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    fixed = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", new, text)
    if fixed == text:
        return False
    try:
        path.write_text(fixed, encoding="utf-8")
        return True
    except OSError:
        return False


def apply_domain(paths, plan: RenamePlan) -> RenamePlan:
    """계획을 실행한다. [중요] **계획이 성립하지 않으면 아무것도 하지 않는다.**"""
    if not plan.ok:
        return plan
    old, new = plan.old, plan.new
    # ① 참조 먼저 — 디렉토리를 옮긴 뒤에 하면 계획의 경로가 어긋난다
    for path_s, _what in plan.edits:
        pth = Path(path_s)
        if pth.name == "domain.yaml" and pth.parent.name == old:
            data = yaml_io.read(pth)
            if data is not None and data.get("domain") == old:
                data["domain"] = new
                pth.write_text(yaml_io.dump(data), encoding="utf-8")
            continue
        _rewrite_refs(pth, old, new)
    # ② 이동 — 파일이 통째로 가므로 잠금(verified_by_user·protected)이 따라간다
    for src, dst in plan.moves:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)
    plan.applied = True
    return plan


def plan_class(paths, domain: str, old: str, new: str) -> RenamePlan:
    """클래스 개명 계획 — 이름이 **파일명과 멤버 목록** 양쪽에 박힌다."""
    p = RenamePlan(old=old, new=safe_name(new), kind="class")
    if not p.new or not p.new.isascii():
        p.error = "새 이름이 비었거나 비ASCII 다"
        return p
    if p.new == old:
        p.error = "old == new"
        return p
    pkg = _domain_pkg(paths, domain)
    if not pkg.is_dir():
        p.error = f"그 도메인이 없다: {pkg}"
        return p
    for y in sorted(pkg.glob("L*/**/*.yaml")):
        try:
            text = y.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", text):
            p.edits.append((str(y), f"`{old}` 언급"))
        if y.stem == old:
            p.moves.append((str(y), str(y.with_name(f"{p.new}{y.suffix}"))))
    man = pkg / "domain.yaml"
    if man.is_file():
        try:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])",
                         man.read_text(encoding="utf-8")):
                p.edits.append((str(man), "manifest 의 멤버 목록"))
        except OSError:
            pass
    if not p.edits and not p.moves:
        p.error = f"`{old}` 을(를) `{domain}` 에서 찾지 못했다 — 이름을 확인할 것"
    p.notes.append("[중요] 경계를 준 치환이다 — 부분 일치는 다른 이름을 삼킨다 (실측된 오보고)")
    p.notes.append("[주의] 트윈은 git 밖이다 — 적용 전에 백업할 것")
    return p


def apply_class(paths, plan: RenamePlan) -> RenamePlan:
    if not plan.ok:
        return plan
    for path_s, _ in plan.edits:
        _rewrite_refs(Path(path_s), plan.old, plan.new)
    for src, dst in plan.moves:
        shutil.move(src, dst)
    plan.applied = True
    return plan
