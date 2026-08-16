"""개명 cascade(`#167`) 계약 테스트 — [중요] **한 곳만 고치고 끝나지 않는가.**

개명의 위험은 실패가 **조용한** 것이다: 디렉토리는 새 이름인데 다른 도메인이 옛 이름을
가리키면 링크가 죽고 검색이 빗나가는데 아무도 오류를 보지 않는다. 그래서 재는 것 넷:

    ① cascade    다른 도메인의 참조까지 따라가는가
    ② 경계       부분 일치로 **다른 이름을 삼키지** 않는가 (실측된 오보고가 근거)
    ③ 안 하는 것 DB 를 건드리지 않는가 (우리 SSOT 는 YAML)
    ④ 안전      기본이 계획인가 · 충돌을 미리 막는가 · 잠금이 따라가는가

실행: .venv/bin/python master/test_rename.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import rename as R      # noqa: E402
from master.ontology import yaml_io          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.ontology = root / "ontology"
        self.context = root / "context"


def fixture():
    root = Path(tempfile.mkdtemp(prefix="ax-rename-"))
    p = P(root)
    for d, extra in (("MissionRuntime", ["MissionEditor"]), ("MissionEditor", ["MissionRuntime"]),
                     ("Other", [])):
        pkg = p.ontology / "domains" / d
        (pkg / "L1" / "objects").mkdir(parents=True)
        yaml_io.write(pkg / "domain.yaml",
                      {"domain": d, "tier": 3, "related": extra,
                       "members": ["MissionTask", "MissionTaskDetailBase"]})
        yaml_io.write(pkg / "L1" / "objects" / "MissionTask.yaml",
                      {"name": "MissionTask", "verified_by_user": True,
                       "note": "MissionTask 는 MissionTaskDetailBase 와 다르다"})
        md = p.context / "_domains"
        md.mkdir(parents=True, exist_ok=True)
        (md / f"{d}.md").write_text(
            f"---\nparent_domain: {'MissionRuntime' if d == 'MissionEditor' else ''}\n---\n"
            f"# {d}\n\n## 협력 도메인\n" + "".join(f"- {e}\n" for e in extra),
            encoding="utf-8")
    return root, p


# ── ① cascade ─────────────────────────────────────────────────

def test_domain_rename_follows_references():
    root, p = fixture()
    plan = R.plan_domain(p, "MissionRuntime", "MissionCore")
    check("계획이 성립한다", plan.ok, plan.error)
    check("패키지 디렉토리를 옮긴다",
          any(s.endswith("domains/MissionRuntime") for s, _ in plan.moves), str(plan.moves))
    check("사람 편집 MD 도 옮긴다",
          any(s.endswith("_domains/MissionRuntime.md") for s, _ in plan.moves), str(plan.moves))
    check("manifest 의 domain 값을 고친다",
          any("manifest" in w for _, w in plan.edits), str(plan.edits))
    check("[중요] **다른 도메인의 참조**를 따라간다",
          any("MissionEditor/domain.yaml" in s for s, _ in plan.edits), str(plan.edits))
    check("[중요] 다른 도메인의 MD(parent_domain·협력)도 잡는다",
          any(s.endswith("_domains/MissionEditor.md") for s, _ in plan.edits), str(plan.edits))
    check("무관한 도메인은 안 건드린다",
          not any("Other" in s for s, _ in plan.edits), str(plan.edits))
    check("[중요] 계획 단계에서는 아무것도 안 바뀐다",
          (p.ontology / "domains" / "MissionRuntime").is_dir() and not plan.applied)

    R.apply_domain(p, plan)
    check("적용되면 디렉토리가 새 이름", (p.ontology / "domains" / "MissionCore").is_dir())
    check("옛 디렉토리는 사라진다", not (p.ontology / "domains" / "MissionRuntime").exists())
    man = yaml_io.read(p.ontology / "domains" / "MissionCore" / "domain.yaml")
    check("manifest 의 domain 값이 바뀐다", man["domain"] == "MissionCore", str(man)[:80])
    other = yaml_io.read(p.ontology / "domains" / "MissionEditor" / "domain.yaml")
    check("[중요] 다른 도메인의 참조가 새 이름을 가리킨다",
          other["related"] == ["MissionCore"], str(other))
    md = (p.context / "_domains" / "MissionEditor.md").read_text(encoding="utf-8")
    check("[중요] parent_domain 도 따라간다", "parent_domain: MissionCore" in md, md[:80])
    check("사람 편집 MD 가 새 이름으로", (p.context / "_domains" / "MissionCore.md").is_file())


# ── ② 경계 — 부분 일치로 다른 이름을 삼키지 않는다 ────────────

def test_boundary_does_not_swallow_longer_names():
    """[중요] 실측된 오보고가 근거다 — 부분 일치가 현존 클래스를 「옛이름」으로 잡았다."""
    root, p = fixture()
    plan = R.plan_class(p, "MissionRuntime", "MissionTask", "Quest")
    check("계획이 성립한다", plan.ok, plan.error)
    R.apply_class(p, plan)
    obj = p.ontology / "domains" / "MissionRuntime" / "L1" / "objects"
    check("파일명이 바뀐다", (obj / "Quest.yaml").is_file() and not (obj / "MissionTask.yaml").exists())
    data = yaml_io.read(obj / "Quest.yaml")
    check("이름 필드가 바뀐다", data["name"] == "Quest", str(data))
    check("[중요] **더 긴 이름은 안 삼킨다** — MissionTaskDetailBase 는 그대로",
          "MissionTaskDetailBase" in data["note"], data["note"])
    man = yaml_io.read(p.ontology / "domains" / "MissionRuntime" / "domain.yaml")
    check("멤버 목록에서 정확히 그 항목만 바뀐다",
          man["members"] == ["Quest", "MissionTaskDetailBase"], str(man["members"]))
    check("[중요] 잠금이 따라온다 (이동이지 재생성이 아니다)", data.get("verified_by_user") is True)


# ── ③ 안 하는 것 — DB ─────────────────────────────────────────

def test_db_is_not_touched():
    """[중요] 우리 SSOT 는 YAML 이다. 원전의 DB 쓰기를 옮기면 드리프트가 되살아난다."""
    import ast
    src = Path(R.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[-1] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported |= {a.name for a in n.names}
            if n.module:
                imported.add(n.module.split(".")[-1])
    check("[중요] sqlite 를 import 하지 않는다", "sqlite3" not in imported, str(sorted(imported)))
    check("안 옮긴 이유를 모듈이 적어 둔다", "DB↔YAML" in src or "드리프트" in src)
    root, p = fixture()
    check("계획이 그 사실을 사람에게도 말한다",
          any("DB" in n for n in R.plan_domain(p, "MissionRuntime", "X").notes))


# ── ④ 안전 ────────────────────────────────────────────────────

def test_guards():
    root, p = fixture()
    check("비ASCII 새 이름 거부", not R.plan_domain(p, "MissionRuntime", "미션").ok)
    check("빈 이름 거부", not R.plan_domain(p, "MissionRuntime", "  ").ok)
    check("old == new 거부", not R.plan_domain(p, "MissionRuntime", "MissionRuntime").ok)
    check("없는 도메인 거부", not R.plan_domain(p, "없음", "X").ok)
    conflict = R.plan_domain(p, "MissionRuntime", "MissionEditor")
    check("[중요] 새 이름이 이미 있으면 **미리** 막는다", not conflict.ok and "충돌" in conflict.error,
          conflict.error)
    check("적용 안 된 계획은 실행해도 아무것도 안 한다",
          R.apply_domain(p, conflict).applied is False)
    check("공백은 안전 문자로", R.safe_name("Mission Core") == "Mission_Core")
    check("없는 클래스는 거부", not R.plan_class(p, "MissionRuntime", "없는것", "X").ok)
    check("계획에 백업 경고가 있다 (트윈은 git 밖이다)",
          any("백업" in n for n in R.plan_domain(p, "MissionRuntime", "X").notes))
    check("요약이 계획/적용을 구분한다",
          "계획만" in R.plan_domain(p, "MissionRuntime", "X").summary())


def main() -> int:
    for fn in (test_domain_rename_follows_references, test_boundary_does_not_swallow_longer_names,
               test_db_is_not_touched, test_guards):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_rename: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
