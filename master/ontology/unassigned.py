"""미배정 클래스 노출 — 🔴 **노출만 한다. 자동 편입 0** (소 1.3.6).

## 🔴 규모가 곧 설계다

실측 2026-08-09: 그래프의 클래스 **1,806** 중 도메인에 배정된 것은 **111(6%)** 뿐이다.
즉 미배정은 **1,695건** — 평평한 목록으로 "노출" 하면 프로젝트 전체를 쏟아내는 것이고,
사람은 *"다 넣어"* 나 *"됐어"* 로 끝낸다. `collect.propose` 가 후보에 반드시 근거를 붙이는
것과 같은 이유로, 여기서는 **붙을 자리가 보이는 것부터** 내민다.

    ① 인접  — 배정된 클래스의 조상·자식·#include 이웃이다 → **어느 도메인에** 붙을지까지 말한다
    ② 고립  — 어디에도 안 닿는다 → **세어서 보고**하고, 규모 순 상위만 표본으로 보여준다

②를 지우지 않는 이유: *"인접한 것만 보여주면 새 도메인이 필요한 영역이 영영 안 보인다."*
실제로 미배정의 대부분이 ②라면 그건 **도메인이 모자라다는 신호**지 클래스가 하찮다는 뜻이
아니다.

## 🔴 자동 편입은 하지 않는다 (원본 하드룰)

원본이 자동 승급으로 크게 데었고(2026-06-01 영구 비활성), 사용자도 *"자동승급 오동작이
심했다"* 고 확인했다. 이 모듈은 **읽기 전용**이다 — 반환값에 `add` 도 `write` 도 없다.
편입은 사람이 `edit`/`package` 로 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

DEFAULT_LIMIT = 30


@dataclass
class Adjacent:
    """붙을 자리가 보이는 미배정 클래스."""
    name: str
    domain: str                 # 어느 도메인에 인접한가
    why: str                    # 조상 / 자식 / #include 이웃
    via: str = ""               # 그 도메인의 어느 멤버를 통해서

    @property
    def line(self) -> str:
        s = f"{self.name} → {self.domain} ({self.why}"
        return s + (f", {self.via} 경유)" if self.via else ")")


@dataclass
class Report:
    total_classes: int = 0
    assigned: int = 0
    adjacent: list = field(default_factory=list)     # [Adjacent]
    isolated: list = field(default_factory=list)     # [(이름, 메서드수)]
    isolated_total: int = 0
    notes: list = field(default_factory=list)

    @property
    def unassigned_total(self) -> int:
        return self.total_classes - self.assigned

    @property
    def summary(self) -> str:
        s = (f"클래스 {self.total_classes} · 배정 {self.assigned} · "
             f"미배정 {self.unassigned_total} "
             f"(인접 {len(self.adjacent)} · 고립 {self.isolated_total})")
        if self.notes:
            s += " · " + "; ".join(self.notes[:2])
        return s

    def render(self, limit: int = DEFAULT_LIMIT) -> str:
        out = [self.summary, ""]
        if self.adjacent:
            out.append(f"## 붙을 자리가 보이는 것 ({len(self.adjacent)})")
            for a in self.adjacent[:limit]:
                out.append(f"  {a.line}")
            if len(self.adjacent) > limit:
                out.append(f"  … 외 {len(self.adjacent) - limit}건")
        else:
            out.append("## 붙을 자리가 보이는 것 — 없다")
        out.append("")
        # 🔴 고립분을 숨기지 않는다 — 대부분이 여기라면 도메인이 모자라다는 신호다
        out.append(f"## 어디에도 안 닿는 것 — {self.isolated_total}건 (규모 순 상위)")
        for name, n in self.isolated[:limit]:
            out.append(f"  {name}  (메서드 {n})")
        if self.isolated_total > len(self.isolated):
            out.append(f"  … 외 {self.isolated_total - len(self.isolated)}건")
        out.append("")
        out.append("🔴 **자동 편입은 하지 않는다.** 넣을 것을 골라 `edit`/패키지로 사람이 넣는다.")
        return "\n".join(out)


def _graph_classes(paths: ProjectPaths) -> dict:
    """`{클래스: 메서드수}`. 그래프가 없으면 빈 dict — **0을 성공으로 보고하지 않는다.**"""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return {}
    conn = gdb.connect(paths)
    try:
        out = {r["name"]: 0 for r in conn.execute("SELECT name FROM classes")}
        for r in conn.execute(
                "SELECT class_name, COUNT(*) AS n FROM methods GROUP BY class_name"):
            if r["class_name"] in out:
                out[r["class_name"]] = r["n"]
        return out
    finally:
        conn.close()


def scan(paths: ProjectPaths, *, sample: int = DEFAULT_LIMIT) -> Report:
    """미배정을 훑는다. **읽기 전용.**"""
    from . import collect

    rep = Report()
    classes = _graph_classes(paths)
    rep.total_classes = len(classes)
    if not classes:
        rep.notes.append("🔴 클래스 그래프가 없다 — `python -m master.graph build` 먼저")
        return rep

    assigned = collect.classified_elsewhere(paths, exclude="")
    rep.assigned = len({a for a in assigned if a in classes})

    # ① 인접 — 도메인마다 propose 를 돌려 근거까지 받는다 (이미 검증된 경로를 재사용한다)
    seen: dict = {}
    root = paths.ontology / "domains"
    domains = sorted(d.name for d in root.iterdir()
                     if d.is_dir() and (d / "domain.yaml").is_file()) if root.is_dir() else []
    for d in domains:
        try:
            pr = collect.propose(paths, d, collect.members_of(paths, d))
        except Exception as e:                            # noqa: BLE001
            rep.notes.append(f"{d} 후보 수집 실패({type(e).__name__})")
            continue
        for c in pr.candidates:
            if c.name in assigned or c.name not in classes:
                continue
            if c.name not in seen:                        # 먼저 잡은 도메인을 유지한다
                seen[c.name] = Adjacent(name=c.name, domain=d, why=c.why,
                                        via=getattr(c, "via", "") or "")
    rep.adjacent = sorted(seen.values(), key=lambda a: (a.domain, a.name))

    # ② 고립 — 나머지. 🔴 세어서 보고하고, 표본은 규모 순으로.
    isolated = [(n, m) for n, m in classes.items()
                if n not in assigned and n not in seen]
    rep.isolated_total = len(isolated)
    rep.isolated = sorted(isolated, key=lambda t: (-t[1], t[0]))[:sample]
    return rep
