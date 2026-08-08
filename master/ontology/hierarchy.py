"""개념 계층 — 하위 온톨로지 문서를 object 로 갖는다 (소 1.3.10).

사용자 제안(2026-08-09): 지금 `objects` 는 **클래스만** 담는데, 하위 문서도 담게 한다.

    [미션 시스템]        objects: [미션 매니저] · [미션 에디터 편집창] · UMissionTaskExecutor
    [미션 에디터 편집창]  objects: UEUW_InGameTaskEditor · …  (클래스 12개)

## 왜 필요한가 — 두 가지가 동시에 풀린다

**① 추상 계층이 실제로 추상해진다.** 위로 갈수록 크고 개념적이라는 성질이 **데이터에**
반영된다. 지금은 `parent_domain` 이 이름표뿐이고 objects 는 여전히 평면 클래스 목록이다.

**② 후보 폭발이 구조적으로 줄어든다.** 실측 2026-08-09 — 멤버 후보가 도메인당 184~190개.
"이미 다른 도메인에 속한 것 제외" 로 MissionEditor 18 · MissionRuntime 36 까지 줄었지만
**`GlobalEventSystem` 은 178 로 거의 그대로**였다. 온 프로젝트가 include 하는 허브라
상한으로 풀 문제가 아니다. 하위로 갈라 상위가 하위를 참조하면 상위의 후보가 사라진다.

## 🔴 구현 규칙 둘 — 지키지 않으면 조용히 망가진다

⑴ **`kind: domain` 으로 종류를 구분한다.** 하위 문서 참조에는 `file` 도 `evidence` 도
   없다. 클래스 규칙으로 검사하면 **레이어 추정·사실 게이트가 전부 오탐**을 낸다.
⑵ **순환을 막는다.** A 가 B 를 갖고 B 가 A 를 가지면 무한 순회다. 상속 그래프에서 이미
   같은 방어를 했지만 문서 참조는 **새 축**이라 따로 필요하다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import yaml_io

KIND_DOMAIN = "domain"          # object 종류 — 하위 문서 참조
KIND_CLASS = "class"            # 기본. 값이 없으면 클래스로 본다(기존 파일 호환)


def is_domain_ref(obj: dict) -> bool:
    """이 object 가 하위 문서 참조인가. **`kind` 가 없으면 클래스**로 본다 —
    받아온 247개 yaml 이 그 키를 안 쓴다(실측)."""
    return str((obj or {}).get("kind", KIND_CLASS)).lower() == KIND_DOMAIN


def _objects(paths: ProjectPaths, domain: str) -> list:
    """도메인의 object yaml 들을 읽어 dict 목록으로."""
    root = paths.ontology / "domains" / domain
    man = yaml_io.read(root / "domain.yaml") or {}
    out = []
    for rel in man.get("objects") or []:
        o = yaml_io.read(root / str(rel))
        if isinstance(o, dict) and o.get("name"):
            out.append(o)
    return out


def children(paths: ProjectPaths, domain: str) -> list:
    """직계 하위 문서 이름들."""
    return [o["name"] for o in _objects(paths, domain) if is_domain_ref(o)]


def descendants(paths: ProjectPaths, domain: str) -> list:
    """모든 하위 문서 (전이적). 🔴 **순환에서 멈춘다.**"""
    out, seen, stack = [], {domain}, list(children(paths, domain))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue                      # 순환 — 여기서 끊는다
        seen.add(cur)
        out.append(cur)
        stack.extend(children(paths, cur))
    return out


def class_members(paths: ProjectPaths, domain: str, *, recursive: bool = False) -> dict:
    """`{클래스: 소스파일}` — **하위 문서 참조는 뺀다.**

    `recursive=True` 면 하위 문서들의 클래스까지 합친다. 상위 도메인의 "실제 관할 범위"
    를 물을 때 쓴다 — 후보 제외 계산이 그것을 필요로 한다.
    """
    out = {}
    for o in _objects(paths, domain):
        if not is_domain_ref(o):
            out[o["name"]] = o.get("file") or ""
    if recursive:
        for d in descendants(paths, domain):
            for o in _objects(paths, d):
                if not is_domain_ref(o):
                    out.setdefault(o["name"], o.get("file") or "")
    return out


@dataclass
class LinkResult:
    status: str                 # added · noop · cycle · not_found
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("added", "noop")


def add_child(paths: ProjectPaths, parent: str, child: str) -> LinkResult:
    """상위 문서에 하위 문서를 object 로 건다. **순환은 거부한다.**

    사용자가 *"미션 시스템 하위 문서로 [미션 에디터]를 만들어줘"* 라고 요청했을 때 부르는
    자리다 — 도구가 스스로 판단해 걸지 않는다.
    """
    root = paths.ontology / "domains"
    p_dir, c_dir = root / parent, root / child
    if not (p_dir / "domain.yaml").is_file():
        return LinkResult("not_found", f"상위 `{parent}` 의 domain.yaml 이 없다")
    if not (c_dir / "domain.yaml").is_file():
        return LinkResult("not_found", f"하위 `{child}` 의 domain.yaml 이 없다")
    if parent == child or parent in descendants(paths, child):
        # 🔴 child 의 자손에 parent 가 있으면 걸자마자 순환이다.
        return LinkResult("cycle", f"`{child}` 아래에 이미 `{parent}` 가 있다 — 순환이 된다")
    if child in children(paths, parent):
        return LinkResult("noop", "이미 걸려 있다")

    rel = f"L1/objects/{child}.yaml"      # 하위 문서는 개념이라 L1(추상)에 둔다
    yaml_io.write(p_dir / rel, {
        "name": child, "kind": KIND_DOMAIN,
        "ref": f"domains/{child}/domain.yaml",
        "note": "하위 온톨로지 문서 참조 — 클래스가 아니다",
    })
    man = yaml_io.read(p_dir / "domain.yaml") or {}
    objs = list(man.get("objects") or [])
    if rel not in objs:
        objs.append(rel)
    man["objects"] = sorted(objs)
    yaml_io.write(p_dir / "domain.yaml", man)
    # 하위 쪽에도 부모를 적어 둔다 — 어느 쪽에서 물어도 답이 나와야 한다.
    cman = yaml_io.read(c_dir / "domain.yaml") or {}
    cman["parent_domain"] = parent
    yaml_io.write(c_dir / "domain.yaml", cman)
    return LinkResult("added", f"`{parent}` 아래 `{child}` 를 걸었다")


def tree(paths: ProjectPaths) -> dict:
    """`{도메인: [직계 하위…]}` — 루트는 `parent_domain` 이 없는 것들이다."""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return {}
    return {d.name: children(paths, d.name)
            for d in sorted(root.iterdir()) if d.is_dir()}


def roots(paths: ProjectPaths) -> list:
    """부모가 없는 도메인. 개념 트리의 꼭대기."""
    t = tree(paths)
    has_parent = {c for kids in t.values() for c in kids}
    return [d for d in t if d not in has_parent]
