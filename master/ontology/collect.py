"""관계 수집 — 도메인 멤버 후보를 **제안**한다 (중 1.3 입력, LLM 0).

원본: `watcher/ontology_dep_graph.py` (`expand_seeds_with_one_hop_children` ·
`_ancestors_of` · `_includes_for`).

## [중요] 원본과 갈리는 지점 — 자동 확장이 아니라 제안이다

원본은 자식 1홉을 **자동으로** 시드에 넣는다(`expand_seeds_with_one_hop_children`).
여기서는 **후보로 내밀고 묻는다**:

    "관련 클래스로 이것들이 보인다 — 포함할까?"
    "이 클래스들의 자식도 있다"

사용자 지시(2026-08-09): *"휴리스틱이 최대한 수집되어야 하니 대화형으로 어떤 클래스들이
추가될지, 관련된 클래스는 이것이 있다던지 제안하고 질문해야 한다"*.

자동으로 넣으면 **무엇이 이 개념에 속하는가** 라는 사람의 판단이 반영되지 않는다.
시소러스 창구와 같은 패턴이고, `silently auto-add 금지`·`자동 승급 영구 비활성`과 같은 뿌리다.

## 세 가지 근거를 모은다 (전부 실측 — 지어내지 않는다)

| 근거 | 어디서 | 왜 |
|---|---|---|
| **조상 4단계** | `class_graph` 상속 | 멤버의 계약이 어디서 오는지 |
| **자식 1홉** | 같은 곳 | 부모만 등록해도 구현체가 딸려 온다 |
| **`#include` 이웃** | `dependency_graph` | 상속이 없어도 협력하는 것 |

깊이 4는 원본 값이다(`_ancestors_of(max_depth=4)`). 더 올리면 엔진 계층까지 올라가
`UObject` 같은 것이 모든 도메인의 조상이 되어 신호가 사라진다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths
from ..graph import class_graph as cg, db as gdb, dependency as dep

ANCESTOR_DEPTH = 4          # 원본 값. 더 올리면 엔진 계층이 모두의 조상이 된다
PROPOSAL_LIMIT = 20         # 한 번에 물어볼 수 있는 양. 넘으면 사람이 안 읽는다

# [중요] **`#include` 1홉이 후보 폭발의 원인이다** — 실측 2026-08-09: 받아온 도메인에 돌리니
# 후보가 **184~190개**로 나왔고 대부분이 이 채널이었다. 물어볼 수 있는 양이 아니다.
#
# 헤더 하나가 수십 파일에 얽히므로 1홉만으로도 도메인 전체 규모를 넘는다. 그래서:
#   ⑴ 멤버당 이웃 파일 수를 자른다 (아래)
#   ⑵ [중요] **이미 어느 도메인에든 속한 클래스는 후보에서 뺀다** — 그게 가장 크게 줄인다.
#      상위 문서가 하위 문서를 object 로 갖는 구조(소 1.3.10)에서 특히 그렇다:
#      하위에 있는 클래스를 상위가 다시 물어볼 이유가 없다
INCLUDE_FANOUT = 4          # 멤버 파일당 볼 이웃 파일 수
INCLUDE_CANDIDATES = 25     # 이 채널이 낼 수 있는 후보 총량


@dataclass
class Candidate:
    name: str
    why: str                 # "조상" · "자식" · "#include 이웃" — 사용자가 판단할 근거
    via: str = ""            # 어느 멤버를 통해 나왔나
    file: str = ""


@dataclass
class Proposal:
    domain: str
    members: list = field(default_factory=list)       # 이미 멤버인 것
    candidates: list = field(default_factory=list)    # 물어볼 것

    @property
    def empty(self) -> bool:
        return not self.candidates

    @property
    def question(self) -> str:
        """작업 PC 의 Claude 가 사용자에게 던질 문장.

        [중요] **후보가 없으면 없다고 말한다.** 채우려고 무관한 클래스를 넣지 않는다.
        """
        if not self.candidates:
            return (f"`{self.domain}` 에 추가할 만한 관련 클래스를 찾지 못했다 "
                    f"(멤버 {len(self.members)}개 기준). 직접 지정하면 넣는다.")
        by = {}
        for c in self.candidates[:PROPOSAL_LIMIT]:
            by.setdefault(c.why, []).append(c.name)
        parts = [f"**{why}**: {', '.join(names[:8])}" for why, names in by.items()]
        more = ("" if len(self.candidates) <= PROPOSAL_LIMIT
                else f" (외 {len(self.candidates) - PROPOSAL_LIMIT}개)")
        return (f"`{self.domain}` 에 넣을 만한 관련 클래스가 보인다 — "
                + " · ".join(parts) + more
                + ". 어떤 것을 포함할까? 넣지 않을 것은 그대로 두면 된다.")

    @property
    def summary(self) -> str:
        return f"{self.domain}: 멤버 {len(self.members)} · 후보 {len(self.candidates)}"


def ancestors(paths: ProjectPaths, name: str, depth: int = ANCESTOR_DEPTH) -> list:
    """상속 조상. 도메인 밖도 포함한다 — **계약이 어디서 오는지**가 판단 근거다."""
    return cg.find_ancestors(paths, name, max_depth=depth)


def children(paths: ProjectPaths, names: list) -> dict:
    """멤버들의 **직계 자식**(1홉). `{자식: 통해서 온 부모}`."""
    out = {}
    for n in names:
        for child in cg.find_subclasses(paths, n, max_depth=1):
            out.setdefault(child, n)
    return out


def include_neighbours(paths: ProjectPaths, files: list) -> dict:
    """`#include` 이웃 파일 → 그 파일이 정의하는 클래스. `{클래스: 통해서 온 파일}`.

    [주의] 역방향(`dependents`)은 basename 근사라 무관한 항목이 섞일 수 있다 — 그래서
    **후보로만** 쓴다. 자동으로 넣지 않는 이유가 여기에도 있다.
    """
    if not gdb.exists(paths) or not dep.exists(paths):
        return {}
    neigh: dict = {}
    seen_files: set = set()
    for f in files:
        if not f:
            continue
        for g in list(dep.dependencies(paths, f, depth=1))[:INCLUDE_FANOUT] + \
                 list(dep.dependents(paths, f, depth=1))[:INCLUDE_FANOUT]:
            if g not in seen_files and g not in files:
                seen_files.add(g)
    if not seen_files:
        return {}
    conn = gdb.connect(paths)
    try:
        marks = ",".join("?" * len(seen_files))
        for r in conn.execute(
                f"SELECT name, file FROM classes WHERE file IN ({marks}) "
                f"ORDER BY name LIMIT ?", (*seen_files, INCLUDE_CANDIDATES)):
            neigh.setdefault(r["name"], r["file"])
    finally:
        conn.close()
    return neigh


def classified_elsewhere(paths: ProjectPaths, exclude: str = "") -> set:
    """**이미 어느 도메인에든 속한 클래스.** 후보에서 뺀다.

    두 곳을 본다 — `class_ontology` 분류행과 **모든 도메인의 object yaml**. 후자가
    중요하다: 하위 온톨로지 문서(소 1.3.10)에 이미 들어간 클래스를 상위가 다시 물어보면
    같은 결정을 두 번 시키는 셈이다.
    """
    out: set = set()
    root = paths.ontology / "domains"
    if root.is_dir():
        from . import hierarchy, yaml_io
        for d in root.iterdir():
            if not d.is_dir() or d.name == exclude:
                continue
            man = yaml_io.read(d / "domain.yaml") or {}
            for rel in man.get("objects") or []:
                o = yaml_io.read(d / str(rel)) or {}
                # 하위 문서 참조는 클래스가 아니라 후보 제외 대상도 아니다.
                if o.get("name") and not hierarchy.is_domain_ref(o):
                    out.add(o["name"])
    try:
        if gdb.exists(paths):
            conn = gdb.connect(paths)
            try:
                for r in conn.execute(
                        "SELECT class_name FROM class_ontology "
                        "WHERE ontology_domain IS NOT NULL AND ontology_domain != ?",
                        (exclude,)):
                    out.add(r["class_name"])
            finally:
                conn.close()
    except Exception:                                   # noqa: BLE001
        pass
    return out


def propose(paths: ProjectPaths, domain: str, members: dict) -> Proposal:
    """도메인 멤버 → 추가 후보. `members` 는 `{클래스: 소스파일}`.

    **이미 멤버인 것은 후보에서 뺀다.** 그리고 근거(`why`)를 반드시 붙인다 — 근거 없는
    후보는 사용자가 판단할 수 없고, 그러면 "다 넣어" 나 "다 빼" 로 끝난다.
    """
    p = Proposal(domain=domain, members=sorted(members))
    # [중요] 이미 다른 도메인에 속한 것은 묻지 않는다 — 후보 폭발의 실질 대책.
    #    **자기 하위 문서의 클래스도 뺀다** — 하위가 이미 관할하는 것을 상위가 다시 물으면
    #    같은 결정을 두 번 시키는 셈이고, 허브 도메인에서 후보가 폭발하는 원인이다.
    from . import hierarchy
    known = (set(members) | classified_elsewhere(paths, exclude=domain)
             | set(hierarchy.class_members(paths, domain, recursive=True)))
    seen: dict = {}

    for name in sorted(members):
        for a in ancestors(paths, name):
            if a not in known and a not in seen:
                seen[a] = Candidate(a, "조상(계약이 오는 곳)", via=name)

    for child, via in children(paths, list(members)).items():
        if child not in known:
            seen[child] = Candidate(child, "자식(구현체)", via=via)   # 자식이 더 강한 신호

    for name, f in include_neighbours(paths, [v for v in members.values() if v]).items():
        if name not in known and name not in seen:
            seen[name] = Candidate(name, "#include 이웃", file=f)

    p.candidates = sorted(seen.values(), key=lambda c: (c.why, c.name))
    return p


def members_of(paths: ProjectPaths, domain: str) -> dict:
    """현재 멤버 `{클래스: 소스파일}` — `stale` 과 같은 규칙(manifest ∪ 분류행)."""
    from . import stale
    return stale._members(paths, domain)
