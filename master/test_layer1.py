"""층1 — 결정적 자기검증 (중 2.1).

[중요] 지키는 계약은 넷이다:

    ① **휘발 태그는 잡고 보존 태그는 건드리지 않는다** — 태그가 두 종류라는 게 실제 계약이다
    ② [중요] **`[FEEDBACK]` 이 소스에 남으면 위반** — 원전에서 검증이 무한 실패한 그 자리다
    ③ **동결은 추가 허용 · 변경/삭제 위반 · 본문 채움 통과**
    ④ [중요] **fail-closed** — 안 돌린 것도, 기준 원본이 없는 것도 통과가 아니다

`.venv/bin/python master/test_layer1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import infer as INF        # noqa: E402
from master.work import layer1 as L1        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


HDR = """#pragma once
UCLASS()
class MODULARSTAGE_API UFoo : public UObject
{
\tGENERATED_BODY()
public:
\tvirtual void SetData(const FMissionTaskInfo& InTaskInfo) override;
\tint32 GetStep() const;
};
"""
H, C = "Source/A/Foo.h", "Source/A/Foo.cpp"


# ── ① 휘발 태그 vs 보존 태그 ────────────────────────────────────────────────────

def test_volatile_tags_are_caught() -> None:
    for tag in ("[PSEUDO]", "[PSEUDO:2]", "[IMPL]"):
        r = L1.check({C: f"void UFoo::F()\n{{\n\t// {tag} 나중에 채운다\n}}\n"})
        check(f"{tag} 를 잡는다", not r.ok, r.summary)
        check(f"{tag} 를 사유에 적는다", any(tag.split(':')[0] in p for p in r.problems),
              str(r.problems))


def test_permanent_tags_and_plain_comments_pass() -> None:
    """[중요] `[DOC]`·`[STATE]`·`[BIND]`·`[REPLICATED]` 와 무태그 주석은 **남아 있어야 정상**이다."""
    body = ("// [DOC] 무엇을 하는가\n// [STATE] 상태 설명\n// [BIND] 바인딩\n"
            "// [REPLICATED] 복제됨\n// 그냥 주석\nvoid UFoo::F() {}\n")
    r = L1.check({C: body})
    check("보존 태그는 통과", r.ok, r.summary)


def test_feedback_left_in_source_is_a_violation() -> None:
    """[중요] 원전: *"모든 주석 보존"* 지시가 `[FEEDBACK]` 삭제를 막아 **검증이 무한 실패**했다."""
    r = L1.check({C: "// [FEEDBACK] 빌드가 깨졌다\nvoid UFoo::F() {}\n"})
    check("[FEEDBACK] 잔재는 위반", not r.ok, r.summary)
    check("사유가 FEEDBACK 을 지목", any("FEEDBACK" in p for p in r.problems), str(r.problems))


def test_retry_feedback_block_residue_is_a_violation() -> None:
    """`#806` — 재시도 피드백 블록(C·`#` 둘 다)이 남으면 위반. 문장 중간의 인용은 아니다."""
    from master.work import revise as RV
    r = L1.check({C: RV.build_block(["x"], 2, C) + "\n\nvoid UFoo::F() {}\n"})
    check("C 피드백 블록 잔재는 위반", not r.ok, r.summary)
    check("  사유가 AUTO-VERIFY FEEDBACK 을 지목",
          any("AUTO-VERIFY FEEDBACK" in p for p in r.problems), str(r.problems))
    r = L1.check({"m.py": RV.build_block(["x"], 2, "m.py") + "\n\ndef f():\n    return 1\n"})
    check("`#` 피드백 블록 잔재는 위반 (구문은 멀쩡해도)", not r.ok
          and any("AUTO-VERIFY FEEDBACK" in p for p in r.problems)
          and not any("구문 오류" in p for p in r.problems), str(r.problems))
    r = L1.check({"m.py": "    # AUTO-VERIFY FEEDBACK 들여쓴 잔재\nx = 1\n"})
    check("들여쓴 `#` 여는 줄도 위반", not r.ok, r.summary)
    r = L1.check({"m.py": 'OPEN = "# AUTO-VERIFY FEEDBACK"\nC = "/* AUTO-VERIFY FEEDBACK"\n'})
    check("문자열 안 언급(줄 중간)은 통과", r.ok, r.summary)
    r = L1.check({C: '// 블록은 /* AUTO-VERIFY FEEDBACK 로 연다\nvoid UFoo::F() {}\n'})
    check("주석 문장 중간 인용은 통과", r.ok, r.summary)


def test_fence_residue_is_a_violation() -> None:
    r = L1.check({C: "```cpp\nvoid UFoo::F() {}\n```\n"})
    check("펜스 잔재는 위반", not r.ok, r.summary)



def test_fence_baseline_aware_819() -> None:
    print("\n🔴 펜스 잔재는 기준 원본의 개수만큼 기존이다 (`#819`)")
    p = "pkg/review_runner.py"
    F = "`" * 3
    base = ("import os\nimport sys\n\n"
            f'DRAFT_PROMPT = """답을 diff 로 낸다.\n{F}diff\n{{diff}}\n{F}"""\n\n\n'
            "def f():\n    return DRAFT_PROMPT\n")
    kept = base.replace("import os\nimport sys\n\n", "")
    r = L1.check({p: kept}, baseline=lambda _p: base)
    check("원본 펜스 2개를 그대로 두면 통과 (review_runner 사례)", r.ok, r.summary)

    more = kept + f'\nEXTRA = """\n{F}\n"""\n'
    r = L1.check({p: more}, baseline=lambda _p: base)
    fp = [x for x in r.problems if "펜스" in x]
    check("하나 더 생기면 막는다", not r.ok and len(fp) == 1, str(r.problems))
    check("  문구가 새로 생김·원본 개수를 싣는다",
          bool(fp) and "새로 생김 1" in fp[0] and "원본 2" in fp[0], str(fp))

    fewer = kept.replace(f"{F}diff\n", "").replace(f"{F}\"\"\"", '"""')
    r = L1.check({p: fewer}, baseline=lambda _p: base)
    check("펜스를 줄인 것은 펜스 문제가 아니다",
          not any("펜스" in x for x in r.problems), str(r.problems))

    r = L1.check({p: kept}, baseline=lambda _p: None)
    check("신규 파일(None)의 펜스는 종전대로 위반",
          any(x == f"{p}: 마크다운 펜스가 남아 있다" for x in r.problems), str(r.problems))
    r = L1.check({p: kept})
    check("baseline 함수가 없으면 종전대로 위반",
          any(x == f"{p}: 마크다운 펜스가 남아 있다" for x in r.problems), str(r.problems))

    plain = "def f():\n    raise NotImplementedError\n"
    wrapped = f"{F}python\ndef f():\n    return 1\n{F}\n"
    r = L1.check({p: wrapped}, baseline=lambda _p: plain)
    fp = [x for x in r.problems if "펜스" in x]
    check("🔴 답을 펜스로 감싼 응답(14b 결함)은 기준이 있어도 막는다",
          not r.ok and len(fp) == 1 and "새로 생김 2" in fp[0] and "원본 0" in fp[0], str(r.problems))
    r = L1.check({C: f"{F}cpp\nvoid UFoo::F() {{}}\n{F}\n"},
                 baseline=lambda _p: "void UFoo::F() {}\n")
    check("  .cpp 도 같은 규칙 (기준에 펜스 없음 → 위반)", not r.ok, r.summary)


