"""도메인 규범 번들 — 소 2.3.1. **목표 ②의 종점.**

    작업 명세(대상 클래스·제목) ──▶ search_norms (소 2.1.2)
                                        │  관련 도메인 ≤2
                                        ▼
                             도메인 패키지에서 **규범만** 추려 번들
                                        │
                                        ▼
                             매니페스트 「도메인 규범」 절 → 작업장 → 코드 작성

## 🔴 규범의 본체는 invariants 다

액션은 *"무엇을 하는가"* 이고 invariant 는 *"무엇을 지켜야 하는가"* 다. 코드를 쓰는 쪽에
필요한 것은 후자다 — `ServerOnlyExecutorRegistration`(서버 권한에서만 등록된다) 같은 것을
모르면 컴파일은 되는데 **런타임에 틀린 코드**가 나온다. 그게 이 프로젝트가 3층 게이트를
두는 이유이기도 하다.

액션은 **대상 클래스와 얽힌 것만** 곁들인다 — 흐름(누가→무엇을)이 invariant 의 맥락이 된다.

## 🔴 "관련된 것만" 이 목표의 절반이다

목표 ②는 *"관련된 것만 추출해 전달"* 이다. 도메인 전체를 실으면 매니페스트가 부풀고, 그건
**프롬프트 예산을 먹어 정작 소스를 못 싣게 만든다**(실측 2.79~2.85자/토큰 · `num_ctx` 8192).
그래서 두 겹으로 좁힌다:

1. **도메인** — `search_norms` 가 최대 2개 (노이즈 3중 차단이 걸린 채로)
2. **항목** — 대상 클래스와 교집합이 있는 액션. invariant 는 도메인 전체 규칙이라 안 거른다

## 🔴 잘랐으면 잘랐다고 적는다

예산을 넘으면 자르되 **몇 개를 뺐는지 본문에 쓴다.** 조용히 자르면 작업장은 그것이 전부인
줄 알고, 없는 규칙을 안 지킨다 — 매니페스트 결손 명시와 같은 규칙이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search import domain_index
from ..context_search.paths import ProjectPaths
from ..ontology import yaml_io

# 🔴 예산 — 매니페스트는 이미 골조·계약·RAG 를 싣는다. 규범이 그것을 밀어내면 안 된다.
# 실측 환산(2.79자/토큰) 기준 3,000자 ≈ 1,075토큰.
TOTAL_CHARS = 3000
SUMMARY_CHARS = 240
INVARIANT_CHARS = 220
MAX_DOMAINS = 2
MAX_INVARIANTS = 6          # 도메인당
MAX_ACTIONS = 3             # 도메인당, 대상 클래스와 얽힌 것만


@dataclass
class DomainNorms:
    domain: str
    summary: str = ""
    invariants: list = field(default_factory=list)      # {name, text, evidence}
    actions: list = field(default_factory=list)         # {name, description, primary}
    dropped_invariants: int = 0
    dropped_actions: int = 0
    source: str = ""
    score: float = 0.0

    @property
    def empty(self) -> bool:
        return not (self.invariants or self.actions or self.summary)


@dataclass
class NormBundle:
    query: str = ""
    domains: list = field(default_factory=list)
    degraded: list = field(default_factory=list)      # 🔴 왜 비었는지
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.domains)

    @property
    def counts(self) -> tuple:
        return (len(self.domains),
                sum(len(d.invariants) for d in self.domains),
                sum(len(d.actions) for d in self.domains))

    def render(self) -> list:
        """매니페스트에 넣을 마크다운 줄. **비면 왜 비었는지 쓴다.**"""
        if not self.domains:
            why = " / ".join(self.degraded) or "관련 도메인을 찾지 못했다"
            return [f"_규범 없음 — {why}. "
                    f"**이 태스크는 도메인 규범 grounding 없이 진행된다.**_"]
        out: list = []
        for d in self.domains:
            head = f"### `{d.domain}`"
            if d.score:
                head += f"  ({d.source}, rrf={d.score:.4f})"
            out.append(head)
            if d.summary:
                out.append(f"> {d.summary}")
            if d.invariants:
                out.append("")
                out.append("**지켜야 할 규칙 (invariants)**")
                for i in d.invariants:
                    ev = f"  — `{i['evidence']}`" if i.get("evidence") else ""
                    out.append(f"- **{i['name']}**: {i['text']}{ev}")
            if d.actions:
                out.append("")
                out.append("**관련 액션**")
                for a in d.actions:
                    impl = f" (`{a['primary']}`)" if a.get("primary") else ""
                    out.append(f"- **{a['name']}**{impl}: {a['description']}")
            if d.dropped_invariants or d.dropped_actions:
                # 🔴 잘랐으면 잘랐다고 적는다
                out.append("")
                out.append(f"_(예산으로 제외: invariant {d.dropped_invariants}건 · "
                           f"액션 {d.dropped_actions}건 — 필요하면 "
                           f"`ontology/domains/{d.domain}/` 를 직접 읽을 것)_")
            out.append("")
        return out


def _clip(text: str, limit: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= limit else t[:limit].rstrip() + "…"


def _relevant(action: dict, targets: set) -> bool:
    """액션이 대상 클래스와 얽혀 있나. 대상이 없으면 **전부 관련**으로 본다."""
    if not targets:
        return True
    names = set(action.get("objects_affected") or [])
    impl = (action.get("implementation") or {}).get("primary") or ""
    if "::" in impl:
        names.add(impl.split("::", 1)[0])
    for step in action.get("flow") or []:
        if isinstance(step, dict) and step.get("actor"):
            names.add(str(step["actor"]))
    return bool(names & targets)


def _load_domain(paths: ProjectPaths, domain: str, targets: set) -> DomainNorms:
    root = paths.ontology / "domains" / domain
    man = yaml_io.read(root / "domain.yaml") or {}
    dn = DomainNorms(domain=domain, summary=_clip(man.get("summary"), SUMMARY_CHARS))

    for rel in man.get("invariants_files") or []:
        item = yaml_io.read(root / str(rel))
        if not isinstance(item, dict) or not item.get("text"):
            continue
        if len(dn.invariants) >= MAX_INVARIANTS:
            dn.dropped_invariants += 1
            continue
        dn.invariants.append({"name": item.get("name") or "(이름없음)",
                              "text": _clip(item["text"], INVARIANT_CHARS),
                              "evidence": item.get("evidence") or ""})

    for rel in man.get("actions") or []:
        item = yaml_io.read(root / str(rel))
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if not _relevant(item, targets):
            continue
        if len(dn.actions) >= MAX_ACTIONS:
            dn.dropped_actions += 1
            continue
        dn.actions.append({
            "name": item["name"],
            "description": _clip(item.get("description") or "", INVARIANT_CHARS),
            "primary": (item.get("implementation") or {}).get("primary") or "",
        })
    return dn


def attach(paths: ProjectPaths, *, classes: list | None = None, stem: str = "",
           extra_query: str = "", top_k: int = MAX_DOMAINS,
           budget: int = TOTAL_CHARS, search=None) -> NormBundle:
    """작업 명세 → 도메인 규범 번들. **베스트에포트** — 실패해도 등록을 막지 않는다.

    🔴 다만 **조용히 비우지 않는다.** 왜 비었는지가 `degraded` 에 남고 매니페스트 본문에 찍힌다.
    """
    targets = {c for c in (classes or []) if c}
    query = " ".join(x for x in [" ".join(sorted(targets)), stem, extra_query] if x and x.strip())
    b = NormBundle(query=query)
    if not query.strip():
        b.degraded.append("질의를 만들 수 없었다 (대상 클래스·제목이 비었다)")
        return b

    finder = search or domain_index.search_norms
    try:
        hits = finder(paths, query, top_k=top_k)
    except Exception as e:                              # noqa: BLE001 — 등록을 막지 않는다
        b.degraded.append(f"규범 검색 실패: {type(e).__name__}: {e}")
        return b
    if not hits:
        # 🔴 노이즈 3중 차단이 의도적으로 0건을 낸 것일 수 있다 — 실패가 아니다.
        b.degraded.append("질의와 정확히 매칭되는 도메인이 없다 (노이즈 차단이 정상 동작한 결과일 수 있다)")
        return b

    used = 0
    for h in hits:
        dn = _load_domain(paths, h["domain"], targets)
        dn.source, dn.score = h.get("source", ""), float(h.get("rrf_score") or 0)
        if dn.empty:
            continue
        size = len(dn.summary) + sum(len(i["text"]) + len(i["name"]) for i in dn.invariants) \
            + sum(len(a["description"]) + len(a["name"]) for a in dn.actions)
        if used + size > budget and b.domains:
            b.truncated = True
            b.degraded.append(f"예산({budget}자)으로 도메인 {h['domain']} 을 싣지 않았다")
            break
        b.domains.append(dn)
        used += size
    if not b.domains and not b.degraded:
        b.degraded.append("찾은 도메인에 규범 항목이 없다")
    return b
