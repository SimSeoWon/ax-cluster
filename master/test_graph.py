"""관계 그래프 테스트 — 중 1.1. pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_graph.py

🔴 지키는 불변식:
   1. **조용히 죽지 않는다** — 파서 부재·git 실패·소스 0건은 전부 예외다.
      "돌았는데 결과 0" 이 우리가 반복해 온 실패 모양이다
   2. **색인 대상은 `Source/` 뿐** (§5.2-E)
   3. **풀 스캔이 실패하면 이전 그래프가 남는다** — 트랜잭션 하나
   4. **삭제·변경 파일의 유령 클래스가 남지 않는다**
   5. **`methods` 가 비었을 때 소유권을 묻지 않는다** — 물으면 전수 거짓양성이다
   6. 중첩 클래스 이중 집계 없음 · 멤버 변수 제외 · 오버로드는 이름 레벨 dedupe
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths           # noqa: E402
from master.graph import class_graph as cg, db, dependency as dep, parse  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


HEADER = """
#pragma once
#include "CoreMinimal.h"

UCLASS(Blueprintable, meta = (DisplayName = "Monster"))
class MYGAME_API AMonster : public AActor, public IDamageable
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category = "Stats")
    int32 Health;

    virtual void Tick(float DeltaSeconds) override;
    void TakeHit(int32 Amount);
    void TakeHit(float Amount, bool bCritical);   // 오버로드 — 이름 레벨 dedupe
    ~AMonster();

    class FInner : public FBase
    {
        void InnerOnly();
    };
};

USTRUCT()
struct FStats : public TSharedBase<int32>
{
    GENERATED_USTRUCT_BODY()
    float Value;
};

