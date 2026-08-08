"""워크플로우 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_work.py

🔴 지키는 불변식 (PLAN §4.2, plan v5 C.1/C.2):
   1. **두 작업장이 같은 ref 에 push 하지 않는다** — zombie race 가 구조적으로 성립 불가
   2. **식별자를 조용히 정규화하지 않는다** — 이름이 곧 정체성이다
   3. **매니페스트는 1회 수집** — 작업장은 읽기만 한다
   4. **수집 결손을 숨기지 않는다** — grounding 없이 일하는 줄 알아야 한다
   5. **매니페스트 쓰기는 원자적** — 반쯤 쓰인 것을 읽으면 안 된다
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths  # noqa: E402
from master.work import branch_names as bn  # noqa: E402
from master.work import manifest as mf  # noqa: E402
from master.work.register import (  # noqa: E402
    RegisterError, TaskSpec, register_work,
)
from master.work.generate import (  # noqa: E402
    GenerateError, build_prompt, dispatch, generate, strip_fence,
)
from master.verdict import Verdict  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


class FakeSearch:
    def __init__(self, hits=(), exc=None):
        self._hits = list(hits)
        self._exc = exc
        self.calls = []

    def search(self, query, limit=8):
        self.calls.append((query, limit))
        if self._exc:
            raise self._exc
        return self._hits[:limit]


class FakeHit:
    def __init__(self, file_id, rrf=0.03, source="vector+bm25", excerpt="본문"):
        self.file_id, self.rrf_score, self.source, self.excerpt = file_id, rrf, source, excerpt


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-work-test-"))
    paths = ProjectPaths(name="TestProj", root=tmp / "TestProj")

    # ── 브랜치 규약 ─────────────────────────────────
    print("\n[1] 2-tier 규약")
    check("durable", bn.durable_branch("task_5") == "task/task_5")
    check("attempt", bn.attempt_branch("task_5", "HV0I6DL", "20260808_120000")
          == "attempt/task_5/HV0I6DL/20260808_120000")
    check("durable 판별", bn.is_durable("task/task_5") and not bn.is_durable("attempt/x/y/z"))
    check("attempt 판별", bn.is_attempt("attempt/x/y/z") and not bn.is_attempt("task/task_5"))
    check("glob", bn.attempt_glob("task_5") == "attempt/task_5/*")

    print("\n[2] 🔴 zombie race 가 구조적으로 성립하지 않는다")
    a = bn.attempt_branch("task_5", "HV0I6DL", "t1")     # 작업장 A
    b = bn.attempt_branch("task_5", "JFVS693", "t2")     # 재배정된 B
    check("서로 다른 ref", a != b, f"{a} vs {b}")
    check("둘 다 durable 이 아니다", not bn.is_durable(a) and not bn.is_durable(b))
    check("같은 작업장 재시도도 갈린다",
          bn.attempt_branch("task_5", "A", "t1") != bn.attempt_branch("task_5", "A", "t2"))
    check("같은 glob 으로 일괄 정리된다",
          bn.parse_attempt(a)["task_id"] == bn.parse_attempt(b)["task_id"] == "task_5")

    print("\n[3] 파싱 왕복")
    got = bn.parse_attempt(a)
    check("필드", got == {"task_id": "task_5", "workshop": "HV0I6DL", "ts": "t1"}, str(got))
    check("durable 파싱", bn.parse_durable("task/task_5") == "task_5")
    for bad in ("task/task_5", "attempt/a/b", "attempt/a/b/c/d", "", "쓰레기", None):
        check(f"  attempt 아님: {bad!r}", bn.parse_attempt(bad) is None)
    for bad in ("attempt/a/b/c", "task/a/b", "", None):
        check(f"  durable 아님: {bad!r}", bn.parse_durable(bad) is None)

    print("\n[4] 🔴 잘못된 식별자를 조용히 고치지 않는다")
    for bad, why in [("", "빈 값"), ("   ", "공백뿐"), ("a/b", "슬래시"),
                     ("a b", "공백"), ("a:b", "콜론"), ("한글", "비ASCII")]:
        try:
            bn.durable_branch(bad)
            check(f"  거부: {why}", False, "통과해 버렸다")
        except bn.BranchNameError:
            check(f"  거부: {why}", True)
    check("attempt 도 작업장명을 검사한다",
          _raises(lambda: bn.attempt_branch("t", "a/b", "ts"), bn.BranchNameError))
    check("attempt 도 ts 를 검사한다",
          _raises(lambda: bn.attempt_branch("t", "w", ""), bn.BranchNameError))
    check("앞뒤 공백은 다듬는다 (내용은 안 바꾼다)",
          bn.durable_branch("  task_5  ") == "task/task_5")

    # ── 매니페스트 ──────────────────────────────────
    print("\n[5] 매니페스트 조립")
    s = FakeSearch([FakeHit("A.md"), FakeHit("B.md", 0.02, "vector", "")])
    m = mf.build(paths, "task_1", classes=["UManagerBase"], stem="초기화",
                 contracts="Init() 동결", searcher=s, now=NOW)
    check("온전히 수집", m.ok and m.hits == 2, f"ok={m.ok} hits={m.hits}")
    check("클래스명이 질의 앞에 온다", s.calls[0][0].startswith("UManagerBase"), s.calls[0][0])
    check("stem 도 질의에 들어간다", "초기화" in s.calls[0][0])
    for want in ("task_1", "TestProj", "UManagerBase", "Init() 동결", "A.md", "B.md"):
        check(f"  본문에 {want}", want in m.body)
    check("발췌 없는 히트도 실린다", "B.md" in m.body)
    check("재검색 불필요를 명시", "재검색 불필요" in m.body)

    print("\n[5b] 🔴 골조는 매니페스트로 간다 (task_data 는 전송 수단이 아니다)")
    ms = mf.build(paths, "t", classes=["UFoo"], skeleton="class UFoo { void Init(); };",
                  searcher=FakeSearch([FakeHit("A.md")]), now=NOW)
    check("골조 섹션", "## 골조" in ms.body)
    check("본문이 실린다", "class UFoo { void Init(); };" in ms.body)
    check("cpp 펜스", "```cpp" in ms.body)
    check("골조 없으면 섹션도 없다", "## 골조" not in m.body)

    print("\n[5-1] 🔴 소켓 타임아웃도 GenerateError 로 (배치를 크래시시키지 않는다)")
    import urllib.error as _ue

    def _timeout(*a, **kw):
        raise TimeoutError("timed out")

    def _urlerr(*a, **kw):
        raise _ue.URLError("refused")

    def _badjson(*a, **kw):
        raise ValueError("Expecting value: line 1 column 1")

    import importlib
    genmod = importlib.import_module("master.work.generate")
    for label, fn in (("소켓 타임아웃", _timeout), ("연결 실패", _urlerr),
                      ("JSON 파싱 실패", _badjson)):
        real = genmod.urllib.request.urlopen
        genmod.urllib.request.urlopen = fn
        try:
            genmod.call_broker("x")
            check(f"{label} → GenerateError", False, "예외 없음")
        except GenerateError as e:
            check(f"{label} → GenerateError", True)
            check(f"  사유가 남는다 ({label})", len(str(e)) > 8, str(e))
        except Exception as e:
            check(f"{label} → GenerateError", False, f"{type(e).__name__}: {e}")
        finally:
            genmod.urllib.request.urlopen = real

    print("\n[6] 🔴 온톨로지가 없다는 사실을 숨기지 않는다")
    check("규범 섹션이 있다", "도메인 규범" in m.body)
    check("미구현이라 적혀 있고 소분류를 가리킨다",
          "미구현" in m.body and "2.3.1" in m.body)

    print("\n[7] 🔴 수집 결손을 숨기지 않는다 (베스트에포트지만 조용하지 않다)")
    m2 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch(exc=RuntimeError("죽음")),
                  now=NOW)
    check("검색 실패해도 매니페스트는 나온다", bool(m2.body))
    check("  ok=False", not m2.ok)
    check("  본문에 경고", "수집이 온전하지 않다" in m2.body and "RuntimeError" in m2.body)

    m3 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch([]), now=NOW)
    check("결과 0건도 결손으로 표시", not m3.ok and "결과가 없다" in m3.body)

    m4 = mf.build(paths, "t", searcher=FakeSearch([FakeHit("X.md")]), now=NOW)
    check("질의를 못 만들면 검색하지 않는다", not m4.ok and "질의를 만들 수 없" in m4.body)

    m5 = mf.build(paths, "t", classes=["UFoo"], searcher=None, now=NOW)
    check("검색기 없음도 기록", not m5.ok and "검색기가 없다" in m5.body)

    print("\n[8] 히트 수 제한과 발췌 길이")
    many = FakeSearch([FakeHit(f"{i}.md", excerpt="가" * 500) for i in range(20)])
    m6 = mf.build(paths, "t", classes=["UFoo"], hits=3, searcher=many, now=NOW)
    check("limit 이 전달된다", many.calls[0][1] == 3, str(many.calls[0]))
    check("히트 수", m6.hits == 3)
    check("발췌가 잘린다", "…" in m6.body and "가" * 200 not in m6.body)

    print("\n[9] 저장 — 원자적, 파생물 위치")
    p = mf.write(paths, m)
    check("경로", p == paths.root / "manifests" / "task_1.md", str(p))
    check("트윈 파생물 아래", p.parent == paths.manifests)
    check("읽힌다", mf.read(paths, "task_1") == m.body)
    check("임시 파일이 안 남는다", not list(p.parent.glob("*.tmp")))
    check("없는 것은 None (빈 문자열과 구분)", mf.read(paths, "없는거") is None)
    p2 = mf.write(paths, mf.build(paths, "task_1", classes=["UBar"],
                                  searcher=FakeSearch([FakeHit("C.md")]), now=NOW))
    check("덮어쓰기", p2 == p and "C.md" in mf.read(paths, "task_1"))

    print("\n[10] 경로 안전")
    check("슬래시가 디렉토리를 벗어나지 못한다",
          mf.manifest_path(paths, "a/b").parent == paths.manifests,
          str(mf.manifest_path(paths, "a/b")))
    check("빈 task_id 거부", _raises(lambda: mf.manifest_path(paths, "  "), mf.ManifestError))

    print("\n[11] collect() — 검색기를 못 열어도 등록을 막지 않는다")
    broken = mf._BrokenSearcher(OSError("DB 없음"))
    m7 = mf.build(paths, "t9", classes=["UFoo"], searcher=broken, now=NOW)
    check("예외가 새어 나오지 않는다", not m7.ok)
    check("원인이 기록된다", "OSError" in m7.body and "DB 없음" in m7.body)

    # ── 큐 slug (워크플로우가 드러낸 잠복 버그) ──────
    print("\n[11b] 🔴 한글 제목이 전부 같은 slug 가 되던 문제")
    from master.task_queue.logic import _slugify  # noqa: E402
    ko = ["워크플로우 복구", "골조 전달", "매니저 초기화"]
    slugs = [_slugify(k) for k in ko]
    check("한글 제목이 갈린다", len(set(slugs)) == 3, str(slugs))
    check("  전부 'work' 가 아니다", all(s != "work" for s in slugs))
    check("순수 ASCII 는 그대로 (기존 work id 호환)",
          _slugify("Add UManagerBase") == "add_umanagerbase")
    check("ASCII+한글 섞임도 갈린다",
          _slugify("Add U 매니저") != _slugify("Add U 테이블"))
    check("🔴 같은 제목은 여전히 충돌한다 (중복 검출이 요점)",
          _slugify("워크플로우 복구") == _slugify("  워크플로우   복구  "))
    check("빈 제목", _slugify("") == "work")
    check("기호뿐", _slugify("!!!") == "work")

    # ── 등록 ────────────────────────────────────────
    print("\n[12] 명세 검증 — 🔴 절반 등록하고 실패하지 않는다")
    calls = []

    def poster(url, payload):
        calls.append((url, payload))
        if url.endswith("/works"):
            return {"work_id": "w1"}
        return {"task_id": f"task_{len(calls) - 1}"}

    def reg(specs, **kw):
        return register_work("제목", specs, paths=paths, target_repo="r",
                             poster=poster, searcher=FakeSearch([FakeHit("A.md")]), **kw)

    for bad, why in [
        ([], "태스크 0개"),
        ([TaskSpec(stem="")], "stem 비었음"),
        ([TaskSpec(stem="A")], "classes·target_file 둘 다 없음"),
        ([TaskSpec(stem="A", classes=["U"]), TaskSpec(stem="A", classes=["V"])], "stem 중복"),
    ]:
        n = len(calls)
        check(f"  거부: {why}", _raises(lambda: reg(bad), RegisterError))
        check(f"    HTTP 호출 0건 (반쪽 work 를 안 남긴다)", len(calls) == n, str(len(calls) - n))
    check("빈 title 거부",
          _raises(lambda: register_work("", [TaskSpec(stem="A", classes=["U"])],
                                        paths=paths, target_repo="r", poster=poster),
                  RegisterError))

    print("\n[13] 정상 등록")
    calls.clear()
    got = reg([TaskSpec(stem="ManagerBase", classes=["UManagerBase"], contracts="Init() 동결",
                        skeleton="class UManagerBase {};", requires=["ue5"]),
               TaskSpec(stem="TableData", classes=["UManager_TableData"])])
    check("ok", got.ok, got.summary())
    check("work 1회 + task 2회", len(calls) == 3, str(len(calls)))
    check("work_id", got.work_id == "w1")
    check("태스크 2건", len(got.tasks) == 2)
    check("매니페스트가 붙는다", all(t.manifest_path for t in got.tasks))
    check("  디스크에 실재", all(Path(t.manifest_path).is_file() for t in got.tasks))
    check("  task_id 로 읽힌다", mf.read(paths, got.tasks[0].task_id) is not None)

    wp = calls[0][1]
    check("🔴 2-tier 를 쓴다", wp["distribution_mode"] == "push", str(wp))
    tp = calls[1][1]
    check("task_data 에도 남는다 (감사 기록)", tp["task_data"]["skeleton"] == "class UManagerBase {};")
    check("🔴 골조가 매니페스트에 도달한다",
          "class UManagerBase {};" in (mf.read(paths, got.tasks[0].task_id) or ""))
    check("동결 계약이 실린다", tp["task_data"]["contracts"] == "Init() 동결")
    check("능력 라우팅", tp["requires"] == ["ue5"])
    check("🔴 저장소를 만지는 필드가 없다",
          not any(k in tp for k in ("branch", "commit", "repo_path")), str(sorted(tp)))
    check("등록 요약", "2/2" in got.summary(), got.summary())

    print("\n[14] 부분 실패를 숨기지 않는다")
    def flaky(url, payload):
        if url.endswith("/works"):
            return {"work_id": "w2"}
        if payload["stem"] == "Bad":
            raise RegisterError("HTTP 500")
        return {"task_id": "task_ok"}

    got2 = register_work("t", [TaskSpec(stem="Good", classes=["U"]),
                               TaskSpec(stem="Bad", classes=["V"])],
                         paths=paths, target_repo="r", poster=flaky,
                         searcher=FakeSearch([FakeHit("A.md")]))
    check("ok=False", not got2.ok)
    check("실패 1건", len(got2.failed) == 1 and got2.failed[0].stem == "Bad")
    check("성공분은 살아 있다", got2.tasks[0].ok)
    check("요약에 실패 표시", "실패 1건" in got2.summary(), got2.summary())

    print("\n[15] task_id 를 못 받으면 실패로 잡는다")
    got3 = register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                         target_repo="r", searcher=FakeSearch([]),
                         poster=lambda u, p: {"work_id": "w3"} if u.endswith("/works") else {})
    check("ok=False", not got3.ok and "task_id" in got3.tasks[0].error)
    check("매니페스트도 안 만든다", not got3.tasks[0].manifest_path)

    print("\n[16] 매니페스트 결손이 등록을 막지 않는다 (베스트에포트)")
    got4 = register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                         target_repo="r", poster=poster,
                         searcher=FakeSearch(exc=RuntimeError("검색 죽음")))
    check("등록은 성공", got4.ok, got4.summary())
    check("결손이 기록된다", bool(got4.tasks[0].manifest_degraded))
    check("요약에 드러난다", "결손" in got4.summary(), got4.summary())

    # ── 생성 → 층2 → 인계 ───────────────────────────
    F = chr(96) * 3
    print("\n[17] 마크다운 펜스 — §4.4 가 실측한 coder 모델의 유일한 결함")
    for label, src, want_code, want_stripped in [
        ("언어 표시 있음", f"{F}cpp\nvoid A(){{}}\n{F}", "void A(){}", True),
        ("언어 표시 없음", f"{F}\nvoid A(){{}}\n{F}", "void A(){}", True),
        ("앞뒤 공백까지", f"\n  {F}cpp\nvoid A(){{}}\n{F}  \n", "void A(){}", True),
        ("펜스 없음", "void A(){}", "void A(){}", False),
    ]:
        code, st = strip_fence(src)
        check(f"  {label}", code == want_code and st == want_stripped, f"{code!r} st={st}")
    mid = f"void A(){{}}\n{F}cpp\nvoid B(){{}}"
    code, st = strip_fence(mid)
    check("🔴 중간 펜스는 남긴다 (층2 가 잡아야 한다)", F in code and not st, code)
    check("빈 입력", strip_fence("") == ("", False))

    print("\n[18] 프롬프트 — 매니페스트를 싣고 동결을 명시한다")
    pr = build_prompt(manifest_body="## 골조\nclass UFoo;", instruction="Init 구현",
                      target_file="Foo.cpp")
    check("매니페스트가 통째로 실린다", "class UFoo;" in pr)
    check("🔴 동결을 명시", "FROZEN" in pr)
    check("재검색 금지를 명시", "do not search" in pr)
    check("펜스 금지를 명시", "No markdown fences" in pr)
    check("대상 파일", "Foo.cpp" in pr)
    check("지시가 실린다", "Init 구현" in pr)

    print("\n[19] 🔴 매니페스트가 없으면 생성하지 않는다 (grounding 0 = 환각 조건)")
    gp = ProjectPaths(name="G", root=tmp / "G")
    try:
        generate(gp, "없는태스크", instruction="x")
        check("거부", False, "생성해 버렸다")
    except GenerateError as e:
        check("거부", "매니페스트가 없다" in str(e), str(e))
        check("  이유를 말한다", "grounding" in str(e))

    print("\n[20] 생성 → 층2 → 인계")
    mf.write(gp, mf.build(gp, "t1", classes=["UFoo"], skeleton="class UFoo{};",
                          searcher=FakeSearch([FakeHit("A.md")]), now=NOW))
    seen = {}

    def caller(url, payload):
        seen.update(payload)
        return f"{F}cpp\nvoid UFoo::Init(){{}}\n{F}"

    ok_v = Verdict(approved=True, failure=None)
    d = dispatch(gp, "t1", instruction="Init 구현", target_file="Foo.cpp",
                 caller=caller, verifier=lambda files: ok_v)
    check("ok", d.ok, d.summary())
    check("펜스가 벗겨진 코드", d.code == "void UFoo::Init(){}", repr(d.code))
    check("  벗겼다고 알린다", any("펜스" in n for n in d.notes), str(d.notes))
    check("🔴 stateless — context 를 안 보낸다", "context" not in seen, str(sorted(seen)))
    check("temperature=0", seen["options"]["temperature"] == 0)
    check("think=False (35B 토큰 낭비 방지)", seen["think"] is False)
    check("stream=False", seen["stream"] is False)

    print("\n[21] 🔴 fail-closed — 층2 를 못 넘으면 인계하지 않는다")
    bad = Verdict(approved=False, failure=None, findings=["세미콜론 누락"])
    d = dispatch(gp, "t1", instruction="x", caller=caller, verifier=lambda f: bad)
    check("차단", not d.ok and d.verdict.blocked)
    check("  코드는 들고 있다 (진단용)", bool(d.code))
    check("  요약에 드러난다", "차단" in d.summary(), d.summary())

    d = dispatch(gp, "t1", instruction="x", caller=lambda u, p: "",
                 verifier=lambda f: ok_v)
    check("빈 생성 = 차단", not d.ok and "비었다" in d.error, d.error)

    d = dispatch(gp, "t1", instruction="x", caller=caller, verifier=lambda f: None)
    check("🔴 verdict 가 없으면 통과가 아니다", not d.ok)

    def dead(url, payload):
        raise GenerateError("브로커에 닿지 않는다")

    d = dispatch(gp, "t1", instruction="x", caller=dead)
    check("브로커 장애 = 차단", not d.ok and "닿지 않는다" in d.error)
    check("  층2 를 부르지 않는다", d.verdict is None)

    print("\n[22] 층2 에 넘기는 파일명")
    names = []
    dispatch(gp, "t1", instruction="x", target_file="Bar.cpp", caller=caller,
             verifier=lambda f: (names.append(f[0][0]), ok_v)[1])
    check("target_file 을 쓴다", names == ["Bar.cpp"], str(names))
    names.clear()
    dispatch(gp, "t1", instruction="x", caller=caller,
             verifier=lambda f: (names.append(f[0][0]), ok_v)[1])
    check("없으면 task_id 로", names == ["t1.cpp"], str(names))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


def _raises(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
