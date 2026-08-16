"""레이어 추정 — L1/L2/L3 (소 1.3.5). **LLM 0.**

원본: `watcher/ontology_layers.py` (Phase η.6.1, 2026-05-28 재보정판).

    L1 = 추상/계약/책임 — 도메인 책임 트렁크 (분기·연 단위 변경)
    L2 = 부모/기반 구현 — 공통 패턴 가지 (월 단위)
    L3 = 실제 구현 리프 — 휘발성 구현체 (주·일 단위)

## [중요] 동등 투표 평균을 쓰지 않는다 — 원본이 한 번 실패하고 고친 지점

원안은 4 시그널 동등 투표 평균이었는데 **모든 클래스를 중앙(L2)으로 끌어당겨 L3 에
도달하지 못했다** — 회사 실측 `MissionEditor L1=1 / L2=12 / L3=0`. "L3 = 구현 리프 다수"
라는 설계 의도와 정반대다.

재보정: **구조가 먼저 축을 정하고, git churn 은 보정자로 '강등' 만** 한다.

    트렁크(자손 또는 자식 ≥1):  depth==0 → L1        (도메인 내부 상속 트리 루트)
                                depth>=1 → L2        (부모도 자식도 있는 중간 기반)
    리프(자손 0 · 자식 0)                → L3        (구현체)
    + L2 이면서 고churn(90일 ≥ 임계)     → L3 강등    (휘발성 구현)

[중요] **상향(리프→L2)은 하지 않는다.** git 커밋 0 은 *"진짜 안정"* 과 *"git 시그널이 죽음"*
(얕은 클론·신규 파일)을 **구분하지 못한다.** 하향만 하면 시그널이 죽어도 리프→L3 기본
분포가 보장된다.

## 그래프는 **도메인 내부**로 한정한다

`parent_map`·`children_map` 을 도메인 멤버들로만 만든다. 엔진 클래스(`AActor`)까지 넣으면
모든 것이 그 자손이 되어 depth 가 무의미해진다 — 원본이 *"도메인 scope 로 자연히 한정"*
이라고 적어 둔 것이 이 뜻이다.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# 90일 커밋이 이 값 이상이면 휘발성 — 중간 기반(L2)을 구현 리프(L3)로 강등한다.
GIT_VOLATILE = 10
GIT_WINDOW_DAYS = 90


@dataclass
class Estimate:
    name: str
    layer: int
    confidence: float
    signals: dict = field(default_factory=dict)
    locked: bool = False          # verified_by_layer — 사용자 검수 잠금

    @property
    def summary(self) -> str:
        s = self.signals
        return (f"{self.name}: L{self.layer} ({self.confidence}) "
                f"자손={s.get('descendants')} 자식={s.get('fan_in')} 깊이={s.get('depth')}"
                + (" " if self.locked else "")
                + (" ↓git" if s.get("git_demoted") else ""))


def build_member_graph(members: dict) -> tuple[dict, dict]:
    """`{클래스: 부모}` → (parent_map, children_map). **도메인 안에 있는 부모만** 잇는다."""
    names = set(members)
    parent_map, children_map = {}, {}
    for name, parent in members.items():
        if parent and parent in names:
            parent_map[name] = parent
            children_map.setdefault(parent, []).append(name)
    return parent_map, children_map


def descendant_count(name: str, children_map: dict) -> int:
    """자손 총수. 순환이 있어도 멈춘다 — 상속 그래프가 항상 DAG 라고 믿지 않는다."""
    seen, stack, n = {name}, list(children_map.get(name, [])), 0
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        n += 1
        stack.extend(children_map.get(cur, []))
    return n


def internal_depth(name: str, parent_map: dict) -> int:
    """도메인 내부 상속 깊이. 루트는 0. 순환은 방문 집합으로 끊는다."""
    seen, depth, cur = {name}, 0, name
    while cur in parent_map:
        cur = parent_map[cur]
        if cur in seen:
            break
        seen.add(cur)
        depth += 1
    return depth


def count_commits(repo: Path, file: str, *, days: int = GIT_WINDOW_DAYS) -> int:
    """최근 N일 커밋 수. **실패하면 0** — git 이 없다고 추정을 막지 않는다.

    0 이 "안정" 을 뜻하지 않는다는 점이 중요하다(위 docstring). 그래서 이 값은 **강등
    조건에만** 쓰인다.
    """
    if not file or not repo.is_dir():
        return 0
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={days} days ago",
             "--oneline", "--", file],
            capture_output=True, text=True, timeout=20)
        return len([x for x in p.stdout.splitlines() if x.strip()]) if p.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError):
        return 0


def estimate(name: str, *, parent_map: dict, children_map: dict,
             repo: Path | None = None, file: str = "") -> Estimate:
    """한 클래스의 레이어. **구조 우선, git 은 강등만.**"""
    fan_in = len(children_map.get(name, []))
    desc = descendant_count(name, children_map)
    depth = internal_depth(name, parent_map)
    commits = count_commits(repo, file) if repo is not None else 0

    if desc >= 1 or fan_in >= 1:                       # 트렁크
        if depth == 0:
            layer, conf = 1, (0.8 if desc >= 3 else 0.65)
        else:
            layer, conf = 2, 0.7
    else:                                              # 리프
        layer, conf = 3, 0.8

    demoted = False
    if layer == 2 and commits >= GIT_VOLATILE:
        layer, conf, demoted = 3, 0.7, True

    return Estimate(name=name, layer=layer, confidence=round(conf, 3),
                    signals={"fan_in": fan_in, "descendants": desc, "depth": depth,
                             f"commits_{GIT_WINDOW_DAYS}d": commits, "git_demoted": demoted})


def estimate_domain(members: dict, *, files: dict | None = None,
                    locked: set | None = None, repo: Path | None = None) -> list:
    """도메인 멤버 전체. `members` 는 `{클래스: 부모}`.

    [중요] `locked`(= `verified_by_layer=1`)는 **추정하지 않는다.** 사용자가 검수해 잠근 값을
    자동 추정이 덮으면 검수의 의미가 사라진다 — 원본이 같은 규칙을 둔다.
    """
    parent_map, children_map = build_member_graph(members)
    files, locked = files or {}, locked or set()
    out = []
    for name in sorted(members):
        if name in locked:
            out.append(Estimate(name=name, layer=0, confidence=1.0, locked=True))
            continue
        out.append(estimate(name, parent_map=parent_map, children_map=children_map,
                            repo=repo, file=files.get(name, "")))
    return out


def distribution(estimates: list) -> dict:
    """L1/L2/L3 분포. [중요] **L3 가 0 이면 추정이 중앙으로 쏠린 것**이다 — 원본이 그 증상으로
    동등 투표 평균을 폐기했다. 분포를 보고할 수 있어야 그 재발을 안다."""
    d = {1: 0, 2: 0, 3: 0, "locked": 0}
    for e in estimates:
        if e.locked:
            d["locked"] += 1
        else:
            d[e.layer] = d.get(e.layer, 0) + 1
    return d
