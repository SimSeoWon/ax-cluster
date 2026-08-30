"""`gitea` 그룹 승격 판정 (`#336` ②).

[중요] **이 테스트가 잡는 것은 「감쌌나」가 아니라 「필요할 때만 감쌌나」다.** 종전에는
`twin_base`·`ontology/drift` 가 무조건 `sg gitea -c` 로 감쌌고, 서비스 유닛의
`NoNewPrivileges=true` 가 그것을 막아 **base 확인이 항상 실패**했다(실측 오류:
`setgid: 명령을 허용하지 않음`). 정작 서비스는 `User=sim` 이라 그 그룹을 이미 들고 있었다.

`python3 master/test_gitea_group.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import gitea_group as G                            # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_wrap() -> None:
    argv = ["git", "-C", "/a b", "status"]

    # [중요] 그룹이 이미 있으면 **그대로** — 이것이 이 변경의 전부다
    got = G.wrap(argv, force=False)
    check("[중요] 그룹이 있으면 감싸지 않는다", got == argv, str(got))

    got = G.wrap(argv, force=True)
    check("그룹이 없으면 sg 로 감싼다", got[:3] == ["sg", "gitea", "-c"], str(got))
    check("[중요] 공백 있는 경로를 인용한다 — 안 하면 인자가 쪼개진다",
          "'/a b'" in got[3], got[3])

    # 원본을 훼손하지 않는다 (호출부가 같은 리스트를 재사용한다)
    check("입력 argv 를 바꾸지 않는다", argv == ["git", "-C", "/a b", "status"], str(argv))


def test_wrap_shell() -> None:
    cmd = "git ls-remote --heads /var/lib/gitea/x.git"

    got = G.wrap_shell(cmd, force=True)
    check("문자열 명령도 감싼다", got == ["sg", "gitea", "-c", cmd], str(got))

    got = G.wrap_shell(cmd, force=False)
    check("[중요] 안 감쌀 때는 셸을 안 태운다 — argv 로 쪼갠다",
          got == ["git", "ls-remote", "--heads", "/var/lib/gitea/x.git"], str(got))

    # [주의] 두 갈래의 파싱 규칙이 같아야 한다 — 인용된 경로가 한 인자로 남는지
    q = "git ls-remote --heads '/a b/x.git'"
    got = G.wrap_shell(q, force=False)
    check("[주의] 인용된 경로가 한 인자로 남는다", got[-1] == "/a b/x.git", str(got))


def test_has_group() -> None:
    # 없는 그룹은 False — 예외로 죽지 않는다 (KeyError 를 삼킨다)
    check("[중요] 모르는 그룹이면 False (죽지 않는다)",
          G.has_group("존재하지않는그룹_ax336") is False)
    check("판정이 bool 이다", isinstance(G.has_group(), bool))


def test_call_sites_use_the_one_judgement() -> None:
    """[중요] **판정이 한 곳인지**를 소스로 잰다 — 두 벌이면 조용히 어긋난다."""
    import ast
    root = Path(__file__).resolve().parent
    offenders = []
    for rel in ("work/twin_base.py", "ontology/drift.py", "events/consumer.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        # [중요] **파서로 찾는다** — 문서·주석의 `sg` 언급을 세지 않는다. `#321` 이 치른
        #    값과 같은 이유다: 「모양이 바뀌는 변경은 파서로 찾는다」.
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts:
                continue
            first = node.elts[0]
            if isinstance(first, ast.Constant) and first.value == "sg":
                offenders.append(f"{rel}:{node.lineno}")
    check("[중요] 호출부가 sg 를 직접 박지 않는다 (판정은 gitea_group 하나)",
          not offenders, " | ".join(offenders))


def main() -> int:
    for fn in (test_wrap, test_wrap_shell, test_has_group,
               test_call_sites_use_the_one_judgement):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_gitea_group: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
