"""리뷰 큐 소비자 (`#636`) — **초고까지만 만든다. 상용은 사람이 건다.**

검증하는 것:

    ① 🔴 **자동 경로에 상용 호출이 없다** — commercial_chat 을 가로채 호출 0 을 확인한다
    ② 초고가 나면 `reviews/<작성자>/` 에 「미검증」으로 쓰인다
    ③ 🔴 **초고 문서에 표가 없다** → 소비자가 0건으로 읽어 유령 항목이 안 생긴다
    ④ [중요] 지적 없음이면 **문서를 쓰지 않는다** (12/20 이 지적 0건인 프로젝트다)
    ⑤ 초고 호출 실패는 큐에 남아 재시도된다
    ⑥ diff 를 못 읽으면 **결정적**으로 갈려 1회에 멈춘다
    ⑦ trivial·소스 없음은 유실이 아니라 설계된 스킵 — done 으로 종결
    ⑧ `kind=scope` 는 이 소비자가 처리하지 않는다 (`#639` 의 몫)
    ⑨ 선언부는 커밋에 `.h` 가 없어도 짝 헤더에서 긁는다
    ⑩ grounding 머리말이 「미검증·버려라」를 먼저 말한다 (사람 검증 단계용)
    ⑪ 🔴 **`main()` 이 실제로 돈다** — 유닛이 부르는 진입점이다

[중요] ⑪ 은 값을 치르고 얻었다. 첫 배포 회차가 @reg.projects@ AttributeError 로 죽었는데
(`Registry` 의 필드는 `.names` 다), **유닛 21건이 전부 통과한 상태였다** — `run_once` 만 탔고
`main()` 은 한 줄도 안 탔기 때문이다. 유닛이 부르는 경로는 유닛 테스트도 타야 한다.

`.venv/bin/python master/test_review_runner.py`
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import review_gen as RG                 # noqa: E402
from master.context_synth import review_queue as Q                # noqa: E402
from master.context_synth import review_runner as R               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Paths:
    def __init__(self, root):
        self.root = str(root)
        self.repo = str(Path(root) / "repo")
        self.canary = Path(root) / "canary" / "permanent_loss.jsonl"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root)] + list(a),
                          capture_output=True, text=True)


def make_repo() -> Path:
    """실제 git 저장소 — diff·작성자를 진짜로 읽는다 (모의하지 않는다)."""
    root = Path(tempfile.mkdtemp(prefix="ax-run-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text(
        "class AFoo {\npublic:\n  void Bar();\n};\n", encoding="utf-8")
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {}\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "init")
    (repo / "Source" / "M" / "A.cpp").write_text(
        "void AFoo::Bar() {\n  int x = 1;\n  x = x / 0;\n}\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "change")
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    return root, head


def test_초고까지만_만든다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    called = []
    orig = RG.commercial_chat
    RG.commercial_chat = lambda *a, **kw: called.append(1)
    try:
        r = R.run_once(Paths(root), draft_call=lambda p: "나눗셈이 0 이다. 라인 3.")
    finally:
        RG.commercial_chat = orig
    check("🔴 ① 자동 경로가 상용을 부르지 않는다", not called, str(called))
    check("② 초고가 저장된다", bool(r.written) and Path(r.written).is_file(), str(r.written))
    body = Path(r.written).read_text(encoding="utf-8")
    check("② 「미검증」 표시가 있다", R.DRAFT_STATUS in body)
    check("② 커밋 헤더가 있다 (fix_index 가 번호를 준다)", f"- 커밋: `{head}`" in body)
    check("🔴 ③ 표가 없다 — 유령 항목이 안 생긴다",
          not RG.format_ok(body) and RG.parseable_rows(body) == 0,
          f"rows={RG.parseable_rows(body)}")
    check("큐가 done 이다", Q.counts(root)["done"] == 1, str(Q.counts(root)))
    shutil.rmtree(root)


def test_지적_없으면_문서를_안_쓴다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "없음")
    check("④ 문서를 쓰지 않는다", not r.written, str(r.written))
    check("④ 그래도 done 으로 종결", r.state == "done" and Q.counts(root)["done"] == 1)
    check("④ 사유가 남는다", r.why == "지적 없음", r.why)
    shutil.rmtree(root)


def test_초고_실패는_재시도된다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])

    def boom(p):
        raise RuntimeError("브로커에 닿지 않는다")

    r = R.run_once(Paths(root), draft_call=boom)
    check("⑤ 실패로 기록된다", r.state == "failed", r.state)
    check("⑤ 큐에 남아 다시 잡힌다", Q.claim(root) is not None)
    shutil.rmtree(root)


def test_diff를_못_읽으면_결정적이다():
    root, _ = make_repo()
    Q.enqueue(root, key="0" * 40, files=["Source/M/A.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑥ 실패", r.state == "failed", r.state)
    it = Q.items(root)[0]
    check("🔴 ⑥ 결정적으로 갈린다", it["last_kind"] == Q.DETERMINISTIC, it["last_kind"])
    check("🔴 ⑥ 1회에 멈춘다 (몇 번을 돌려도 같다)",
          it["state"] == "abandoned", it["state"])
    shutil.rmtree(root)


def test_설계된_스킵():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["README.md"])
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑦ 소스 변경 없음은 done", r.state == "done" and r.why == "소스 변경 없음", r.why)
    shutil.rmtree(root)

    root, head = make_repo()
    Q.enqueue(root, kind="scope", key="Source/M")
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑧ kind=scope 는 처리하지 않는다 (#639 의 몫)",
          r.state == "failed" and "kind" in (r.why or ""), r.why)
    shutil.rmtree(root)


def test_선언부():
    root, head = make_repo()
    d = R.declarations(Path(root) / "repo", ["Source/M/A.cpp"], head)
    check("🔴 ⑨ 커밋에 .h 가 없어도 짝 헤더를 긁는다", "class AFoo" in d, d[:80])
    check("⑨ 경로가 붙는다", "Source/M/A.h" in d, d[:80])
    shutil.rmtree(root)


def test_main_이_실제로_돈다():
    """🔴 ⑪ 유닛이 부르는 진입점. 레지스트리·경로 해석까지 진짜로 탄다.

    [중요] 여기서 모의하는 것은 **로컬 모델 호출 하나뿐**이다 — 나머지(레지스트리 로드,
    프로젝트 이름 해석, 트윈 경로, 큐 읽기)는 실물로 돈다. 첫 배포가 죽은 자리가 바로
    그 「나머지」였다.
    """
    import os
    root, head = make_repo()
    projects = Path(tempfile.mkdtemp(prefix="ax-reg-"))
    (projects / "projects.yaml").write_text(
        "version: 1\nactive: T\nprojects:\n  - T\n", encoding="utf-8")
    twin = projects / "T"
    twin.mkdir()
    (twin / "config.yaml").write_text(
        f"version: 1\nname: T\nrepo:\n  local_clone: repo\n", encoding="utf-8")
    shutil.copytree(Path(root) / "repo", twin / "repo")

    old_env = os.environ.get("AX_PROJECTS_ROOT")
    os.environ["AX_PROJECTS_ROOT"] = str(projects)
    calls = []
    orig_draft = R.draft
    R.draft = lambda *a, **kw: (calls.append(1), ("나눗셈이 0 이다.", ""))[1]
    try:
        Q.enqueue(twin, key=head, files=["Source/M/A.cpp"])
        rc = R.main(["--limit", "1"])
        check("🔴 ⑪ main() 이 rc=0 으로 끝난다", rc == 0, f"rc={rc}")
        check("⑪ 큐를 실제로 비웠다", Q.counts(twin)["done"] == 1, str(Q.counts(twin)))
        check("⑪ 초고 호출이 일어났다", len(calls) == 1, str(calls))
        rc2 = R.main(["--limit", "1"])
        check("⑪ 큐가 비면 조용히 끝난다", rc2 == 0 and len(calls) == 1, f"rc={rc2}")
    finally:
        R.draft = orig_draft
        if old_env is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_env
    shutil.rmtree(root); shutil.rmtree(projects)


def test_grounding_머리말():
    g = R.grounding_text("초고다", "class AFoo;")
    check("⑩ 미검증이라고 먼저 말한다", "미검증" in g and "버려라" in g, g[:90])
    check("⑩ 선언부는 실측으로 구분한다", "실측" in g, g[:90])
    check("⑩ 둘 다 비면 빈 문자열", R.grounding_text("", "") == "")


if __name__ == "__main__":
    for fn in (test_초고까지만_만든다, test_지적_없으면_문서를_안_쓴다,
               test_초고_실패는_재시도된다, test_diff를_못_읽으면_결정적이다,
               test_설계된_스킵, test_선언부, test_main_이_실제로_돈다,
               test_grounding_머리말):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
