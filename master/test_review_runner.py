"""리뷰 큐 소비자 (`#636`·`#638`) — 로컬 초안 → Antigravity 정형 리뷰.

검증하는 것:

    ① 로컬 초안 뒤에 Antigravity를 정확히 한 번 부른다 (Claude 자동 폴백 없음)
    ② 성공하면 초안은 제거되고 최종 정형 리뷰만 `reviews/<작성자>/`
    ③ 최종 리뷰를 기존 수집기가 읽어 주간 플랜 입력이 된다
    ④ 로컬이 「없음」이어도 Antigravity는 원본 diff를 직접 본다
    ⑤ 초고 호출 실패는 큐에 남아 재시도된다
    ⑥ diff 를 못 읽으면 **결정적**으로 갈려 1회에 멈춘다
    ⑦ trivial·소스 없음은 유실이 아니라 설계된 스킵 — done 으로 종결
    ⑧ `kind=scope` 는 이 소비자가 처리하지 않는다 (`#639` 의 몫)
    ⑨ 선언부는 커밋에 `.h` 가 없어도 짝 헤더에서 긁는다
    ⑩ grounding 머리말이 「미검증·버려라」를 먼저 말한다 (Antigravity 검증용)
    ⑫ 기존 초안을 재사용하고 성공 시 제거한다. 실패 시에는 보존한다
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
        self.ontology = str(Path(root) / "ontology")
        self.canary = Path(root) / "canary" / "permanent_loss.jsonl"
        self.usage_log = Path(root) / "usage_log.jsonl"          # `#713` ① 기록 지점


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


def _review_body():
    return """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 3 | 0으로 나눔 | 분모 검사 |

## 3. 영향 분석
런타임 오류 위험.
"""


def test_로컬뒤_antigravity가_퇴고한다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []
    r = R.run_once(Paths(root), draft_call=lambda p: "나눗셈이 0 이다. 라인 3.",
                   review_call=lambda p: calls.append(p) or _review_body())
    check("① Antigravity 퇴고를 한 번 부른다", len(calls) == 1, str(len(calls)))
    check("① 퇴고 프롬프트에 초안과 원본 diff가 함께 있다",
          "나눗셈이 0" in calls[0] and "x = x / 0" in calls[0])
    check("② 성공한 초안은 제거", not r.draft_written
          and not list((Path(root) / "reviews" / "_drafts").rglob("*.md")))
    check("② 최종 리뷰는 작성자 디렉토리", "reviews/테스터/" in r.written
          and Path(r.written).is_file(), r.written)
    body = Path(r.written).read_text(encoding="utf-8")
    check("③ 최종 리뷰가 정형 계약", RG.format_ok(body) and RG.parseable_rows(body) == 1)
    check("③ 최종 리뷰에 모델 이력", "초안 모델: gemma4:e4b" in body
          and "검증 모델: Antigravity" in body)
    check("큐가 done 이다", Q.counts(root)["done"] == 1, str(Q.counts(root)))
    shutil.rmtree(root)


def test_로컬_없음이어도_antigravity가_본다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []
    r = R.run_once(Paths(root), draft_call=lambda p: "없음",
                   review_call=lambda p: calls.append(p) or _review_body())
    check("④ 로컬이 없음이어도 Antigravity 호출", len(calls) == 1)
    check("④ 최종 리뷰가 저장되고 done", bool(r.written) and r.state == "done"
          and Q.counts(root)["done"] == 1)
    shutil.rmtree(root)


def test_초안_실패여도_antigravity가_마무리한다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])

    def boom(p):
        raise RuntimeError("브로커에 닿지 않는다")

    calls = []
    r = R.run_once(Paths(root), draft_call=boom,
                   review_call=lambda p: calls.append(p) or _review_body())
    check("⑤ 로컬 초안 실패여도 Antigravity가 호출된다", len(calls) == 1)
    check("⑤ 최종 리뷰 성공으로 종결된다", r.state == "done" and bool(r.written), r.state)
    shutil.rmtree(root)


def test_기존_초안_재사용과_실패_보존():
    root, head = make_repo()
    paths = Paths(root)
    old = Path(R.write_draft(paths, head, ["Source/M/A.cpp"], "기존 초안의 0 나눗셈"))
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    local_calls = []
    prompts = []
    r = R.run_once(paths, draft_call=lambda p: local_calls.append(p) or "새 초안",
                   review_call=lambda p: prompts.append(p) or _review_body())
    check("⑫ 기존 초안이면 로컬 재호출 없음", not local_calls)
    check("⑫ 기존 초안이 Antigravity 입력", "기존 초안의 0 나눗셈" in prompts[0])
    check("⑫ 성공한 기존 초안 제거", not old.exists() and r.state == "done")
    shutil.rmtree(root)

    root, head = make_repo()
    paths = Paths(root)
    old = Path(R.write_draft(paths, head, ["Source/M/A.cpp"], "실패 때 남을 초안"))
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    r = R.run_once(paths, draft_call=lambda p: "호출되면 안 됨", review_call=lambda p: "산문")
    check("⑫ 형식 실패면 초안 보존", r.state == "failed" and old.is_file())
    check("⑫ 실패 산출물은 일반 리뷰에 없음",
          not list((Path(root) / "reviews" / "테스터").glob("*.md")))
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
    orig_draft, orig_agy = R.draft, R.agy_only
    R.draft = lambda *a, **kw: (calls.append(1), ("나눗셈이 0 이다.", ""))[1]
    R.agy_only = lambda _p, **_kw: _review_body()
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
        R.agy_only = orig_agy
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
    for fn in (test_로컬뒤_antigravity가_퇴고한다,
               test_로컬_없음이어도_antigravity가_본다,
               test_초안_실패여도_antigravity가_마무리한다,
               test_기존_초안_재사용과_실패_보존,
               test_diff를_못_읽으면_결정적이다,
               test_설계된_스킵, test_선언부, test_main_이_실제로_돈다,
               test_grounding_머리말):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
