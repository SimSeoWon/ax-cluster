"""골조 빌드 게이트 (소 1.1.5).

[중요] 지키는 계약은 **fail-closed** 다 — *"확인하지 못했다"* 를 *"괜찮다"* 로 바꾸면 이 게이트는
없는 것과 같다. 원전은 빌드를 등재 *뒤*에 두었다가 깨진 골조가 `origin` 에 박혔다.

`.venv/bin/python master/test_skeleton_gate.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.layer3_verify import BuildResult      # noqa: E402
from master.work import skeleton as S             # noqa: E402
from master.work import skeleton_gate as G        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Facts:
    host: str = "192.168.0.2"
    user: str = "janus"
    windows: bool = True
    path: str = r"E:\trunk\ModularStage"
    home: str = r"C:\Users\janus"
    ue5: str = r"C:\Program Files\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def good_skeleton() -> S.Skeleton:
    head = ("#pragma once\nUCLASS()\nclass FOO_API UFoo : public UObject\n{\n"
            "    GENERATED_BODY()\npublic:\n    void Go();\n};\n")
    return S.Skeleton(stem="Foo",
                      files={"Source/A/Foo.h": "// [DOC] 왜 이렇게 생겼나\n" + head,
                             "Source/A/Foo.cpp": "// [DOC] 무엇을 왜\n// [PSEUDO] 구현한다"},
                      frozen=S.frozen_decls(head), pseudo=1)


def test_build_bat_is_derived_not_guessed() -> None:
    """[중요] 실측: 이 기계의 엔진은 `C:\\Program Files\\UE_5.8` — `Epic Games` 하위가 아니다.

    경로를 짐작했다가 실제로 틀렸다(1차 측정이 `NO_BUILD_BAT` 으로 끝났다). `probe` 가
    찾아 둔 값에서 되짚는다.
    """
    bb = G._build_bat_from(Facts())
    check("Build.bat 을 유도한다",
          bb == r"C:\Program Files\UE_5.8\Engine\Build\BatchFiles\Build.bat", bb)
    check("엔진을 모르면 빈 문자열", G._build_bat_from(Facts(ue5="")) == "")
    check("모양이 다르면 빈 문자열", G._build_bat_from(Facts(ue5=r"C:\weird\thing.exe")) == "")


def test_target_name() -> None:
    check("에디터 타깃을 만든다", G.target_name("ModularStage") == "ModularStageEditor")
    check("이미 붙어 있으면 그대로", G.target_name("ModularStageEditor") == "ModularStageEditor")
    try:
        G.target_name("")
        check("[중요] 빈 프로젝트는 거부", False)
    except ValueError:
        check("[중요] 빈 프로젝트는 거부", True)


def test_place_writes_into_the_isolated_tree() -> None:
    """[중요] 사람·워커의 트리가 아니라 **격리 트리**에 쓴다."""
    wrote: list = []
    got = G.place(Facts(), r"E:\trunk\ms-wt-1",
                  {"Source/A/Foo.h": "h", "Source/A/Foo.cpp": "c"},
                  writer=lambda f, p, t: wrote.append((p, t)))
    check("경로를 윈도우로 잇는다",
          got == [r"E:\trunk\ms-wt-1\Source\A\Foo.cpp", r"E:\trunk\ms-wt-1\Source\A\Foo.h"],
          str(got))
    check("체크아웃 경로를 안 쓴다", all("ModularStage\\Source" not in p for p, _ in wrote))
    check("내용을 그대로 넘긴다", sorted(t for _, t in wrote) == ["c", "h"])
    try:
        G.place(Facts(), "", {"a.h": "x"}, writer=lambda *a: None)
        check("[중요] 트리 경로가 비면 거부", False)
    except ValueError:
        check("[중요] 트리 경로가 비면 거부", True)


def test_gate_blocks_before_building_when_not_a_skeleton() -> None:
    """[중요] 골조가 아니면 빌드할 이유도 없다 — 싼 검사를 먼저."""
    built: list = []
    bad = S.Skeleton(stem="Bad", files={"a.h": "완성된 파일"}, frozen=set(), pseudo=0)
    g = G.run(Facts(), bad, tree=r"E:\wt", project="ModularStage",
              writer=lambda *a: None, builder=lambda *a, **k: built.append(1))
    check("[중요] 통과가 아니다", not g.ok, g.summary)
    check("빌드를 부르지 않았다", built == [], str(built))
    check("사유를 말한다", "골조가 아니다" in g.error, g.error)

    empty = S.Skeleton(stem="Empty")
    g2 = G.run(Facts(), empty, tree=r"E:\wt", project="ModularStage",
               writer=lambda *a: None, builder=lambda *a, **k: built.append(1))
    check("[중요] 파일이 없으면 막는다", not g2.ok and "세울 것이 없다" in g2.error, g2.error)


def test_gate_refuses_feedback_in_a_skeleton() -> None:
    """🔴 **`[FEEDBACK]` 은 골조에 쓸 수 없다** (2026-09-05 — `.33` 이 라운드 2 골조에
    「기존 코드 수정 지시」로 쓰려다 잡혔다).

    둘 다 **조용히** 실패하는 자리라 사람이 못 본다:
      ① 층1 이 소스에 남은 `[FEEDBACK]` 을 위반으로 잡아 워커 커밋이 막힌다
      ② 사전 훑기는 `[PSEUDO]` 개수로만 「할 일 있음」을 판정한다 — `[FEEDBACK]` 만 든
         파일은 *"골조가 이미 완성본"* 으로 걷혀 **파견조차 되지 않는다**
    """
    built: list = []
    sk = good_skeleton()
    first = sorted(sk.files)[0]
    sk.files[first] = sk.files[first] + "\n    // [FEEDBACK] 여기 필터가 빠졌다 — 고쳐라\n"
    g = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage",
              writer=lambda *a: None, builder=lambda *a, **k: built.append(1))
    check("🔴 통과가 아니다", not g.ok, g.summary)
    check("  빌드를 부르지 않았다 (싼 검사가 먼저다)", built == [], str(built))
    check("  사유가 태그를 지목한다", "[FEEDBACK]" in g.error, g.error)
    check("  대신 무엇을 쓸지 말한다", "`[PSEUDO]`" in g.error, g.error)


def test_gate_is_fail_closed_on_every_uncertainty() -> None:
    """[중요] *"확인하지 못했다"* 는 통과가 아니다."""
    sk = good_skeleton()

    # ① 배치 실패
    def boom(*a):
        raise RuntimeError("scp 해시 불일치")
    g = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=boom,
              builder=lambda *a, **k: BuildResult(passed=True, failure=None, result="Succeeded"))
    check("[중요] 배치 실패는 막는다", not g.ok and "배치 실패" in g.error, g.error)
    check("배치 실패면 빌드 안 함", not g.checked)

    # ② 엔진을 못 찾음
    g2 = G.run(Facts(ue5=""), sk, tree=r"E:\wt", project="ModularStage",
               writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=True, failure=None))
    check("[중요] 엔진 미발견은 막는다", not g2.ok and "Build.bat" in g2.error, g2.error)

    # ③ UBT 가 판정을 못 냈다 (SSH 실패·타임아웃) — layer3 계약이 failure 로 준다
    g3 = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=False, failure="3600초 안에 안 끝났다"))
    check("[중요] 판정 없음은 막는다", not g3.ok, g3.summary)
    check("돌리긴 했다고 기록", g3.checked)

    # ④ 빌드 실패
    g4 = G.run(Facts(), sk, tree=r"E:\wt", project="ModularStage", writer=lambda *a: None,
               builder=lambda *a, **k: BuildResult(passed=False, failure=None,
                                                   result="Failed", detail="CompileError"))
    check("[중요] 빌드 실패는 막는다", not g4.ok, g4.summary)
    check("요약이 사유를 보인다", "FAILED" in g4.summary or "CompileError" in g4.summary,
          g4.summary)


def test_gate_passes_only_on_a_real_verdict() -> None:
    seen: dict = {}

    def builder(host, user, bb, target, up, **kw):
        seen.update(host=host, target=target, uproject=up, build_bat=bb)
        return BuildResult(passed=True, failure=None, result="Succeeded", seconds=812.4)

    g = G.run(Facts(), good_skeleton(), tree=r"E:\trunk\ms-wt-7", project="ModularStage",
              writer=lambda *a: None, builder=builder)
    check("[완료] 통과", g.ok, g.summary)
    check("에디터 타깃을 짓는다", seen["target"] == "ModularStageEditor", str(seen))
    check("[중요] uproject 도 격리 트리 것", seen["uproject"] == r"E:\trunk\ms-wt-7\ModularStage.uproject",
          seen["uproject"])
    check("유도한 Build.bat 을 쓴다", seen["build_bat"].endswith(r"\Build.bat"), seen["build_bat"])
    check("소요를 기록한다", g.seconds == 812.4, str(g.seconds))
    check("파일 수를 요약에", "파일 2" in g.summary, g.summary)


def test_not_run_is_not_a_pass() -> None:
    """[주의] **게이트를 안 붙인 것**과 **게이트가 통과한 것**은 다르다."""
    g = G.GateResult(stem="Foo")
    check("[중요] 안 돌렸으면 통과 아님", not g.ok)
    check("요약이 '미확인' 이라고 말한다", "미확인" in g.summary, g.summary)


def _kimodo_py_skeleton():
    """Kimodo 실물 `webui/pose_ops.py` 의 첫 최상위 함수를 D2 모양 골조로 바꾼다.

    실물이 없으면(다른 기계) 같은 모양의 작은 파일로 대신한다 — 판정 규칙은 같다.
    """
    import ast
    src_p = Path(__file__).resolve().parents[1] / "KimodoMotion_WebUI/repo/webui/pose_ops.py"
    if src_p.is_file():
        src = src_p.read_text(encoding="utf-8")
    else:
        src = "def joint_names():\n    return ['a']\n"
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    lines = src.splitlines()
    head = lines[:fn.body[0].lineno - 1]
    tail = lines[fn.end_lineno:]
    ind = " " * (fn.col_offset + 4)
    body = [f"{ind}# [DOC] 이 함수가 무엇을 왜 하는가 — 계약은 여기 남는다",
            f"{ind}# [PSEUDO] 여기를 채워라",
            f"{ind}raise NotImplementedError"]
    return "\n".join(head + body + tail) + "\n", fn.name


def test_python_skeleton_gate():
    print("\n🔴 `kind: code` — `.py` 골조 게이트 (`#695` P2)")
    text, name = _kimodo_py_skeleton()

    @dataclass
    class _Sk:
        stem: str
        files: dict
        ok: bool = False          # [중요] Python 골조는 동결 헤더가 없다 — `ok` 에 기대지 않는다

    good = _Sk("pose_ops", {"webui/pose_ops.py": text})
    g = G.run_python(good)
    check(f"실물 골조({name})는 통과한다", g.ok, g.summary)
    check("  mode 는 py_compile", g.mode == G.MODE_PY, g.mode)
    check("  판정을 실제로 냈다 (checked)", g.checked)
    g2 = G.run(None, good, tree="", project="x")
    check("[중요] run() 이 `.py` 를 Python 판으로 보낸다 (SSH·UHT 없이)", g2.ok and g2.mode == G.MODE_PY,
          g2.summary)

    broken = _Sk("b", {"webui/pose_ops.py": text.replace("raise NotImplementedError", "raise (", 1)})
    g = G.run_python(broken)
    check("🔴 구문이 깨진 골조는 막는다", not g.ok and g.checked, g.summary)
    check("  사유에 파일:행 이 있다", "webui/pose_ops.py:" in (g.build.raw_tail if g.build else ""),
          g.build.raw_tail if g.build else "")

    for label, files, want in (
        ("`.py` 가 아닌 파일이 섞이면 막는다", {"a.py": text, "b.cpp": "// [DOC] x"}, "`.py` 가 아닌"),
        ("`# [PSEUDO]` 0개면 완성 파일이다", {"a.py": text.replace("# [PSEUDO] 여기를 채워라", "")}, "[PSEUDO]"),
        ("`[DOC]` 0개면 계약이 안 남는다", {"a.py": text.replace("[DOC]", "설명")}, "[DOC]"),
        ("`[FEEDBACK]` 이 있으면 막는다", {"a.py": text + "# [FEEDBACK] 고쳐라\n"}, "[FEEDBACK]"),
        ("파일이 없으면 막는다", {}, "파일이 없다"),
    ):
        g = G.run_python(_Sk("x", files))
        check(label, not g.ok and want in g.error, g.error[:120])
    check("  문장 중간의 [PSEUDO] 는 마커가 아니다 (층1 과 같은 모양)",
          not G.run_python(_Sk("x", {"a.py": "# [DOC] 아래 [PSEUDO] 참고\nx = 1\n"})).ok)

    import os
    before = set(os.listdir(Path(__file__).resolve().parent))
    G.run_python(good)
    check("[중요] 바이트코드를 쓰지 않는다 (트리를 안 더럽힌다)",
          set(os.listdir(Path(__file__).resolve().parent)) == before)



def test_check_head_cli():
    """🔴 `#695` P6 ⓐ — 요청자가 push 전에 부르는 입구. **HEAD 커밋**을 잰다, 실제 `-m` 실행."""
    import os
    import subprocess
    import sys as _s
    import tempfile
    print("\n🔴 `.py` 골조 — push 전 검사 입구 (`-m …skeleton_gate --py`)")
    repo_root = Path(__file__).resolve().parents[1]
    good = "# [DOC] 무엇을 왜\ndef f(a):\n    # [PSEUDO] 채워라\n    raise NotImplementedError\n"
    with tempfile.TemporaryDirectory() as d:
        g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
        g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        Path(d, "a.py").write_text(good, encoding="utf-8")
        g("add", "-A"); g("commit", "-q", "-m", "skel")
        env = {**os.environ, "PYTHONPATH": str(repo_root)}
        run = lambda *files: subprocess.run(  # noqa: E731
            [_s.executable, "-m", "master.work.skeleton_gate", "--py", *files],
            cwd=d, env=env, capture_output=True, text=True)
        r = run("a.py")
        check("정상 골조 — rc 0", r.returncode == 0, r.stdout + r.stderr)
        Path(d, "a.py").write_text(good.replace("raise NotImplementedError", "raise ("), encoding="utf-8")
        r = run("a.py")
        check("[중요] 작업 트리가 아니라 HEAD 를 잰다 (커밋 안 한 깨짐은 안 보인다)", r.returncode == 0,
              r.stdout)
        g("commit", "-qam", "broken")
        r = run("a.py")
        check("🔴 커밋된 깨짐은 rc 1 + 파일:행", r.returncode == 1 and "a.py:" in r.stdout, r.stdout)
        r = run("nope.py")
        check("  HEAD 에 없는 파일은 rc 1 + 사유", r.returncode == 1 and "HEAD 에 없는" in r.stdout, r.stdout)
        r = subprocess.run([_s.executable, "-m", "master.work.skeleton_gate"], cwd=d, env=env,
                           capture_output=True, text=True)
        check("  인자가 없으면 rc 2 + 사용법", r.returncode == 2 and "사용법" in r.stdout, r.stdout)

def main() -> int:
    for fn in (test_build_bat_is_derived_not_guessed, test_target_name,
               test_place_writes_into_the_isolated_tree,
               test_gate_blocks_before_building_when_not_a_skeleton,
               test_gate_refuses_feedback_in_a_skeleton,
               test_gate_is_fail_closed_on_every_uncertainty,
               test_gate_passes_only_on_a_real_verdict, test_not_run_is_not_a_pass,
               test_python_skeleton_gate, test_check_head_cli):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_skeleton_gate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