# ── ③ 동결 ──────────────────────────────────────────────────────────────────────

def test_freeze_semantics() -> None:
    add = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const;\n\tvoid New();")
    chg = HDR.replace("SetData(const FMissionTaskInfo& InTaskInfo)",
                      "SetData(FMissionTaskInfo In)")
    dele = HDR.replace("\tint32 GetStep() const;\n", "")
    fill = HDR.replace("\tint32 GetStep() const;", "\tint32 GetStep() const { return 0; }")
    for name, new, want in [("추가는 허용", add, True), ("시그니처 변경은 위반", chg, False),
                            ("선언 삭제는 위반", dele, False), ("본문 채움은 허용", fill, True)]:
        r = L1.check({H: new}, baseline=lambda p: HDR)
        check(name, r.ok is want, r.summary)


def test_cpp_is_not_a_freeze_target() -> None:
    """동결은 **선언**의 문제다 — `.cpp` 본문이 바뀌는 것은 정상 작업이다."""
    r = L1.check({C: "void UFoo::Other() {}\n"}, baseline=lambda p: "void UFoo::F() {}\n")
    check(".cpp 는 동결 대상이 아니다", r.ok, r.summary)


def test_new_file_has_nothing_to_freeze() -> None:
    r = L1.check({H: HDR}, baseline=lambda p: None)
    check("신규 파일은 통과", r.ok, r.summary)
    check("동결 미검사로 센다", r.skipped == [H], str(r.skipped))


# ── ④ fail-closed ───────────────────────────────────────────────────────────────

