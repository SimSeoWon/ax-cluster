"""질의 → 도메인 **결정적** 추론 (소 2.2.2).

## `search_norms` 와 무엇이 다른가

    search_norms   BM25 + 벡터로 **닮은** 도메인을 찾는다      통계 · 순위 · 언제나 뭔가 나온다
    infer          질의에 나온 **클래스의 소속**을 표에서 읽는다  결정적 · 근거 있음 · 없으면 없다

전자는 *"이 질의와 비슷한 도메인"*, 후자는 *"이 질의가 말하는 클래스가 속한 도메인"* 이다.
후자가 맞으면 **근거를 댈 수 있다** — *"`UMissionTaskExecutor` 가 MissionRuntime 소속이다"*.

## 🔴 출처는 패키지 yaml 이다 — DB 표가 아니다

`class_graph.db` 에 `class_ontology` 표가 있지만 **행이 0 이다**(실측 2026-08-10). 우리
파이프라인은 그 표를 채우지 않고, 실제 소속은 각 도메인의 `objects/*.yaml` 에 있다
(`collect.classified_elsewhere` 도 거기서 읽는다). **죽은 표를 근거로 삼지 않는다.**

## 🔴 모르면 비운다

질의에 아는 클래스가 하나도 없으면 **빈 결과**다. 산문에서 도메인 이름을 닮은 말을 찾아
추측하지 않는다 — 그건 `search_norms` 의 일이고, 그쪽은 노이즈 3중 차단을 갖고 있다.
여기서 추측하면 *"결정적"* 이라는 이 함수의 유일한 값어치가 사라진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .paths import ProjectPaths

# UE 식별자 꼴. 접두사(U/A/F/I/E)가 붙은 것과 일반 PascalCase 를 모두 본다.
_IDENT = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")


@dataclass
class Evidence:
    cls: str
    domain: str
    via: str = "질의에 직접"          # 또는 "별칭: <말>"

    @property
    def line(self) -> str:
        return f"{self.cls} → {self.domain} ({self.via})"


@dataclass
class Inference:
    domains: list = field(default_factory=list)      # 근거 수 내림차순
    evidence: list = field(default_factory=list)
    unknown: list = field(default_factory=list)      # 질의에 있었지만 어느 도메인에도 없는 클래스
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.domains)

    @property
    def summary(self) -> str:
        if not self.domains:
            # 🔴 왜 못 했는지가 요약에 없으면 사람은 "버그" 로 읽는다 — 사유를 싣는다
            s = "도메인 추론 불가 — " + (self.notes[0] if self.notes
                                          else "질의에 아는 클래스가 없다")
            if self.unknown:
                s += f" (미배정 후보 {len(self.unknown)}: {', '.join(self.unknown[:3])})"
            return s
        s = "도메인: " + ", ".join(self.domains)
        return s + " · 근거 " + "; ".join(e.line for e in self.evidence[:4])


def membership(paths: ProjectPaths) -> dict:
    """`{클래스: 도메인}`. **패키지 yaml 이 출처다** (위 § 참조)."""
    from ..ontology import hierarchy, yaml_io
    root = paths.ontology / "domains"
    out: dict = {}
    if not root.is_dir():
        return out
    for d in sorted(x for x in root.iterdir() if x.is_dir()):
        man = yaml_io.read(d / "domain.yaml") or {}
        for rel in man.get("objects") or []:
            item = yaml_io.read(d / str(rel)) or {}
            name = item.get("name")
            # 하위 문서 참조는 클래스가 아니다
            if name and not hierarchy.is_domain_ref(item):
                out.setdefault(str(name), d.name)
    return out


def infer(paths: ProjectPaths, query: str, *, expansion=None) -> Inference:
    """질의가 말하는 도메인. **읽기 전용이고 LLM 을 쓰지 않는다.**

    `expansion` 을 주면(시소러스 확장 결과) 별칭으로 얻은 클래스도 근거로 센다 —
    한글 질의는 식별자를 직접 쓰지 않으므로 그쪽이 실질 경로다.
    """
    inf = Inference()
    q = (query or "").strip()
    if not q:
        return inf
    owner = membership(paths)
    if not owner:
        inf.notes.append("도메인 패키지가 없다 — 추론할 근거가 없다")
        return inf

    found: dict = {}                                   # 클래스 → Evidence
    for name in _IDENT.findall(q):
        if name in owner:
            found[name] = Evidence(name, owner[name], "질의에 직접")
        elif name not in found and len(name) > 3 and name[0] in "UAFIE":
            inf.unknown.append(name)                   # 클래스처럼 생겼는데 소속이 없다

    for term, cls in (getattr(expansion, "added", None) or []):
        if cls in owner and cls not in found:
            found[cls] = Evidence(cls, owner[cls], f"별칭: {term}")
        elif cls not in owner and cls not in inf.unknown:
            inf.unknown.append(cls)

    if not found:
        return inf                                     # 🔴 추측하지 않는다

    counts: dict = {}
    for e in found.values():
        counts[e.domain] = counts.get(e.domain, 0) + 1
    inf.evidence = sorted(found.values(), key=lambda e: (e.domain, e.cls))
    inf.domains = [d for d, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return inf


def infer_for(paths: ProjectPaths, query: str) -> Inference:
    """시소러스 확장까지 태워서 추론한다 — 한글 질의의 실질 경로."""
    from .expand import expand_for
    return infer(paths, query, expansion=expand_for(paths, query))
