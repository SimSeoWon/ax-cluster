"""온톨로지 항목 대화형 편집 + 검수 잠금 (소 1.3.2 · 1.3.7).

원본: `mcp/context_search/ontology_manage_items.py` 의 `edit_ontology_item_impl`.

## 🔴 편집이 곧 잠금이다

사람이 손댄 항목을 재합성이 덮으면 **검수가 의미를 잃고, 사용자는 다시는 검수하지 않는다.**
그래서 편집은 언제나 `verified_by_user: true` 를 함께 건다 — 원본과 같다.

`package.merge_preserve_locked` 가 그 표식을 보고 지킨다. 🔴 **지금까지 그 보존 로직은
死코드였다** — 표식을 *거는 경로가 아예 없었기 때문이다(실측 2026-08-09). 이 모듈이 그 절반을
채운다.

## 🔴 `name` 과 `layer` 는 패치로 바꾸지 않는다

파일명이 `name` 에서 나오고 경로가 `layer` 에서 나온다. 패치로 바꾸면 **파일과 내용이
어긋나거나 같은 항목이 두 경로에 생긴다.** 원본이 같은 이유로 막았다. 계층을 옮기는 것은
합성기(`layers`)의 일이고, 이름을 바꾸는 것은 지우고 새로 만드는 것이다.

## ⚠️ 원본과 갈라지는 곳 — 별칭은 잠그지 않는다

원본은 `add_object_alias_impl` 이 이 함수를 타서 **별칭만 추가해도 항목이 잠겼다.** 우리는
그러지 않는다(`thesaurus.register` 는 파일을 직접 쓰고, `package.carry_human_fields` 가 필드
단위로 이월한다). 이유: 별칭은 *기계 소유 항목에 붙은 사람의 데이터*지 "이 항목 내용을
검수했다" 가 아니다. 잠가 버리면 그 항목의 **나머지 내용이 영원히 개선되지 못한다.**

## 🔴 잠금은 풀 수 있어야 한다

잘못 건 잠금이 영구가 되면 그 항목은 영영 낡는다. `set_lock(..., locked=False)` 를 둔다 —
다만 **되돌리면 다음 재합성이 덮는다**는 사실을 반환값에 실어 보낸다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from . import yaml_io
from .package import LAYER_DIRS, SUBDIRS, _safe

LOCK_FIELD = "verified_by_user"
# 🔴 패치로 바꿀 수 없는 것 — 파일 경로가 이 둘에서 나온다.
IMMUTABLE = ("name", "layer")


class EditError(RuntimeError):
    """편집할 수 없다. 🔴 **조용히 새 파일을 만들지 않는다.**"""


@dataclass
class EditResult:
    domain: str
    kind: str
    name: str
    path: str = ""
    changed: list = field(default_factory=list)     # 실제로 값이 바뀐 키
    ignored: list = field(default_factory=list)     # 🔴 불변이라 무시한 키
    locked: bool = False
    was_locked: bool = False
    note: str = ""

    @property
    def summary(self) -> str:
        s = f"{self.domain}/{self.kind}/{self.name}"
        s += f" · 변경 {len(self.changed)}" if self.changed else " · 변경 없음"
        if self.ignored:
            s += f" · 🔴 무시 {self.ignored} (불변)"
        s += " · 🔒 잠금" if self.locked else " · 잠금 해제"
        return s + (f" — {self.note}" if self.note else "")


def find_item(paths: ProjectPaths, domain: str, kind: str, name: str):
    """항목 파일. 🔴 **전 계층을 훑는다** — 계층은 합성기가 옮길 수 있다."""
    if kind not in SUBDIRS:
        raise EditError(f"kind 는 {SUBDIRS} 중 하나여야 한다: {kind!r}")
    root = paths.ontology / "domains" / domain
    fn = f"{_safe(name)}.yaml"
    for layer in LAYER_DIRS:
        p = root / layer / kind / fn
        if p.is_file():
            return p
    return None


def _load(paths: ProjectPaths, domain: str, kind: str, name: str):
    p = find_item(paths, domain, kind, name)
    if p is None:
        raise EditError(
            f"{domain}/{kind}/{name} 를 찾지 못했다. 🔴 **새로 만들지 않는다** — 이름을 잘못 준 "
            f"편집이 조용히 새 항목을 만들면 원본과 사본이 갈린다")
    item = yaml_io.read(p)
    if not isinstance(item, dict):
        raise EditError(f"{p} 를 읽지 못했다 (매핑이 아니다)")
    return p, item


def edit(paths: ProjectPaths, domain: str, kind: str, name: str, patch: dict,
         *, lock: bool = True) -> EditResult:
    """항목 하나를 **얕게 병합**하고 잠근다.

    🔴 중첩 값은 **키 전체를 다시 넘겨야** 한다 — 부분 병합을 지원하면 무엇이 남고 무엇이
    사라졌는지 호출자가 알 수 없게 된다(원본도 같은 선택을 했다: *"단순함 우선, 과설계 금지"*).
    """
    p, item = _load(paths, domain, kind, name)
    res = EditResult(domain=domain, kind=kind, name=str(item.get("name") or name),
                     path=str(p), was_locked=item.get(LOCK_FIELD) is True)

    merged = dict(item)
    for k, v in (patch or {}).items():
        if k in IMMUTABLE:
            res.ignored.append(k)           # 🔴 조용히 적용하지 않는다 — 보고한다
            continue
        if k == LOCK_FIELD:
            res.ignored.append(k)           # 잠금은 `lock` 인자로만 — 두 경로를 두지 않는다
            continue
        if merged.get(k) != v:
            res.changed.append(k)
        merged[k] = v

    merged[LOCK_FIELD] = bool(lock)
    res.locked = bool(lock)
    if not lock and res.was_locked:
        res.note = "🔴 잠금을 풀었다 — 다음 재합성이 이 항목을 덮을 수 있다"

    yaml_io.write(p, merged)
    return res


def set_lock(paths: ProjectPaths, domain: str, kind: str, name: str,
             locked: bool = True) -> EditResult:
    """내용을 건드리지 않고 잠금만 바꾼다."""
    return edit(paths, domain, kind, name, {}, lock=locked)


def locked_items(paths: ProjectPaths, domain: str = "") -> list:
    """지금 잠겨 있는 것들. **가시성이 없으면 사람이 무엇을 잠갔는지 잊는다.**"""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return []
    out = []
    domains = [root / domain] if domain else sorted(d for d in root.iterdir() if d.is_dir())
    for d in domains:
        if not d.is_dir():
            continue
        for layer in LAYER_DIRS:
            for kind in SUBDIRS:
                sub = d / layer / kind
                if not sub.is_dir():
                    continue
                for f in sorted(sub.glob("*.yaml")):
                    item = yaml_io.read(f)
                    if isinstance(item, dict) and item.get(LOCK_FIELD) is True:
                        out.append({"domain": d.name, "kind": kind, "layer": layer,
                                    "name": str(item.get("name") or f.stem),
                                    "path": str(f)})
    return out