def test_fail_closed_directions() -> None:
    empty = L1.check({})
    check("빈 입력은 통과가 아니다", not empty.ok, empty.summary)

    unchecked = L1.Layer1()
    check("안 돌린 것은 통과가 아니다", not unchecked.ok, unchecked.summary)
    check("미확인이라고 적는다", "미확인" in unchecked.summary, unchecked.summary)

    no_base = L1.check({H: HDR})
    check("기준 원본 없이도 잔재는 본다", no_base.checked)
    check("동결은 미검사라고 적는다", "미검사" in no_base.summary, no_base.summary)


# ── [중요] 배선 — 응답 수락 경로 (소 2.1.3) ─────────────────────────────────────────

def test_residue_response_is_rejected_at_acceptance_not_at_apply() -> None:
    """[중요] 잔재가 있는 응답이 *"통과"* 로 스풀에 들어가면 왕복이 하나 더 든다."""
    want = [H, C]
    good = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\nvoid UFoo::F() {{}}\n"
    ok = INF.judge("RESPONSE: 2\nRESULT: DONE", good, want=want)
    check("정상 응답은 통과", ok.ok, ok.summary)

    bad = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\n// [PSEUDO] 나중에\n"
    r = INF.judge("RESPONSE: 2\nRESULT: DONE", bad, want=want)
    check("[중요] 잔재가 있으면 수락 단계에서 막는다", not r.ok, r.summary)
    check("치명 메모로 남는다", any("휘발 태그" in n for n in r.fatal), str(r.notes))

    fb = f"=== FILE: {H} ===\n{HDR}=== FILE: {C} ===\n// [FEEDBACK] 남았다\n"
    r2 = INF.judge("RESPONSE: 2\nRESULT: DONE", fb, want=want)
    check("[FEEDBACK] 잔재도 수락 단계에서 막는다", not r2.ok, r2.summary)


# [중요] **여기 있던 `test_integrate_still_runs_layer1_as_the_last_line` 를 지웠다**
# (2026-09-03, 통합자 삭제). 층1 이 「두 곳」에 있다는 계약이 한 곳으로 줄었다 —
# 통합 시점 검사는 마스터에 없고, 응답 수락(`infer.judge`)과 커밋 직전(`wcommit`)이 남는다.
# 통합 검사는 `.33` 이 서브 브랜치를 전부 머지한 뒤 한 번 한다.

def test_a_citation_is_not_a_marker() -> None:
    """🔴 **`[DOC]` 문장이 태그를 인용한 것은 위반이 아니다** (실측 2026-09-05).

    라운드 2 조각 하나가 이렇게 죽었다 — 워커는 본문을 다 쓰고 실제 마커도 전부 지웠는데,
    골조의 설명 문장이 태그 이름을 **언급**하고 있었다:

        * EvaluateInteractor 의 후보 판정에 이 가드가 추가된다(아래 [PSEUDO] 참고).

    문자열 포함으로 보던 판정이 그것을 잡아 **커밋을 막고 추론값을 버렸다.**
    [주의] 느슨해진 것이 아니다 — 마커의 실제 모양(주석이 통째로 지시)만 본다.
    """
    cite = ("/**\n * [DOC] 이 가드는 후보 판정에 추가된다(아래 [PSEUDO] 참고).\n */\n"
            "void A::Go() { Do(); }\n")
    L = L1.check({"A.cpp": cite}, baseline=lambda p: None)
    check("🔴 인용은 통과한다", L.ok, L.summary)

    for real, why in (("// [PSEUDO] 여기를 채워라\n", "줄 주석"),
                      ("    // [PSEUDO:2] 두 번째\n", "들여쓴 줄 주석"),
                      (" * [IMPL] 채워라\n", "블록 주석 이어지는 줄"),
                      ("/* [PSEUDO] */\n", "블록 주석 시작")):
        L2 = L1.check({"A.cpp": "void A::Go() {}\n" + real}, baseline=lambda p: None)
        check(f"  실제 마커는 그대로 막는다 ({why})", not L2.ok, L2.summary)
        check(f"    사유가 태그를 지목한다 ({why})",
              any("휘발 태그" in p for p in L2.problems), L2.summary)


_KIMODO = Path(__file__).resolve().parents[1] / "KimodoMotion_WebUI/repo"


