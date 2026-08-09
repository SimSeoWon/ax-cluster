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


# ── 제거 (소 1.3.2 의 나머지 절반) ────────────────────────────────────────────

@dataclass
class RemoveResult:
    domain: str
    kind: str
    name: str
    removed: bool = False
    was_locked: bool = False
    path: str = ""
    manifest_updated: bool = False
    reason: str = ""

    @property
    def summary(self) -> str:
        if self.removed:
            s = f"🗑️ {self.domain}/{self.kind}/{self.name} 제거"
            if self.was_locked:
                s += " (🔴 잠긴 것을 force 로 지웠다)"
            return s + ("" if self.manifest_updated else " · ⚠️ manifest 갱신 실패")
        return f"보존 {self.domain}/{self.kind}/{self.name} — {self.reason}"


def remove(paths: ProjectPaths, domain: str, kind: str, name: str,
           *, force: bool = False) -> RemoveResult:
    """항목 하나를 지운다. 🔴 **잠긴 것은 `force` 없이는 안 지운다.**

    잠금은 *"사람이 검수했다"* 는 뜻이다. 에이전트의 호출 한 번으로 사라지면 검수가
    의미를 잃는다 — 재합성이 못 덮는 것을 삭제가 덮어서는 안 된다. 지우려면 사람이
    **한 번 더** 말해야 한다(`force=True`).

    🔴 **manifest 목록에서도 뺀다.** 파일만 지우면 manifest 가 없는 파일을 가리키고,
    색인 페이로드가 그 항목을 읽으려다 조용히 건너뛴다(에러가 아니라 결손이 된다).
    """
    p, item = _load(paths, domain, kind, name)
    real = str(item.get("name") or name)
    res = RemoveResult(domain=domain, kind=kind, name=real, path=str(p),
                       was_locked=item.get(LOCK_FIELD) is True)
    if res.was_locked and not force:
        res.reason = ("🔒 검수 잠금이 걸려 있다 — 사람이 손본 것이다. 정말 지우려면 "
                      "force 를 명시하라 (잠금을 먼저 풀어도 된다)")
        return res

    from .package import MANIFEST, _manifest_key
    root = paths.ontology / "domains" / domain
    try:
        rel = str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = ""
    p.unlink()
    res.removed = True

    man = yaml_io.read(root / MANIFEST)
    if isinstance(man, dict):
        key = _manifest_key(kind)
        before = list(man.get(key) or [])
        man[key] = [r for r in before if str(r).replace("\\", "/") != rel]
        yaml_io.write(root / MANIFEST, man)
        res.manifest_updated = len(man[key]) != len(before) or rel == ""
    return res


# ── 보호 표식 (일괄) ─────────────────────────────────────────────────────────
#
# 🔴 **`verified_by_user` 와 다른 것이다.** 섞으면 둘 다 못 쓰게 된다:
#
#     verified_by_user   "사람이 이 항목을 **검수했다**"          — 한 건씩, 사람이 판단
#     protected          "이 내용을 **재생성으로 대체하지 않는다**" — 출처가 근거, 일괄 가능
#
# 받아온 247 yaml 스냅샷은 사람이 항목마다 검수한 것이 **아니다.** 그런데 실측(리포트 11 §20)
# 으로 **우리 합성이 그보다 얕다**는 것이 드러났다 — `TaskListCDOAsSourceOfTruth`(설계 결정)가
# `AbstractBaseContract`(프레임워크 기계적 사실)로 바뀌었다. 둘 다 사실이라 사실 게이트는
# 통과한다. 게이트는 *거짓*을 막지 *얕음*을 막지 못한다.
#
# 그러므로 필요한 것은 "검수했다" 가 아니라 **"이건 우리가 못 만든다"** 는 표식이다.
# 247건에 `verified_by_user` 를 찍으면 그 신호가 오염되고, 나중에 *사람이 실제로 검수한 것*을
# 구분할 수 없게 된다.

