"""systemd 샌드박스 (`#276`) — **큐가 쓰는 트윈 경로가 유닛에 허용돼 있는가**.

## 왜 이 테스트가 있나 (실측 2026-08-22)

`ax-task-queue.service` 는 `ReadWritePaths` 에 **프로젝트 이름이 박혀** 있었다:

    ReadWritePaths=/home/sim/ax-cluster/ModularStage/recipes
    ReadWritePaths=/home/sim/ax-cluster/ModularStage/history

결과 둘. ⓐ 표면을 늘릴 때마다 손으로 경로를 추가해야 했고 — 그래서 `ontology/` 가 빠져
**시소러스 대행이 처음부터 500 이었다**(비마운트 방어가 아니라, 마운트된 프로젝트조차 실패했다.
그리고 나는 그 500 을 「우리 코드가 막았다」고 잘못 읽었다). ⓑ 새 프로젝트(NS)는 애초에
불가능했다 — 유닛에 이름이 없으니까.

[중요] **그래서 코드가 아니라 유닛을 읽는다.** 이 부류의 결함은 파이썬 어디에도 없다.

`.venv/bin/python master/test_sandbox.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
UNIT = ROOT / "master" / "systemd" / "ax-task-queue.service"

# [중요] 큐가 트윈에 쓰는 곳 — **`<트윈>/` 아래 상대 경로**. 표면을 늘리면 여기에 넣는다.
#    출처: `#206`(신호) · `#207`(작업 기록) · `#243`(시소러스 대행).
TWIN_WRITES = ("recipes", "history", "ontology")

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _directives(text: str, key: str) -> list:
    """주석이 아닌 지시문만. [주의] 주석에 든 낡은 예시를 설정으로 세면 안 된다."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or not s.startswith(key + "="):
            continue
        v = s.split("=", 1)[1].strip()
        out.append(v.lstrip("-"))       # `-` 접두사 = 없으면 무시 (systemd 문법)
    return out


def test_no_project_name_in_directives() -> None:
    """[중요] **유닛에 프로젝트 이름이 없어야 한다** (`#276` 완료 조건 2)."""
    text = UNIT.read_text(encoding="utf-8")
    projects = [d.name for d in ROOT.iterdir()
                if d.is_dir() and (d / "config.yaml").exists()]
    check("트윈을 찾았다", len(projects) >= 1, str(projects))
    bad = []
    for key in ("ReadWritePaths", "ReadOnlyPaths", "Environment", "ExecStart"):
        for value in _directives(text, key):
            for p in projects:
                if re.search(rf"(^|[/=]){re.escape(p)}(/|$|\s)", value):
                    bad.append(f"{key}={value}")
    check("[중요] 지시문에 프로젝트 이름이 박혀 있지 않다", not bad, str(bad))
    # 주석에는 있어도 된다 — 왜 그렇게 바뀌었는지의 기록이다
    check("경위가 주석에 남아 있다", "#276" in text)


def test_twin_writes_are_allowed() -> None:
    """[중요] 큐가 쓰는 트윈 경로가 **허용 안에** 있고, 읽기 전용에 **가려지지 않는다**."""
    text = UNIT.read_text(encoding="utf-8")
    rw = [Path(v) for v in _directives(text, "ReadWritePaths")]
    ro = [Path(v) for v in _directives(text, "ReadOnlyPaths")]
    check("쓰기 허용이 선언돼 있다", bool(rw), str(rw))

    projects = [d.name for d in ROOT.iterdir()
                if d.is_dir() and (d / "config.yaml").exists()]
    for proj in projects:
        for sub in TWIN_WRITES:
            target = ROOT / proj / sub
            allowed = any(target == r or r in target.parents for r in rw)
            check(f"{proj}/{sub} 가 쓰기 허용 안에 있다", allowed,
                  f"{target} ∉ {rw}")
            # [중요] 더 구체적인 ReadOnlyPaths 가 덮으면 쓰기는 실패한다 — 그것도 잡는다
            shadowed = [r for r in ro if target == r or r in target.parents]
            check(f"{proj}/{sub} 가 읽기 전용에 가려지지 않는다", not shadowed,
                  str(shadowed))


def test_code_stays_read_only() -> None:
    """[중요] `#206` 의 의도(*"큐가 저장소 코드를 쓸 수 있게 되면 안 된다"*)가 살아 있다.

    루트를 열었으므로 **코드·문서·git 은 되돌려야** 한다 — 안 하면 `#206` 을 잃는다.
    """
    text = UNIT.read_text(encoding="utf-8")
    ro = {Path(v) for v in _directives(text, "ReadOnlyPaths")}
    for must in ("master", "client", "docs", ".git", "reports"):
        check(f"{must} 는 읽기 전용이다", (ROOT / must) in ro, str(sorted(map(str, ro)))[:120])
    check("레지스트리도 읽기 전용이다 (등재는 ax-projects 의 몫이다)",
          (ROOT / "projects.yaml") in ro)


def test_every_non_twin_toplevel_is_covered() -> None:
    """[주의] **트윈이 아닌 최상위 항목이 새로 생기면 여기서 잡는다** — 루트를 열었기 때문에
    목록에 없는 항목은 조용히 쓰기 가능이 된다. 새 항목은 트윈이거나 읽기 전용이어야 한다.
    """
    text = UNIT.read_text(encoding="utf-8")
    ro = {Path(v) for v in _directives(text, "ReadOnlyPaths")}
    uncovered = []
    for e in sorted(ROOT.iterdir()):
        if e.name.startswith(".") and e.name != ".git":
            continue                                    # 숨김 항목은 별 축 (.venv 등)
        if e.is_dir() and (e / "config.yaml").exists():
            continue                                    # 트윈 — 쓰기가 정상이다
        if e in ro:
            continue
        uncovered.append(e.name)
    check("[주의] 트윈이 아닌 최상위 항목이 전부 읽기 전용 목록에 있다", not uncovered,
          f"{uncovered} — 트윈이면 무시, 아니면 ReadOnlyPaths 에 넣을 것")


def test_repo_copy_matches_live() -> None:
    """[중요] **저장소 사본과 실물이 같은가** — 실측 2026-08-22 에 실물에만 3줄 더 있었다.

    유닛을 손으로 고치면 다음 배포가 그것을 되돌린다. 그렇게 `AX_PROJECTS_ROOT` 가
    사본에서 빠져 있었다.
    """
    live = Path("/etc/systemd/system/ax-task-queue.service")
    if not live.exists():
        check("실물 유닛이 없다 — 이 기계가 마스터가 아니다 (건너뜀)", True)
        return
    a = [l for l in UNIT.read_text(encoding="utf-8").splitlines() if l.strip()]
    b = [l for l in live.read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.startswith("# /etc/systemd")]
    check("[중요] 저장소 사본 == 실물", a == b,
          f"차이 {len(set(a) ^ set(b))}줄 — `master/systemd/` 를 고치고 그것으로 설치할 것")


if __name__ == "__main__":
    for fn in (test_no_project_name_in_directives, test_twin_writes_are_allowed,
               test_code_stays_read_only, test_every_non_twin_toplevel_is_covered,
               test_repo_copy_matches_live):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_sandbox: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