def _py_pair():
    """Kimodo 실물 `pose_ops.py` → (구현본, 골조, 함수명). 실물이 없으면 작은 대역."""
    import ast
    f = _KIMODO / "webui/pose_ops.py"
    real = f.read_text(encoding="utf-8") if f.is_file() else \
        "def joint_names():\n    return ['a']\n\n\ndef other(x):\n    return x\n"
    tree = ast.parse(real)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    lines = real.splitlines()
    ind = " " * (fn.col_offset + 4)
    skel = "\n".join(lines[:fn.body[0].lineno - 1]
                     + [f"{ind}# [DOC] 무엇을 왜", f"{ind}# [PSEUDO] 여기를 채워라",
                        f"{ind}raise NotImplementedError"]
                     + lines[fn.end_lineno:]) + "\n"
    return real, skel, fn.name, lines[fn.lineno - 1]


def test_python_freeze_stub_and_syntax():
    print("\n🔴 `.py` — 동결 · 스텁 잔존 · 구문 (`#695` P3)")
    real, skel, name, defline = _py_pair()
    path = "webui/pose_ops.py"
    base = lambda p: skel if p == path else None                      # noqa: E731

    L = L1.check({path: real}, baseline=base)
    check(f"실물 구현({name})은 골조 대비 통과", L.ok, L.summary)
    check("  동결을 실제로 봤다 (skipped 아님)", path not in L.skipped, str(L.skipped))

    stub = skel.replace("# [PSEUDO] 여기를 채워라\n", "")
    L = L1.check({path: stub}, baseline=base)
    check("🔴 마커만 지우고 스텁을 남기면 위반", not L.ok and any("스텁" in x for x in L.problems),
          str(L.problems))

    changed = real.replace(defline, defline.replace("(", "(extra_arg, ", 1), 1)
    L = L1.check({path: changed}, baseline=base)
    check("🔴 시그니처 변경은 동결 위반", not L.ok and any("동결" in x for x in L.problems), str(L.problems))

    import ast
    tree = ast.parse(real)
    last = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))][-1]
    rl = real.splitlines()
    deleted = "\n".join(rl[:last.lineno - 1 - len(last.decorator_list)] + rl[last.end_lineno:]) + "\n"
    L = L1.check({path: deleted}, baseline=lambda p: real)
    check(f"🔴 정의 삭제({last.name})는 동결 위반", not L.ok and any("동결" in x for x in L.problems),
          str(L.problems)[:200])

    L = L1.check({path: real + "\n\ndef brand_new_helper(a, b=1):\n    return a + b\n"},
                     baseline=lambda p: real)
    check("  추가는 허용", L.ok, L.summary)

    L = L1.check({path: real.replace("def ", "def (", 1)})
    check("🔴 구문 오류는 원본 없이도 위반", not L.ok and any("구문" in x for x in L.problems),
          str(L.problems)[:160])

    L = L1.check({path: real})
    check("[중요] 원본이 없으면 `.py` 도 skipped 에 든다", path in L.skipped, str(L.skipped))
    check("  요약이 동결 미검사를 말한다 (조용한 통과 아님)", "동결 미검사" in L.summary, L.summary)
    L = L1.check({path: real, "webui/new.py": "x = 1\n"}, baseline=base)
    check("  신규 .py 도 skipped 로 표시된다", L.skipped == ["webui/new.py"], str(L.skipped))

    # 실물 전수 — 자기 자신을 원본으로 두면 위반 0 이어야 한다 (오탐 측정)
    files = {str(f.relative_to(_KIMODO)): f.read_text(encoding="utf-8", errors="replace")
             for d in ("webui", "scripts") for f in sorted((_KIMODO / d).rglob("*.py"))}
    if files:
        L = L1.check(files, baseline=lambda p: files.get(p))
        check(f"🔴 Kimodo 실물 {len(files)}개 — 자기 대조 오탐 0", L.ok, str(L.problems)[:200])

