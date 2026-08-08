"""도메인 패키지 쓰기 — manifest + objects/actions/invariants (소 1.3.3 의 LLM 0 부분).

원본: `watcher/ontology_synthesizer.write_domain_yaml` + `load_locked_items` /
`merge_preserve_locked`.

## 구조 (원본 3차 보정판)

    domains/<도메인>/
      domain.yaml              ← manifest. 🔴 **DB 색인 대상은 이것뿐**
      L{1,2,3}/objects/<Class>.yaml
      L{1,2,3}/actions/<Action>.yaml
      L{1,2,3}/invariants/<Name>.yaml

레이어 디렉토리로 나누는 이유는 원본이 그렇게 했기 때문만이 아니다 — **한 파일에 다 넣으면
재합성이 사용자 검수분까지 통째로 덮는다.** 항목 하나가 파일 하나면 잠긴 것만 남길 수 있다.

## 🔴 검수 잠금은 덮지 않는다 — 이것이 이 모듈의 존재 이유다

`verified_by_user: true` 인 항목은 **사람이 손본 것**이다. 재합성이 그것을 덮으면 검수가
의미를 잃고, 사용자는 다시는 검수하지 않는다.

원본 규칙 그대로: **새 항목 중 잠긴 이름과 겹치는 것을 버리고, 잠긴 것을 그대로 얹는다**
(`merge_preserve_locked`). 새 내용이 더 좋아 보여도 **덮지 않는다** — 좋고 나쁨을 판단하는
것은 우리가 아니다.

같은 함정을 시소러스에서도 봤다 — 원본이 `aliases` 를 얕은 덮어쓰기로 날린 사고를 기록해
뒀다(Phase η.11). **병합은 우연이 아니라 규칙이다.**
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from . import yaml_io

LAYER_DIRS = ("L1", "L2", "L3")
SUBDIRS = ("objects", "actions", "invariants")
MANIFEST = "domain.yaml"


@dataclass
class WriteStats:
    domain: str
    written: int = 0
    unchanged: int = 0          # 내용이 같아 안 쓴 것 (mtime 보존)
    locked_kept: int = 0        # 🔴 검수 잠금이라 지킨 것
    removed: int = 0            # 더 이상 없는 항목
    notes: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = f"{self.domain}: 작성 {self.written} · 그대로 {self.unchanged}"
        if self.locked_kept:
            s += f" · 🔒 잠금 보존 {self.locked_kept}"
        if self.removed:
            s += f" · 제거 {self.removed}"
        return s


def _layer_of(item: dict) -> str:
    """항목의 레이어 디렉토리. 없으면 L3 — **가장 가변으로 보수적으로** 둔다(원본과 같다)."""
    n = (item or {}).get("layer")
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "L3"
    return f"L{n}" if 1 <= n <= 3 else "L3"


def _safe(name: str) -> str:
    """파일명으로 쓸 수 있게. 경로 구분자·금지문자만 바꾼다 — 이름 자체는 보존한다."""
    out = str(name or "").strip()
    for ch in '\\/:*?"<>|':
        out = out.replace(ch, "_")
    return out or "unnamed"


def locked_items(paths: ProjectPaths, domain: str, subdir: str) -> dict:
    """`verified_by_user: true` 인 항목들 `{이름: dict}`. **사람이 손본 것.**"""
    root = paths.ontology / "domains" / domain
    out = {}
    for layer in LAYER_DIRS:
        d = root / layer / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.yaml")):
            item = yaml_io.read(f)
            if isinstance(item, dict) and item.get("verified_by_user") is True and item.get("name"):
                out[item["name"]] = item
    return out


def merge_preserve_locked(new_items: list, locked: dict) -> list:
    """🔴 **잠긴 항목이 이긴다.** 새 것 중 이름이 겹치는 것을 버리고 잠긴 것을 얹는다.

    새 내용이 더 좋아 보여도 덮지 않는다 — 좋고 나쁨을 판단하는 것은 우리가 아니다.
    """
    if not locked:
        return list(new_items)
    keep = [i for i in new_items if str((i or {}).get("name") or "") not in locked]
    return keep + list(locked.values())


def write(paths: ProjectPaths, domain: str, *, objects: list | None = None,
          actions: list | None = None, invariants: list | None = None,
          manifest_extra: dict | None = None, prune: bool = True) -> WriteStats:
    """도메인 패키지를 쓴다. **잠긴 항목은 지킨다.**

    `prune` — 이번에 안 들어온 항목 파일을 지운다. 🔴 **잠긴 것은 지우지 않는다.**
    사람이 손본 것을 합성이 사라지게 하면 안 된다.
    """
    root = paths.ontology / "domains" / domain
    st = WriteStats(domain=domain)
    rels: dict = {k: [] for k in SUBDIRS}
    kept_paths: set = set()

    for subdir, items in (("objects", objects), ("actions", actions),
                          ("invariants", invariants)):
        if items is None:
            # 이번에 안 만든 종류는 **건드리지 않는다** — 기존 manifest 목록을 그대로 살린다.
            prev = yaml_io.read(root / MANIFEST) or {}
            rels[subdir] = list(prev.get(_manifest_key(subdir)) or [])
            continue
        locked = locked_items(paths, domain, subdir)
        st.locked_kept += len(locked)
        merged = merge_preserve_locked(items, locked)
        for item in merged:
            name = (item or {}).get("name")
            if not name:
                continue
            rel = f"{_layer_of(item)}/{subdir}/{_safe(name)}.yaml"
            rels[subdir].append(rel)
            kept_paths.add(rel)
            if yaml_io.write(root / rel, item):
                st.written += 1
            else:
                st.unchanged += 1
        if prune:
            st.removed += _prune(root, subdir, kept_paths, locked)

    man = yaml_io.read(root / MANIFEST) or {}
    man["domain"] = domain
    for subdir in SUBDIRS:
        man[_manifest_key(subdir)] = sorted(set(rels[subdir]))
    if manifest_extra:
        man.update(manifest_extra)
    if yaml_io.write(root / MANIFEST, man):
        st.written += 1
    else:
        st.unchanged += 1
    return st


def _manifest_key(subdir: str) -> str:
    """manifest 의 키 이름. 받아온 스냅샷이 `invariants_files` 를 쓴다(실측) — 맞춘다."""
    return "invariants_files" if subdir == "invariants" else subdir


def _prune(root, subdir: str, keep: set, locked: dict) -> int:
    """이번에 안 들어온 항목 파일을 지운다. 🔴 **잠긴 것은 남긴다.**"""
    n = 0
    for layer in LAYER_DIRS:
        d = root / layer / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.yaml")):
            rel = f"{layer}/{subdir}/{f.name}"
            if rel in keep:
                continue
            item = yaml_io.read(f) or {}
            if item.get("name") in locked or item.get("verified_by_user") is True:
                continue          # 사람이 손본 것 — 합성이 지우지 않는다
            f.unlink()
            n += 1
    return n
