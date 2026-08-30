"""워크플로우 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_work.py

[중요] 지키는 불변식 (PLAN §4.2, plan v5 C.1/C.2):
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
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


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
    print("\n[1] 3-tier 규약 (#319 — 계층형, 사용자 결정 ⓐ)")
    check("base", bn.base_branch("w9") == "task/w9/base")
    check("durable", bn.durable_branch("w9", "task_5") == "task/w9/task_5")
    check("attempt", bn.attempt_branch("w9", "task_5", "HV0I6DL", "20260808_120000")
          == "attempt/w9/task_5/HV0I6DL/20260808_120000")
    check("durable 판별", bn.is_durable("task/w9/task_5") and not bn.is_durable("attempt/x/y/z"))
    check("attempt 판별", bn.is_attempt("attempt/x/y/z") and not bn.is_attempt("task/w9/task_5"))
    check("base 판별", bn.is_base("task/w9/base") and not bn.is_base("task/w9/task_5"))
    check("glob", bn.attempt_glob("w9", "task_5") == "attempt/w9/task_5/*")
    check("work glob (base + 조각 전부)", bn.work_glob("w9") == "task/w9/*")
    # [중요] `#317` 실측: `task/W` 와 `task/W/T` 는 공존 불가라 작업 브랜치가 `…/base` 여야 한다.
    #    그래서 `base` 는 task_id 로 쓸 수 없다 — 통과시키면 둘이 같은 이름이 된다.
    check("[중요] task_id 로 'base' 는 거부",
          _raises(lambda: bn.durable_branch("w9", "base"), bn.BranchNameError))
    check("[중요] 작업 브랜치는 durable 로 파싱되지 않는다",
          bn.parse_durable("task/w9/base") is None)

    print("\n[2] [중요] zombie race 가 구조적으로 성립하지 않는다")
    a = bn.attempt_branch("w9", "task_5", "HV0I6DL", "t1")     # 작업장 A
    b = bn.attempt_branch("w9", "task_5", "JFVS693", "t2")     # 재배정된 B
    check("서로 다른 ref", a != b, f"{a} vs {b}")
    check("둘 다 durable 이 아니다", not bn.is_durable(a) and not bn.is_durable(b))
    check("같은 작업장 재시도도 갈린다",
          bn.attempt_branch("w9", "task_5", "A", "t1") != bn.attempt_branch("w9", "task_5", "A", "t2"))
    check("같은 glob 으로 일괄 정리된다",
          bn.parse_attempt(a)["task_id"] == bn.parse_attempt(b)["task_id"] == "task_5")

    print("\n[3] 파싱 왕복")
    got = bn.parse_attempt(a)
    check("필드", got == {"work_id": "w9", "task_id": "task_5",
                          "workshop": "HV0I6DL", "ts": "t1"}, str(got))
    check("durable 파싱", bn.parse_durable("task/w9/task_5")
          == {"work_id": "w9", "task_id": "task_5"})
    check("base 파싱", bn.parse_base("task/w9/base") == "w9")
    # [중요] **읽기만 호환** (사용자 결정 2026-08-27) — origin 에 옛 한 칸짜리가 실재한다
    #    (`task/62efc6a6`·`task/6ff986ed`). 모르는 격으로 두면 정리에서 조용히 빠진다.
    check("[중요] 옛 한 칸짜리 durable 도 읽는다",
          bn.parse_durable("task/62efc6a6")
          == {"work_id": None, "task_id": "62efc6a6", "legacy": True})
    check("[중요] 옛 4토큰 attempt 도 읽는다",
          (bn.parse_attempt("attempt/t1/HV/ts") or {}).get("legacy") is True)
    check("[주의] 쓰기는 계층형뿐 — 옛 모양을 만드는 함수는 없다",
          bn.durable_branch("w9", "t1").count("/") == 2)
    for bad in ("attempt/a/b", "attempt/a/b/c/d/e", "", "쓰레기", None):
        check(f"  attempt 아님: {bad!r}", bn.parse_attempt(bad) is None)
    for bad in ("attempt/a/b/c", "task/a/b/c", "", None):
        check(f"  durable 아님: {bad!r}", bn.parse_durable(bad) is None)

    print("\n[4] [중요] 잘못된 식별자를 조용히 고치지 않는다")
    for bad, why in [("", "빈 값"), ("   ", "공백뿐"), ("a/b", "슬래시"),
                     ("a b", "공백"), ("a:b", "콜론"), ("한글", "비ASCII")]:
        try:
            bn.durable_branch("w9", bad)
            check(f"  거부: {why}", False, "통과해 버렸다")
        except bn.BranchNameError:
            check(f"  거부: {why}", True)
        try:
            bn.base_branch(bad)
            check(f"  base 도 거부: {why}", False, "통과해 버렸다")
        except bn.BranchNameError:
            check(f"  base 도 거부: {why}", True)
    check("attempt 도 작업장명을 검사한다",
          _raises(lambda: bn.attempt_branch("w", "t", "a/b", "ts"), bn.BranchNameError))
    check("attempt 도 ts 를 검사한다",
          _raises(lambda: bn.attempt_branch("w", "t", "w", ""), bn.BranchNameError))
    check("앞뒤 공백은 다듬는다 (내용은 안 바꾼다)",
          bn.durable_branch("  w9  ", "  task_5  ") == "task/w9/task_5")

    # ── 매니페스트 ──────────────────────────────────
    print("\n[5] 매니페스트 조립")
    s = FakeSearch([FakeHit("A.md"), FakeHit("B.md", 0.02, "vector", "")])
    # [중요] 규범 번들을 주입한다 — 안 주면 실제 도메인 색인을 찾아가고, 테스트 프로젝트에는
    #    색인이 없어 degraded 가 붙는다. 여기서 재는 것은 **RAG 채널**이다.
    from master.work import norms as nm
    ok_norms = nm.NormBundle(domains=[nm.DomainNorms(
        domain="D", summary="요약", invariants=[{"name": "R", "text": "규칙", "evidence": "X:1"}])])
    # 기준 커밋도 주입한다 — 테스트 프로젝트엔 config.yaml 이 없다. 여기서 재는 것은 RAG 채널이다.
    from master.work import twin_base as tb
    ok_base = tb.Base(commit="a" * 40, branch="task/task_1", exists=True)
    m = mf.build(paths, "task_1", classes=["UManagerBase"], stem="초기화",
                 contracts="Init() 동결", searcher=s, norms=ok_norms, base=ok_base, now=NOW)
    check("온전히 수집", m.ok and m.hits == 2, f"ok={m.ok} hits={m.hits}")
    check("클래스명이 질의 앞에 온다", s.calls[0][0].startswith("UManagerBase"), s.calls[0][0])
    check("stem 도 질의에 들어간다", "초기화" in s.calls[0][0])
    for want in ("task_1", "TestProj", "UManagerBase", "Init() 동결", "A.md", "B.md"):
        check(f"  본문에 {want}", want in m.body)
    check("발췌 없는 히트도 실린다", "B.md" in m.body)
    check("재검색 불필요를 명시", "재검색 불필요" in m.body)

    print("\n[5b] [중요] 골조는 **매니페스트에 없다** — 작업 브랜치에 실물로 있다 (#319)")
    # 종전에는 여기서 `skeleton=` 을 실어 `## 골조` 절을 만들었다. `#319` 완료 조건 3 이
    # 그 절을 뺐다 — 실측(`#317`): 매니페스트 298줄 중 198줄(2/3)이 골조였고, 조각마다 같은
    # 텍스트를 인바운드 토큰으로 실어 보내고 있었다.
    check("[중요] build 는 더 이상 skeleton 인자를 받지 않는다",
          _raises(lambda: mf.build(paths, "t", skeleton="x",
                                   searcher=FakeSearch([]), now=NOW), TypeError))
    ms = mf.build(paths, "t", classes=["UFoo"],
                  searcher=FakeSearch([FakeHit("A.md")]), now=NOW)
    check("골조 절이 없다", "## 골조" not in ms.body)
    check("[중요] 어디에 있는지는 기준 절이 말한다",
          "골조는 이 브랜치에 실물로 있다" in ms.body or "작업 브랜치" in ms.body, ms.body[:400])

    print("\n[5-1] [중요] 소켓 타임아웃도 GenerateError 로 (배치를 크래시시키지 않는다)")
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

    print("\n[5-2] [중요] num_ctx — 주지 않으면 노드가 죽는다 (BC-250 실측)")
    seen = {}

    def _cap(url, payload):
        seen.update(payload)
        return "ok"

    genmod2 = __import__("importlib").import_module("master.work.generate")
    genmod2.call_broker("p", caller=_cap)
    check("기본은 안 넣는다 (코드 생성 경로 불변)", "num_ctx" not in seen["options"])
    genmod2.call_broker("p", num_ctx=4096, caller=_cap)
    check("주면 options 에 실린다", seen["options"]["num_ctx"] == 4096, str(seen["options"]))
    check("  temperature 는 유지", seen["options"]["temperature"] == 0)
    check("  stateless 유지 (context 없음)", "context" not in seen)

    print("\n[6] [중요] 도메인 규범 채널 (소 2.3.1)")
    check("규범 섹션이 있다", "도메인 규범" in m.body)
    check("규범 본문이 실린다", "지켜야 할 규칙" in m.body and "규칙" in m.body)
    check("도메인·항목 수를 센다", m.norm_domains == 1 and m.norm_items == 1,
          f"{m.norm_domains}/{m.norm_items}")
    # [중요] 자리표시자는 사라졌다 — 이 단언이 깨지면 규범 채널이 되돌아간 것이다
    check("[중요] '_미구현_' 자리표시자가 없다", "_미구현" not in m.body)
    m_empty = mf.build(paths, "t0", classes=["UManagerBase"], searcher=s,
                       norms=nm.NormBundle(degraded=["색인 없음"]), now=NOW)
    check("[중요] 규범이 비면 비었다고 본문에 쓴다",
          "규범 grounding 없이" in m_empty.body and not m_empty.ok)

    print("\n[7] [중요] 수집 결손을 숨기지 않는다 (베스트에포트지만 조용하지 않다)")
    m2 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch(exc=RuntimeError("죽음")),
                  now=NOW)
    check("검색 실패해도 매니페스트는 나온다", bool(m2.body))
    check("  ok=False", not m2.ok)
    check("  본문에 경고", "수집이 온전하지 않다" in m2.body and "RuntimeError" in m2.body)

    m3 = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch([]), base=ok_base, now=NOW)
    # [중요] 다른 채널이 결손을 남겨도 이 메시지가 사라지면 안 된다 (2026-08-09 회귀)
    check("결과 0건도 결손으로 표시", not m3.ok and "결과가 없다" in m3.body)
    m3b = mf.build(paths, "t", classes=["UFoo"], searcher=FakeSearch([]), now=NOW)
    # [중요] `#319` — 기준은 트윈 커밋이 아니라 **작업 브랜치**이고, work_id 가 없으면 그 이름을
    #    만들 수 없다. 결손 문구가 바뀌었을 뿐 **채널마다 자기 결손을 센다**는 성질은 그대로다.
    check("[중요] 기준을 못 정해도 '검색 결과가 없다' 는 남는다",
          "결과가 없다" in m3b.body
          and any("작업 브랜치를 정할 수 없다" in d for d in m3b.degraded), m3b.degraded)

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
    print("\n[11b] [중요] 한글 제목이 전부 같은 slug 가 되던 문제")
    from master.task_queue.logic import _slugify  # noqa: E402
    ko = ["워크플로우 복구", "골조 전달", "매니저 초기화"]
    slugs = [_slugify(k) for k in ko]
    check("한글 제목이 갈린다", len(set(slugs)) == 3, str(slugs))
    check("  전부 'work' 가 아니다", all(s != "work" for s in slugs))
    check("순수 ASCII 는 그대로 (기존 work id 호환)",
          _slugify("Add UManagerBase") == "add_umanagerbase")
    check("ASCII+한글 섞임도 갈린다",
          _slugify("Add U 매니저") != _slugify("Add U 테이블"))
    check("[중요] 같은 제목은 여전히 충돌한다 (중복 검출이 요점)",
          _slugify("워크플로우 복구") == _slugify("  워크플로우   복구  "))
    check("빈 제목", _slugify("") == "work")
    check("기호뿐", _slugify("!!!") == "work")

    # ── 등록 ────────────────────────────────────────
    print("\n[12] 명세 검증 — [중요] 절반 등록하고 실패하지 않는다")
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
    # [중요] `#319` 로 호출이 하나 늘었다 — work 생성 → **작업 브랜치 patch** → task ×2.
    #    이름은 work_id 를 받은 뒤에야 만들어지므로 생성 POST 에 실을 수 없다.
    check("work 1회 + patch 1회 + task 2회", len(calls) == 4, str([u for u, _ in calls]))
    check("work_id", got.work_id == "w1")
    check("태스크 2건", len(got.tasks) == 2)
    check("매니페스트가 붙는다", all(t.manifest_path for t in got.tasks))
    check("  디스크에 실재", all(Path(t.manifest_path).is_file() for t in got.tasks))
    check("  task_id 로 읽힌다", mf.read(paths, got.tasks[0].task_id) is not None)

    wp = calls[0][1]
    check("[중요] 3-tier 를 쓴다", wp["distribution_mode"] == "push", str(wp))
    pu, pp = calls[1]
    check("[중요] 작업 브랜치를 큐에 기록한다 (#319)",
          pu.endswith("/works/w1") and pp["target_branch"] == "task/w1/base", f"{pu} {pp}")
    check("  patch 도 프로젝트 스탬프를 싣는다 (#257)", pp.get("project") == paths.name, str(pp))
    check("  결과에 작업 브랜치가 실린다", got.base_branch == "task/w1/base", got.base_branch)
    tp = calls[2][1]
    check("task_data 에 감사 사본이 남는다", tp["task_data"]["skeleton"] == "class UManagerBase {};")
    check("[중요] 골조는 **매니페스트로 가지 않는다** (#319 — 작업 브랜치에 실물로 있다)",
          "class UManagerBase {};" not in (mf.read(paths, got.tasks[0].task_id) or ""))
    check("동결 계약이 실린다", tp["task_data"]["contracts"] == "Init() 동결")
    check("능력 라우팅", tp["requires"] == ["ue5"])
    check("[중요] 저장소를 만지는 필드가 없다",
          not any(k in tp for k in ("branch", "commit", "repo_path")), str(sorted(tp)))
    check("등록 요약", "2/2" in got.summary(), got.summary())

    print("\n[14] 부분 실패를 숨기지 않는다")
    def flaky(url, payload):
        if url.endswith("/works"):
            return {"work_id": "w2"}
        if "/works/" in url:                 # `#319` 작업 브랜치 patch
            return {"ok": True}
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

    print("\n[16-b] `require_base` 기본값은 **off** — `#336` ① (사용자 결정 2026-08-30)")
    # [중요] 종전 기본값(`poster is None`)은 실전에서 항상 True 였고, 그것이 `#317` ①
    #    (등재를 0번으로)과 정면으로 부딪혔다 — 브랜치 이름이 `task/<work_id>/base` 라
    #    work_id 를 받은 뒤에야 생기므로 등재 시점에 base 는 **있을 수 없다.**
    #    부재 판정을 없앤 것이 아니라 파견·통합(`#331`)으로 자리를 옮겼다.
    from master.work import register as _reg
    seen = []
    _orig_bs = _reg.base_status
    _reg.base_status = lambda *a, **k: seen.append(k.get("branch") or a) or _orig_bs(*a, **k)
    try:
        seen.clear()
        register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                      target_repo="r", poster=poster, searcher=FakeSearch([]))
        check("[중요] 기본값에서 base 를 확인하지 않는다 (등재는 기록이다)", not seen, str(seen))

        seen.clear()
        try:
            register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                          target_repo="r", poster=poster, searcher=FakeSearch([]),
                          require_base=True)
        except Exception:                                   # noqa: BLE001
            pass                    # 트윈이 없는 테스트 환경이라 거절/예외 어느 쪽이든 좋다
        check("[주의] 명시하면 종전대로 확인한다 — 게이트를 없앤 것이 아니다", bool(seen))
    finally:
        _reg.base_status = _orig_bs

    print("\n[16-c] `#336` ③ — 등재가 죽으면 **반쪽 work 를 남기지 않는다**")
    # [중요] 실측 2026-08-30: `.33` 첫 실전 등재가 `manifest.build` 에서 예외로 죽어
    #    `total=1`(specs 는 4) 인 work 이 `in_progress` 로 남았고, 다음 세션이 그것을
    #    「이미 등재돼 있다」로 읽어 판단이 흐려졌다. 큐엔 삭제 API 가 없으니 **종결**시킨다.
    seen_patch = []

    def poster_boom(url, payload):
        seen_patch.append((url, payload))
        if url.endswith("/works"):
            return {"work_id": "wboom"}
        raise RuntimeError("태스크 등록이 죽었다")

    try:
        register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                      target_repo="r", poster=poster_boom, searcher=FakeSearch([]))
        check("[중요] 죽으면 예외를 올린다", False, "조용히 통과해버렸다")
    except Exception as e:                                  # noqa: BLE001
        check("[중요] 죽으면 예외를 올린다", True)
        check("[중요] 사람에게 종결 사실을 말한다", "cancelled" in str(e), str(e)[:160])
    cancels = [p for _u, p in seen_patch if p.get("merge_status") == "cancelled"]
    check("[중요] 실패한 work 를 cancelled 로 종결한다", len(cancels) == 1, str(seen_patch)[:200])
    if cancels:
        check("[주의] 사유를 남긴다",
              "등재 실패" in str(cancels[0].get("review_decision") or ""), str(cancels[0]))

    print("\n[16-d] 매니페스트 예외는 **등록을 죽이지 않는다** (베스트에포트가 계약이다)")
    # [중요] 주석은 「베스트에포트」였는데 `try` 가 없었다 — 그래서 `contracts` 가 리스트일 때
    #    `mf.build` 의 `contracts.strip()` 이 AttributeError 로 등록 전체를 죽였다.
    from master.work import register as _r2
    _orig = _r2._build_manifest_and_carry
    _r2._build_manifest_and_carry = lambda *a, **k: (_ for _ in ()).throw(
        AttributeError("'list' object has no attribute 'strip'"))
    try:
        got = register_work("t", [TaskSpec(stem="A", classes=["U"]),
                                  TaskSpec(stem="B", classes=["V"])],
                            paths=paths, target_repo="r", poster=poster,
                            searcher=FakeSearch([]))
        check("[중요] 매니페스트가 죽어도 태스크는 전부 등록된다", len(got.tasks) == 2, str(got.tasks))
        check("[중요] 결손을 결과에 싣는다",
              all(t.manifest_degraded for t in got.tasks), str(got.tasks)[:200])
        check("요약에 드러난다", "결손" in got.summary(), got.summary())
    finally:
        _r2._build_manifest_and_carry = _orig

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
    check("[중요] 중간 펜스는 남긴다 (층2 가 잡아야 한다)", F in code and not st, code)
    check("빈 입력", strip_fence("") == ("", False))

    print("\n[18] 프롬프트 — 매니페스트를 싣고 동결을 명시한다")
    pr = build_prompt(manifest_body="## 골조\nclass UFoo;", instruction="Init 구현",
                      target_file="Foo.cpp")
    check("매니페스트가 통째로 실린다", "class UFoo;" in pr)
    check("[중요] 동결을 명시", "FROZEN" in pr)
    check("재검색 금지를 명시", "do not search" in pr)
    check("펜스 금지를 명시", "No markdown fences" in pr)
    check("대상 파일", "Foo.cpp" in pr)
    check("지시가 실린다", "Init 구현" in pr)
    # [중요] 소 3.5.7 (`#183`) — 원전 금지 3종. 이유가 **UE 특유**라 리뷰뿐 아니라 생성에도 걸린다:
    #    Blueprint 에셋이 C++ 상속과 UPROPERTY **이름**을 직렬화해 들고 있고, 그 의존은
    #    코드에 없다(*"LLM 은 코드만 분석 가능"*). 룰 1(동결)이 리네이밍을 **일부**만 막는다.
    check("[중요] 리네이밍 금지 + **이유**(Blueprint 에셋)",
          "rename" in pr.lower() and "Blueprint" in pr, pr[:0])
    check("[중요] 상속 구조 변경 금지", "inheritance" in pr.lower())
    check("[중요] 모듈 간 이동 금지 (동결로는 못 막는 자리)",
          "move code between modules" in pr.lower())
    check("에셋을 코드에서 볼 수 없다는 사실을 알린다",
          "cannot see those assets" in pr.lower() or "asset references" in pr.lower())

    print("\n[19] [중요] 매니페스트가 없으면 생성하지 않는다 (grounding 0 = 환각 조건)")
    gp = ProjectPaths(name="G", root=tmp / "G")
    try:
        generate(gp, "없는태스크", instruction="x")
        check("거부", False, "생성해 버렸다")
    except GenerateError as e:
        check("거부", "매니페스트가 없다" in str(e), str(e))
        check("  이유를 말한다", "grounding" in str(e))

    print("\n[20] 생성 → 층2 → 인계")
    mf.write(gp, mf.build(gp, "t1", classes=["UFoo"],
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
    check("[중요] stateless — context 를 안 보낸다", "context" not in seen, str(sorted(seen)))
    check("temperature=0", seen["options"]["temperature"] == 0)
    check("think=False (35B 토큰 낭비 방지)", seen["think"] is False)
    check("stream=False", seen["stream"] is False)

    print("\n[21] [중요] fail-closed — 층2 를 못 넘으면 인계하지 않는다")
    bad = Verdict(approved=False, failure=None, findings=["세미콜론 누락"])
    d = dispatch(gp, "t1", instruction="x", caller=caller, verifier=lambda f: bad)
    check("차단", not d.ok and d.verdict.blocked)
    check("  코드는 들고 있다 (진단용)", bool(d.code))
    check("  요약에 드러난다", "차단" in d.summary(), d.summary())

    d = dispatch(gp, "t1", instruction="x", caller=lambda u, p: "",
                 verifier=lambda f: ok_v)
    check("빈 생성 = 차단", not d.ok and "비었다" in d.error, d.error)

    d = dispatch(gp, "t1", instruction="x", caller=caller, verifier=lambda f: None)
    check("[중요] verdict 가 없으면 통과가 아니다", not d.ok)

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

    # ── 대상 파일 (#65) ─────────────────────────────
    print("\n[대상 파일] [중요] 매니페스트가 어느 파일인지 싣는가")
    mt = mf.build(paths, "tf1", classes=["UFoo"],
                  target_files=["Source/A/Foo.h", "Source/A/Foo.cpp"],
                  searcher=None, base=None)
    check("대상 파일 절이 있다", "## 대상 파일" in mt.body, mt.body[:200])
    check("파일이 다 실린다",
          "Source/A/Foo.h" in mt.body and "Source/A/Foo.cpp" in mt.body)
    # [중요] 사용자: "클래스 별로 분리하는건 분산 작업시 충돌을 방지하기 위해서"
    check("[중요] 목록 밖 금지를 못박는다", "이 목록 밖은 건드리지 않는다" in mt.body)
    check("[중요] 파일이 갈라지면 안 되는 이유를 적는다", "두 워커가 같은 곳을 고친다" in mt.body)
    empty = mf.build(paths, "tf2", classes=["UFoo"], searcher=None, base=None)
    check("파일이 없으면 절을 안 만든다", "## 대상 파일" not in empty.body)

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