def test_pyflakes_undefined_name_815():
    print("\n🔴 `.py` — pyflakes 정의 안 된 이름을 조각 단위로 (`#815`)")
    p = "pkg/mod.py"
    bad = "def f():\n    return missing_name + 1\n"
    L = L1.check({p: bad}, baseline=lambda _p: "def f():\n    raise NotImplementedError\n")
    check("새 undefined name 은 위반", not L.ok and any("missing_name" in x for x in L.problems),
          str(L.problems))
    check("  문구가 줄 번호·한글 설명을 싣는다",
          any(x.startswith(f"{p}:2: 정의되지 않은 이름") for x in L.problems), str(L.problems))

    L = L1.check({p: bad}, baseline=lambda _p: bad)
    check("기준 원본에 이미 있던 같은 이름은 통과", L.ok, L.summary)

    two = "def f():\n    return missing_name + missing_name\n"
    L = L1.check({p: two}, baseline=lambda _p: bad)
    n = sum("missing_name" in x for x in L.problems)
    check("🔴 기준보다 한 번 더 쓰면 한 건만 막는다 (개수 비교)", n == 1, str(L.problems))

    L = L1.check({p: bad}, baseline=lambda _p: None)
    check("신규 파일(None)의 undefined name 은 위반", not L.ok and len(L.problems) == 1,
          str(L.problems))
    L = L1.check({p: bad})
    check("baseline 함수가 없어도 검사한다", not L.ok and len(L.problems) == 1, str(L.problems))

    skel = ("import os\n\n\ndef f():\n    # [DOC] 경로를 돌려준다\n"
            "    raise NotImplementedError\n")
    impl = "import os\n\n\ndef f():\n    # [DOC] 경로를 돌려준다\n    return os.getcwd()\n"
    L = L1.check({p: skel}, baseline=lambda _p: None)
    check("미사용 import 만 있는 골조는 통과 (비차단)", L.ok, L.summary)
    L = L1.check({p: impl}, baseline=lambda _p: skel)
    check("  골조의 미사용 import 를 구현이 쓰면 통과", L.ok, L.summary)
    L = L1.check({p: "import os\nx = 1\ny = f'abc'\nx = 2\n"})
    check("  비차단 경고(미사용·f-string·재정의)는 문제에 안 든다", L.ok, L.summary)

    L = L1.check({p: "__all__ = ['ghost']\n"}, baseline=lambda _p: None)
    check("`__all__` 의 정의 안 된 이름은 위반",
          not L.ok and any("ghost" in x and "__all__" in x for x in L.problems), str(L.problems))

    L = L1.check({p: "def f(:\n    return nope\n"}, baseline=lambda _p: None)
    check("구문 오류는 구문으로 한 번만 (pyflakes 중복 없음)",
          len(L.problems) == 1 and "구문 오류" in L.problems[0], str(L.problems))

    L = L1.check({"Source/A.cpp": "int f() { return missing_name; }\n",
                  "notes.txt": "missing_name\n"}, baseline=lambda _p: None)
    check(".py 가 아닌 파일은 이 검사 대상이 아니다", L.ok and not L.unchecked, L.summary)


def test_pyflakes_unavailable_is_unchecked_not_blocked():
    print("\n🔴 pyflakes 를 못 돌리면 막지 않고 미검사로 적는다 (`#815`, 사용자 결정)")
    saved = {k: sys.modules.get(k) for k in ("pyflakes", "pyflakes.api", "pyflakes.reporter")}
    for k in saved:
        sys.modules[k] = None                                # → ImportError
    try:
        L = L1.check({"a.py": "x = missing_name\n", "b.py": "y = other\n"},
                     baseline=lambda _p: None)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    check("미설치는 막지 않는다", L.ok and not L.problems, str(L.problems))
    check("  미검사로 한 번 기록된다", len(L.unchecked) == 1 and "Error" in L.unchecked[0],
          str(L.unchecked))
    check("  요약이 pyflakes 미검사를 말한다", "pyflakes 미검사" in L.summary, L.summary)

    real = L1._flakes
    def boom(path, text):
        raise L1._FlakesUnavailable(f"{path}: RuntimeError: 터짐")
    L1._flakes = boom
    try:
        L = L1.check({"a.py": "x = missing_name\n"})
    finally:
        L1._flakes = real
    check("pyflakes 예외도 막지 않고 미검사", L.ok and "pyflakes 미검사" in L.summary, L.summary)
    L = L1.check({"a.py": "x = missing_name\n"})
    check("  복원 뒤 다시 잡는다", not L.ok, L.summary)


def main() -> int:
    for fn in (test_a_citation_is_not_a_marker,test_volatile_tags_are_caught, test_permanent_tags_and_plain_comments_pass,
               test_feedback_left_in_source_is_a_violation, test_retry_feedback_block_residue_is_a_violation,
               test_fence_residue_is_a_violation, test_fence_baseline_aware_819,
               test_freeze_semantics, test_cpp_is_not_a_freeze_target,
               test_new_file_has_nothing_to_freeze, test_fail_closed_directions,
               test_residue_response_is_rejected_at_acceptance_not_at_apply,
               test_python_freeze_stub_and_syntax,
               test_pyflakes_undefined_name_815, test_pyflakes_unavailable_is_unchecked_not_blocked):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_layer1: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
