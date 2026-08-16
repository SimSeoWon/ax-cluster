"""부분 무효화 — 변경 클래스가 **영향 주는 yaml 만** 다시 만든다 (소 3.2.2). **LLM 0.**

원본: `watcher/ontology_invalidation.py` 190줄 (Phase η.7.2/.3, 2026-05-31).
원본이 이 사이클을 만든 근거는 사용자 통찰이었다 — *"통짜 데이터라 하나 수정되면 모두
재생성. 수정된 내용만"*. 도메인 재합성 비용이 **변경 클래스 비율만큼**으로 준다.

## 원전이 사용자 승인으로 정한 설계 결정 셋 — 그대로 옮긴다

    ① scope = 변경 ∪ co-mentioned      한 yaml 이 여러 클래스를 걸치면 같이 본다 (응집)
    ② 보수적 무효화                     텍스트 토큰 매칭 + **읽기 실패도 무효화**
    ③ MD content-hash 변경·부재 → full  도메인의 뜻이 바뀌면 부분 갱신은 틀린 답이다

②가 보수적인 이유는 원전이 적어 둔 그대로다 — **누락은 silent staleness 의 원천**이다.
과하게 무효화하면 LLM 을 더 쓰고, 놓치면 낡은 문서가 조용히 남는다. 값이 다르다.

## 우리 데이터 실측 (2026-08-15) — 이식이 값을 내는지 먼저 쟀다

    stale 도메인 4개   GlobalEventSystem 1/9 · MissionEditor 3/13
                       MissionRuntime 3/11 · UiManagement 8/9
    manifest md_hash   [중요] 7개 중 3개만 보유 — **전부 받아온 스냅샷이 찍은 것**이고,
                       그중 2개는 이미 현재 MD 와 불일치. 우리 `package.write` 는
                       그 값을 **한 번도 안 찍었다** → 지금 상태로는 전부 full 폴백

그래서 이식은 판정 로직만으로 성립하지 않는다. 원전은 같은 사이클에서
`write_domain_yaml` 이 `md_hash` 를 찍게 했고(`ontology_yaml_dump.py:276`), 우리도
`package.write` 에 그 스탬프를 같이 넣었다 — **신호원을 안 찍으면 판정기가 영원히 full
을 고른다.** (마일스톤 4 함정: *"가드를 만들면 깨울 주체를 같은 커밋에 넣는다"*.)

[주의] 해시식이 원전과 같은지도 쟀다 — `UiManagement` 의 스냅샷 `md_hash` 와 우리
`domain_md.content_hash` 가 **같은 값**이다(`51bbaedc41ffa531`). 다르면 안 바뀐 도메인을
*"MD 변경"* 으로 읽어 부분 갱신이 통째로 죽는다.

## [중요] 원전과 다르게 둔 것 셋

**① 변경 클래스는 다시 재지 않고 `stale` 에서 가져온다.** 원전 `changed_member_classes`
와 우리 `stale.compute` 는 **같은 판정식**(저장 `source_commit` ≠ 컨텍스트 MD
`source_commit`)이다. 한 번 더 구현하면 판정식이 둘이 되고, 그 둘은 언젠가 갈라진다.

**② 잠긴·보호된 yaml 은 무효화하지 않는다.** `protected` 는 **우리 개념**이다(받아온
스냅샷 — 리포트 11 §20: 우리 합성이 스냅샷보다 얕았다). 원전엔 그 개념이 없어 무효화분을
선삭제해도 잃을 것이 없지만, [중요] **우리가 그대로 옮기면 재생성되지 않는 스냅샷 본문을
지우게 된다.** 잠긴 것은 `preserved` 로 세고 건드리지 않는다.

**③ 판정 사유를 로그가 아니라 값으로 돌려준다** (`RefreshPlan.reason`). 원전은
`_LOG` 로 흘리는데, 우리 σ 감사 기준이 *"예외·판정을 값으로 돌려주면 조용하지 않다"* 다.
호출자가 카나리로 찍는다.

## [주의] 한글 베이스와 만나는 자리 (`#194` 머지 지점 — 복각 중에는 고치지 않는다)

무효화 판정은 **영문 식별자 토큰**으로만 언급을 찾는다(`_IDENT_RE`). 액션 yaml 이 클래스를
한글 별칭(`aliases`)으로만 가리키면 그 yaml 은 무효화되지 않는다. 지금은 별칭이 오브젝트
yaml 쪽에만 있어 실해가 없지만, 태그·별칭 커버리지가 올라가면 달라진다. [중요] **복각 중에는
표시만 남긴다** — 그 표시가 곧 머지 지점 목록이다(사용자 확정 2026-08-15).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import collect, domain_md, package, stale, yaml_io

# CamelCase/UE 식별자 토큰. [중요] **원전 정규식 그대로** — 바꾸면 같은 입력에 다른 무효화
# 범위가 나와 원전 리포트와 비교할 수 없다.
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")

KINDS = ("actions", "invariants")


def domain_md_hash(paths: ProjectPaths, domain: str) -> str:
    """원전 이름 보존 — 실체는 `domain_md.content_hash`(MD 를 소유한 모듈에 둔다)."""
    return domain_md.content_hash(paths, domain)


def manifest_md_hash(paths: ProjectPaths, domain: str) -> str | None:
    """manifest 에 찍힌 `md_hash`. 없으면 `None` (레거시·최초 → full).

    [중요] 원전은 정규식으로 긁지만 우리는 **이미 있는 파서**로 읽는다. manifest 를 읽는
    방법이 둘이 되면 한쪽만 고쳐지는 날이 온다.
    """
    man = yaml_io.read(paths.ontology / "domains" / domain / package.MANIFEST)
    if not isinstance(man, dict):
        return None
    v = man.get("md_hash")
    return str(v) if v else None


def changed_member_classes(paths: ProjectPaths, domain: str) -> set:
    """이 도메인에서 **변경된 멤버 클래스**. 판정은 `stale` 이 한다(위 「다르게 둔 것 ①」)."""
    for r in stale.compute(paths, [domain]):
        if r.domain == domain:
            return {name for name, _stored, _latest in r.members}
    return set()


@dataclass
class Invalidation:
    """무효화 범위. [중요] **경로를 돌려준다 — 지우는 것은 호출자다.**"""
    domain: str
    objects: set = field(default_factory=set)         # 변경 클래스 자신
    actions: list = field(default_factory=list)       # 무효화 대상 yaml 경로
    invariants: list = field(default_factory=list)
    scope_classes: set = field(default_factory=set)   # 변경 ∪ 응집
    preserved_actions: int = 0
    preserved_invariants: int = 0
    locked_kept: int = 0                              # [중요] 잠금·보호라 무효화 안 한 것
    unreadable: int = 0                               # 못 읽어서 무효화한 것 (안전측)

    @property
    def empty(self) -> bool:
        return not (self.actions or self.invariants)

    @property
    def summary(self) -> str:
        s = (f"{self.domain}: 변경 {len(self.objects)} · scope {len(self.scope_classes)} · "
             f"무효화 a{len(self.actions)}/i{len(self.invariants)} · "
             f"보존 a{self.preserved_actions}/i{self.preserved_invariants}")
        if self.locked_kept:
            s += f" ·  잠금 {self.locked_kept}"
        if self.unreadable:
            s += f" · [주의] 못 읽어 무효화 {self.unreadable}"
        return s


def _mentioned_members(text: str, member_names: set) -> set:
    """yaml 원문이 언급한 멤버 클래스 (식별자 토큰 ∩ 도메인 멤버)."""
    return set(_IDENT_RE.findall(text)) & member_names


def _iter_yaml(package_dir: Path, kind: str) -> list:
    return sorted(package_dir.glob(f"L*/{kind}/*.yaml"))


def determine_invalidation(paths: ProjectPaths, domain: str, changed_classes: set) -> Invalidation:
    """변경 클래스가 영향 주는 yaml 을 고른다. **보수적** — 애매하면 무효화한다.

    `scope_classes` 는 변경 클래스 ∪ 무효화된 yaml 이 함께 언급한 멤버다. 한 액션이 두
    클래스를 걸치는데 한쪽만 다시 뽑으면 그 액션은 반쪽 근거로 재생성된다.
    """
    changed = set(changed_classes)
    inv = Invalidation(domain=domain, objects=set(changed), scope_classes=set(changed))
    pkg = paths.ontology / "domains" / domain
    member_names = set(collect.members_of(paths, domain))

    for kind in KINDS:
        dst = inv.actions if kind == "actions" else inv.invariants
        for p in _iter_yaml(pkg, kind):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                dst.append(p)                 # [중요] 읽기 실패 = 보수적 무효화 (원전 그대로)
                inv.unreadable += 1
                continue
            item = yaml_io.load(text)
            if isinstance(item, dict) and (item.get("verified_by_user") is True
                                           or item.get("protected") is True):
                # [중요] 사람이 검수했거나 받아온 스냅샷이다 — 재생성이 대체하지 못한다.
                inv.locked_kept += 1
                _bump_preserved(inv, kind)
                continue
            mentioned = _mentioned_members(text, member_names)
            if mentioned & changed:
                dst.append(p)
                inv.scope_classes |= mentioned      # 응집 — 같이 언급된 멤버까지
            else:
                _bump_preserved(inv, kind)
    return inv


def _bump_preserved(inv: Invalidation, kind: str) -> None:
    if kind == "actions":
        inv.preserved_actions += 1
    else:
        inv.preserved_invariants += 1


@dataclass
class RefreshPlan:
    """이 도메인을 어떻게 재합성할 것인가. `changed is None` 이면 **full**."""
    domain: str
    changed: set | None = None
    reason: str = ""

    @property
    def full(self) -> bool:
        return self.changed is None

    @property
    def summary(self) -> str:
        if self.full:
            return f"{self.domain} → full ({self.reason})"
        return (f"{self.domain} → partial (변경 클래스 {len(self.changed)}건: "
                f"{', '.join(sorted(self.changed)[:8])}"
                f"{'…' if len(self.changed) > 8 else ''})")


def plan_domain_refresh(paths: ProjectPaths, domain: str) -> RefreshPlan:
    """full 인가 partial 인가. **LLM 0 · 부작용 0.**

    full 폴백 조건은 원전 decision 3 그대로다 — manifest `md_hash` 부재(레거시·최초)
    또는 도메인 MD 가 그 뒤로 바뀌었다.
    """
    last = manifest_md_hash(paths, domain)
    now = domain_md_hash(paths, domain)
    if not last:
        return RefreshPlan(domain, None, "이유: manifest md_hash 부재/레거시")
    if last != now:
        return RefreshPlan(domain, None,
                           f"이유: 도메인 MD 변경 {last[:8]}≠{(now or '없음')[:8]}")
    changed = changed_member_classes(paths, domain)
    if not changed:
        return RefreshPlan(domain, set(), "변경 클래스 0 — 재합성할 것이 없다")
    return RefreshPlan(domain, changed)


__all__ = [
    "Invalidation", "RefreshPlan", "changed_member_classes", "determine_invalidation",
    "domain_md_hash", "manifest_md_hash", "plan_domain_refresh",
]