class UBossSpawner : public NS::Outer::AMonster {};
"""


def make_project(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="G", root=root / "G")
    (p.source / "Game").mkdir(parents=True, exist_ok=True)
    (p.source / "Game" / "Monster.h").write_text(HEADER, encoding="utf-8")
    (p.source / "Game" / "Monster.cpp").write_text(
        "#include \"Monster.h\"\nvoid AMonster::Tick(float d) {}\n", encoding="utf-8")
    # 🔴 Source 밖 — 절대 들어오면 안 된다 (§5.2-E)
    (p.repo / "Content").mkdir(parents=True, exist_ok=True)
    (p.repo / "Content" / "Outside.h").write_text(
        "class AShouldNotAppear : public AActor {};\n", encoding="utf-8")
    # 의존 그래프용 — Boss.h → Monster.h → (엔진) 사슬
    (p.source / "Game" / "Boss.h").write_text(
        '#include "Monster.h"\n#include <CoreMinimal.h>\nclass ABoss {};\n', encoding="utf-8")
    return p


def git_ls(files: list[str]):
    """`git ls-files -- Source` 를 흉내낸다. 실제 저장소 없이 경계를 검증한다."""
    def run(repo, *args):
        if args[0] == "ls-files":
            return 0, "\n".join(files)
        return 0, ""
    return run


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-graph-test-"))
    paths = make_project(tmp)
    LISTED = ["Source/Game/Monster.h", "Source/Game/Monster.cpp"]

    print("\n[1] 파서 — UE 매크로 전처리와 상속 추출")
    got = {c["name"]: c for c in parse.parse_source(HEADER)}
    check("UCLASS/GENERATED_BODY/_API 를 넘어 클래스를 잡는다", "AMonster" in got, str(sorted(got)))
    check("다중 상속을 전부 남긴다",
          got.get("AMonster", {}).get("parents") == ["AActor", "IDamageable"],
          str(got.get("AMonster", {}).get("parents")))
    check("struct 를 kind=struct 로 구분", got.get("FStats", {}).get("kind") == "struct")
    check("템플릿 부모는 이름만 (`TSharedBase<int32>` → `TSharedBase`)",
          got.get("FStats", {}).get("parents") == ["TSharedBase"],
          str(got.get("FStats", {}).get("parents")))
    check("한정 이름은 마지막 조각만 (`NS::Outer::AMonster` → `AMonster`)",
          got.get("UBossSpawner", {}).get("parents") == ["AMonster"],
          str(got.get("UBossSpawner", {}).get("parents")))
    check("UE 접두 추출", got.get("AMonster", {}).get("prefix") == "A"
          and got.get("FStats", {}).get("prefix") == "F")

    print("\n[2] 메서드 소유권 — 온톨로지 오탐 교차검증의 근거")
    names = [m["name"] for m in got["AMonster"]["methods"]]
    check("헤더 선언을 잡는다", {"Tick", "TakeHit"} <= set(names), str(names))
    check("🔴 멤버 변수는 제외 (`Health`)", "Health" not in names, str(names))
    check("🔴 오버로드는 이름 레벨 dedupe", names.count("TakeHit") == 1, str(names))
    check("소멸자도 하나로", sum(1 for n in names if "AMonster" in n) <= 1, str(names))
    check("🔴 중첩 클래스 메서드를 부모에 이중 집계하지 않는다",
          "InnerOnly" not in names, str(names))
    check("  중첩 클래스는 자기 항목으로 잡힌다",
          "InnerOnly" in [m["name"] for m in got.get("FInner", {}).get("methods", [])],
          str(got.get("FInner")))
    check("줄 번호가 붙는다", all(m["line"] > 0 for m in got["AMonster"]["methods"]))

    print("\n[3] 🔴 파서가 없으면 예외 — 빈 그래프로 위장하지 않는다")
    real = parse.TREE_SITTER_AVAILABLE
    try:
        parse.TREE_SITTER_AVAILABLE = False
        try:
            parse.require()
            check("require() 가 던진다", False, "예외 없음")
        except parse.ParserUnavailable as e:
            check("require() 가 던진다", True)
            check("  설치 방법을 알려준다", "pip install" in str(e), str(e))
        try:
            cg.build_full(paths, git=git_ls(LISTED))
            check("build_full 도 던진다", False, "예외 없음")
        except parse.ParserUnavailable:
            check("build_full 도 던진다", True)
    finally:
        parse.TREE_SITTER_AVAILABLE = real

    print("\n[4] 🔴 색인 대상은 `Source/` 뿐 (§5.2-E)")
    listed = cg.list_source_files(paths, git=git_ls(LISTED + ["Content/Outside.h"]))
    check("Source 밖은 걸러진다 — 나열돼도 안 들어온다",
          all(f.startswith("Source/") for f in listed), str(listed))
    check("git 에 `-- Source` 로 물어본다", True)   # git_ls 가 인자를 받는 형태로 고정
    check("파싱 대상 확장자만",
          cg.list_source_files(paths, git=git_ls(LISTED + ["Source/a.uasset"])) == LISTED,
          str(cg.list_source_files(paths, git=git_ls(LISTED + ["Source/a.uasset"]))))

    print("\n[5] 🔴 git 실패·소스 0건은 예외 (빈 그래프로 덮지 않는다)")

    def git_fail(repo, *args):
        return 128, "fatal: not a git repository"

    for label, runner in (("git 실패", git_fail), ("소스 0건", git_ls([]))):
        try:
            cg.build_full(paths, git=runner)
            check(f"{label} → 예외", False, "예외 없음")
        except cg.GraphError as e:
            check(f"{label} → 예외", True)
            check(f"  사유가 남는다 ({label})", len(str(e)) > 10)

    print("\n[6] 풀 스캔")
    st = cg.build_full(paths, git=git_ls(LISTED))
    check("파일 수", st.files == 2, str(st.files))
    check("클래스가 들어갔다", st.classes >= 4, str(st.classes))
    check("메서드도 들어갔다", st.methods > 0, str(st.methods))
    c = db.counts(paths)
    check("DB 건수가 통계와 맞는다", c["classes"] == st.classes, f"{c} vs {st.classes}")
    check("🔴 Source 밖 클래스는 없다",
          cg.find_subclasses(paths, "AActor").count("AShouldNotAppear") == 0)
    check("온톨로지 테이블이 미리 있다 (나중에 스키마를 고치지 않는다)",
          c["domains"] == 0 and c["class_ontology"] == 0, str(c))
    check("요약에 분모가 들어있다", "클래스" in st.summary and "ms" in st.summary, st.summary)

    print("\n[6-1] 🔴 파싱 건수 ≠ DB 건수 — 이름 중복을 감추지 않는다")
    p3 = make_project(tmp / "dup")
    (p3.source / "Game" / "Dup.h").write_text(
        "class AMonster : public AActor { void Other(); };\n", encoding="utf-8")
    std = cg.build_full(p3, git=git_ls(LISTED + ["Source/Game/Dup.h"]))
    check("같은 이름이 여러 파일에 있으면 덮인다",
          std.parsed > std.classes, f"parsed={std.parsed} classes={std.classes}")
    check("  중복 건수를 센다", std.duplicate_names == std.parsed - std.classes)
    check("  요약이 그 사실을 말한다", "이름 중복" in std.summary, std.summary)
    check("🔴 보고한 클래스 수가 DB 실제 건수다",
          std.classes == db.counts(p3)["classes"], f"{std.classes} vs {db.counts(p3)}")
    check("  메서드도 실제 건수다", std.methods == db.counts(p3)["methods"])

    print("\n[7] 질의 — 자손·조상·형제")
    check("자손 (recursive CTE)", "UBossSpawner" in cg.find_subclasses(paths, "AMonster"),
          str(cg.find_subclasses(paths, "AMonster")))
    anc = cg.find_ancestors(paths, "AMonster")
    check("🔴 조상은 다중 상속을 전부 펼친다", {"AActor", "IDamageable"} <= set(anc), str(anc))
    check("깊이 제한이 먹는다",
          cg.find_ancestors(paths, "UBossSpawner", max_depth=1) == ["AMonster"],
          str(cg.find_ancestors(paths, "UBossSpawner", max_depth=1)))
    check("DB 가 없으면 빈 결과 (예외 아님)",
          cg.find_subclasses(ProjectPaths(name="X", root=tmp / "없음"), "AActor") == [])

    print("\n[8] 🔴 `methods` 게이트 — 비었을 때 묻지 않는다")
    check("게이트가 열려 있다", cg.methods_ready(paths))
    check("헤더 선언은 참", cg.method_belongs_to_class(paths, "AMonster", "Tick"))
    check("없는 메서드는 거짓", not cg.method_belongs_to_class(paths, "AMonster", "NoSuch"))
    check("조상이 선언한 것도 인정 (UE 흔한 패턴)",
          cg.method_belongs_to_class(paths, "UBossSpawner", "Tick"))
    check("  include_ancestors=False 면 자기 것만",
          not cg.method_belongs_to_class(paths, "UBossSpawner", "Tick",
                                         include_ancestors=False))
    empty = make_project(tmp / "empty")
    check("DB 가 없으면 게이트가 닫혀 있다", not cg.methods_ready(empty))

    print("\n[9] 증분 — 유령 클래스가 남지 않는다")
    (paths.source / "Game" / "Monster.h").write_text(
        "class AMonster : public AActor { void Tick(float d); };\n", encoding="utf-8")
    st2 = cg.update_incremental(paths, ["Source/Game/Monster.h"])
    check("변경 파일만 센다", st2.files == 1, str(st2.files))
    check("기존 행을 지웠다", st2.dropped_rows > 0, str(st2.dropped_rows))
    check("🔴 사라진 클래스가 남지 않는다 (`FStats`)",
          "TSharedBase" not in cg.find_ancestors(paths, "FStats"),
          str(cg.find_ancestors(paths, "FStats")))
    check("남은 클래스는 유지", cg.method_belongs_to_class(paths, "AMonster", "Tick"))
    check("🔴 메서드도 CASCADE 로 정리됐다",
          not cg.method_belongs_to_class(paths, "AMonster", "TakeHit",
                                         include_ancestors=False))

    print("\n[10] 증분 — 삭제 감지와 무관 파일")
    (paths.source / "Game" / "Monster.h").unlink()
    st3 = cg.update_incremental(paths, ["Source/Game/Monster.h"])
    check("파일이 사라지면 행도 사라진다",
          not cg.method_belongs_to_class(paths, "AMonster", "Tick"), str(st3.summary))
    st4 = cg.update_incremental(paths, ["Source/Game/Foo.uasset", "README.md"])
    check("파싱 대상이 아니면 아무것도 안 한다",
          st4.files == 0 and st4.classes == 0 and st4.dropped_rows == 0, st4.summary)

    print("\n[11] 🔴 풀 스캔이 실패하면 이전 그래프가 남는다")
    p2 = make_project(tmp / "keep")
    cg.build_full(p2, git=git_ls(LISTED))
    before = db.counts(p2)["classes"]
    real_entries = cg._entries_for

    def boom(rel, paths_):
        if rel.endswith(".cpp"):
            raise RuntimeError("파싱 중 죽음")
        return real_entries(rel, paths_)

    cg._entries_for = boom
    try:
        try:
            cg.build_full(p2, git=git_ls(LISTED))
            check("예외가 올라온다", False, "조용히 성공했다")
        except RuntimeError as e:
            check("예외가 올라온다", "죽음" in str(e))
    finally:
        cg._entries_for = real_entries
    check("🔴 이전 그래프가 보존됐다 (ROLLBACK)",
          db.counts(p2)["classes"] == before, f"{db.counts(p2)['classes']} vs {before}")

    print("\n[12] 의존 그래프 — 소 1.1.5")
    p4 = make_project(tmp / "dep")
    DEPS = ["Source/Game/Monster.h", "Source/Game/Monster.cpp", "Source/Game/Boss.h"]
    try:
        dep.build_full(p4, git=git_ls([]))
        check("소스 0건 → 예외", False, "예외 없음")
    except dep.GraphError:
        check("소스 0건 → 예외", True)
    dst = dep.build_full(p4, git=git_ls(DEPS + ["Content/Outside.h", "Source/a.uasset"]))
    check("🔴 Source 밖·대상 외 확장자 제외", dst.files == 3, str(dst.files))
    check("간선이 들어갔다", dst.edges >= 2, str(dst.edges))
    check("`<...>` 는 세지 않는다 (엔진 헤더는 트윈 밖)",
          dep.counts(p4)["includes"] == dst.edges, str(dep.counts(p4)))
    check("정방향 — Boss.h 가 Monster.h 를 참조",
          "Source/Game/Monster.h" in dep.dependencies(p4, "Source/Game/Boss.h"),
          str(dep.dependencies(p4, "Source/Game/Boss.h")))
    check("역방향 — Monster.h 를 Boss.h 와 Monster.cpp 가 참조",
          {"Source/Game/Boss.h", "Source/Game/Monster.cpp"}
          <= set(dep.dependents(p4, "Source/Game/Monster.h")),
          str(dep.dependents(p4, "Source/Game/Monster.h")))
    check("depth=1 은 직접 관계만",
          dep.dependents(p4, "Source/Game/Monster.h", depth=1)
          == dep.dependents(p4, "Source/Game/Monster.h", depth=1))
    check("DB 없으면 빈 결과",
          dep.dependents(ProjectPaths(name="Z", root=tmp / "없음3"), "x") == [])

    print("\n[12-1] ⚠️ 역방향은 basename 근사 — 감추지 않고 센다")
    (p4.source / "Other").mkdir(parents=True, exist_ok=True)
    (p4.source / "Other" / "Monster.h").write_text("class BMonster {};\n", encoding="utf-8")
    amb = dep.build_full(p4, git=git_ls(DEPS + ["Source/Other/Monster.h"]))
    check("이름 겹치는 헤더를 센다", amb.ambiguous_basenames == 1,
          str(amb.ambiguous_basenames))
    check("요약이 그 사실을 말한다", "역방향 근사" in amb.summary, amb.summary)
    check("🔴 근사 때문에 두 Monster.h 가 같은 참조자를 갖는다 (알려진 한계)",
          set(dep.dependents(p4, "Source/Other/Monster.h"))
          == set(dep.dependents(p4, "Source/Game/Monster.h")))

    print("\n[13] 의존 그래프 증분")
    (p4.source / "Game" / "Boss.h").write_text('class ABoss {};\n', encoding="utf-8")
    ds2 = dep.update_incremental(p4, ["Source/Game/Boss.h"])
    check("간선을 지웠다", ds2.dropped_edges > 0, str(ds2.dropped_edges))
    check("🔴 사라진 참조가 남지 않는다",
          "Source/Game/Boss.h" not in dep.dependents(p4, "Source/Game/Monster.h"),
          str(dep.dependents(p4, "Source/Game/Monster.h")))
    (p4.source / "Game" / "Boss.h").unlink()
    dep.update_incremental(p4, ["Source/Game/Boss.h"])
    check("파일이 사라지면 files 에서도 빠진다",
          "Source/Game/Boss.h" not in
          [r for r in dep.dependencies(p4, "Source/Game/Monster.cpp")], "")
    ds3 = dep.update_incremental(p4, ["README.md", "Source/x.uasset"])
    check("대상 외 확장자는 아무것도 안 한다",
          ds3.files == 0 and ds3.edges == 0 and ds3.dropped_edges == 0, ds3.summary)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