PROTECT_FIELD = "protected"
PROTECT_WHY = "protected_reason"
# 🔴 **언제 기준으로 보호했나.** 없으면 drift 감사(중 2.4.1)가 *"이 항목은 커밋 X 기준인데
# 지금은 Y 다"* 를 말할 수 없다 — 설계 규칙을 서술한 invariant 는 호출 표기가 없어 사실
# 게이트가 통과시키므로, **언제 것인지**가 유일한 단서가 된다.
PROTECT_AT = "protected_at"


@dataclass
class BulkResult:
    changed: list = field(default_factory=list)     # [(도메인, kind, 이름)]
    already: int = 0
    scanned: int = 0
    applied: bool = False
    reason: str = ""
    at: str = ""                                   # 보호 시점의 트윈 커밋

    @property
    def summary(self) -> str:
        head = "적용" if self.applied else "계획"
        s = (f"{head}: 검사 {self.scanned} · 표시 {len(self.changed)} · 이미 {self.already}")
        if self.at:
            s += f" · 기준 {self.at[:8]}"
        elif self.applied and self.changed:
            s += " · ⚠️ 기준 커밋 미상"
        return s + (f" · 사유 «{self.reason}»" if self.reason else "")


def _items(paths: ProjectPaths, domain: str = "", kinds=()):
    """(경로, 항목, 도메인, kind) 를 훑는다. **읽기만 한다.**"""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return
    want = set(kinds) or set(SUBDIRS)
    dirs = [root / domain] if domain else sorted(d for d in root.iterdir() if d.is_dir())
    for d in dirs:
        if not d.is_dir():
            continue
        for layer in LAYER_DIRS:
            for kind in sorted(want):
                sub = d / layer / kind
                if not sub.is_dir():
                    continue
                for f in sorted(sub.glob("*.yaml")):
                    item = yaml_io.read(f)
                    if isinstance(item, dict):
                        yield f, item, d.name, kind


def protect_all(paths: ProjectPaths, *, domain: str = "", kinds=(), reason: str = "",
                on: bool = True, apply: bool = False) -> BulkResult:
    """항목들에 보호 표식을 일괄로 건다/푼다. 🔴 **기본은 계획만**(`apply=False`).

    247건을 손으로 부를 수는 없다. 다만 일괄이라서 더 위험하므로 **먼저 무엇이 바뀌는지
    보여주고**, 실행은 명시할 때만 한다 — `sync`·`cleanup` 과 같은 규칙이다.

    🔴 `reason` 을 요구한다. *왜* 보호하는지 없으면 다음 사람이 풀어도 되는지 판단할 수 없다.
    """
    if on and not (reason or "").strip():
        raise EditError("보호 사유가 비었다 — 왜 재생성으로 대체하면 안 되는지 적어라 "
                        "(예: '받아온 스냅샷. 우리 합성이 더 얕다 — 리포트 11 §20')")
    at = ""
    if on:
        try:
            from ..work import twin_base
            at = twin_base.twin_commit(paths)
        except Exception:                                 # noqa: BLE001
            at = ""                                       # 모르면 안 적는다 (지어내지 않는다)
    res = BulkResult(applied=apply, reason=reason.strip(), at=at)
    for f, item, dom, kind in _items(paths, domain, kinds):
        res.scanned += 1
        if bool(item.get(PROTECT_FIELD)) == bool(on):
            res.already += 1
            continue
        res.changed.append((dom, kind, str(item.get("name") or f.stem)))
        if apply:
            if on:
                item[PROTECT_FIELD] = True
                if reason:
                    item[PROTECT_WHY] = reason.strip()
                if at:
                    item[PROTECT_AT] = at
            else:
                item.pop(PROTECT_FIELD, None)
                item.pop(PROTECT_WHY, None)
                item.pop(PROTECT_AT, None)
            yaml_io.write(f, item)
    return res


def protected_items(paths: ProjectPaths, domain: str = "") -> list:
    """보호 표식이 걸린 것들. **검수 잠금과 따로 센다** — 뜻이 다르다."""
    return [{"domain": dom, "kind": kind, "name": str(item.get("name") or f.stem),
             "reason": str(item.get(PROTECT_WHY) or ""),
             "at": str(item.get(PROTECT_AT) or ""), "path": str(f)}
            for f, item, dom, kind in _items(paths, domain)
            if item.get(PROTECT_FIELD) is True]
