"""워크플로우 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_work.py

[중요] 지키는 불변식 (PLAN §4.2, plan v5 C.1/C.2):
   1. **두 작업장이 같은 ref 에 push 하지 않는다** — zombie race 가 구조적으로 성립 불가
   2. **식별자를 조용히 정규화하지 않는다** — 이름이 곧 정체성이다
   3. **지시서는 골조 주석** — 작업장은 자기 체크아웃에서 읽는다 (매니페스트 철거 2026-09-02)
   4. **수집 결손을 숨기지 않는다** — grounding 없이 일하는 줄 알아야 한다
   5. **스풀 쓰기는 원자적** — 반쯤 쓰인 것을 읽으면 안 된다
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
                             poster=poster, **kw)

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

    print("\n[12.5] 🔴 등재와 **개선요청**은 다른 호출이다 (사용자 결정 2026-09-05)")
    # 사용자: *"이럴꺼면 기능을 분리하던지. 라운드값으로 최초 처리인지 아니면 2회차 3회차
    #    개선요청인지 구분 못해서 그런거 아니야?"* · *"분산작업 등록과 라운드 값을 받는
    #    분산작업 개선 요청으로 말이야"*.
    # [주의] 종전에는 `register_work(work_id=…)` 가 재활성화로 갈렸다 — 한 입구에 두 뜻이라
    #    라운드를 **상태로 추론**했고, 상태가 예상 밖이면 조용히 틀렸다.
    from master.work.register import improve_work
    check("  🔴 등재는 work_id 를 거절한다 (개선요청으로 보낸다)",
          _raises(lambda: register_work("제목", [TaskSpec(stem="R2", classes=["UR2"])],
                                        paths=paths, target_repo="r", poster=poster,
                                        work_id="20260905_0014_work_682fa5e5"), RegisterError))
    check("  개선요청은 라운드 1을 거절한다 (라운드 1은 등록이다)",
          _raises(lambda: improve_work("20260905_0014_work_682fa5e5",
                                       [TaskSpec(stem="R2", classes=["UR2"])],
                                       round=1, paths=paths, poster=poster), RegisterError))
    calls.clear()
    got_re = improve_work("20260905_0014_work_682fa5e5",
                          [TaskSpec(stem="R2", classes=["UR2"])],
                          round=2, paths=paths, poster=poster, require_base=False)
    check("  🔴 `/works` 를 부르지 않는다 (새 work 없음)",
          not any(u.endswith("/works") for u, _ in calls),
          str([u for u, _ in calls]))
    check("  🔴 **승격이 조각보다 먼저다** — reopen 이 첫 호출이다",
          calls and calls[0][0].endswith("/reopen"), str([u for u, _ in calls]))
    check("  라운드 값을 실어 보낸다 (확인용)", calls and calls[0][1].get("round") == 2,
          str(calls[0][1]) if calls else "")
    check("  그 work 에 조각을 등록한다",
          any("/tasks" in u for u, _ in calls), str([u for u, _ in calls]))
    check("  돌려주는 work_id 가 받은 그것이다", got_re.work_id == "20260905_0014_work_682fa5e5",
          got_re.work_id)
    check("  결과가 라운드를 말한다", got_re.round == 2, str(got_re.round))

    def poster_refuse(url, payload):
        if url.endswith("/reopen"):
            return {"ok": False, "reason": "round_mismatch", "error": "라운드가 어긋난다"}
        return {"work_id": "wX"}

    check("🔴 큐가 라운드를 거절하면 등재로 넘어가지 않는다",
          _raises(lambda: improve_work("W1", [TaskSpec(stem="R2", classes=["UR2"])],
                                       round=2, paths=paths, poster=poster_refuse),
                  RegisterError))

    def poster_boom_task(url, payload):
        if url.endswith("/reopen"):
            return {"ok": True, "round": 2, "target_branch": "task/W1/base"}
        if "/tasks" in url:
            raise RuntimeError("태스크 등록이 죽었다")
        return {}

    check("[중요] 개선요청이 실패해도 그 work 을 **종결시키지 않는다** "
          "(지난 라운드 산출물까지 닫힌다)",
          _raises(lambda: improve_work("W1", [TaskSpec(stem="R2", classes=["UR2"])],
                                       round=2, paths=paths, poster=poster_boom_task,
                                       require_base=False), RegisterError))
    check("  그 실패에 `cancelled` 를 쓰지 않는다",
          not any(p.get("merge_status") == "cancelled" for _, p in calls),
          str([p for _, p in calls if isinstance(p, dict) and p.get("merge_status")]))

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

    wp = calls[0][1]
    check("[중요] 3-tier 를 쓴다", wp["distribution_mode"] == "push", str(wp))
    pu, pp = calls[1]
    check("[중요] 작업 브랜치를 큐에 기록한다 (#319)",
          pu.endswith("/works/w1") and pp["target_branch"] == "task/w1/base", f"{pu} {pp}")
    check("  patch 도 프로젝트 스탬프를 싣는다 (#257)", pp.get("project") == paths.name, str(pp))
    check("  결과에 작업 브랜치가 실린다", got.base_branch == "task/w1/base", got.base_branch)
    tp = calls[2][1]
    check("task_data 에 감사 사본이 남는다", tp["task_data"]["skeleton"] == "class UManagerBase {};")
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
                         paths=paths, target_repo="r", poster=flaky)
    check("ok=False", not got2.ok)
    check("실패 1건", len(got2.failed) == 1 and got2.failed[0].stem == "Bad")
    check("성공분은 살아 있다", got2.tasks[0].ok)
    check("요약에 실패 표시", "실패 1건" in got2.summary(), got2.summary())

    print("\n[15] task_id 를 못 받으면 실패로 잡는다")
    got3 = register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                         target_repo="r",
                         poster=lambda u, p: {"work_id": "w3"} if u.endswith("/works") else {})
    check("ok=False", not got3.ok and "task_id" in got3.tasks[0].error)

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
                      target_repo="r", poster=poster)
        check("[중요] 기본값에서 base 를 확인하지 않는다 (등재는 기록이다)", not seen, str(seen))

        seen.clear()
        try:
            register_work("t", [TaskSpec(stem="A", classes=["U"])], paths=paths,
                          target_repo="r", poster=poster,
                          require_base=True)
        except Exception:                                   # noqa: BLE001
            pass                    # 트윈이 없는 테스트 환경이라 거절/예외 어느 쪽이든 좋다
        check("[주의] 명시하면 종전대로 확인한다 — 게이트를 없앤 것이 아니다", bool(seen))
    finally:
        _reg.base_status = _orig_bs

    print("\n[16-c] `#336` ③ — 등재가 죽으면 **반쪽 work 를 남기지 않는다**")
    # [중요] 실측 2026-08-30: `.33` 첫 실전 등재가 예외로 죽어
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
                      target_repo="r", poster=poster_boom)
        check("[중요] 죽으면 예외를 올린다", False, "조용히 통과해버렸다")
    except Exception as e:                                  # noqa: BLE001
        check("[중요] 죽으면 예외를 올린다", True)
        check("[중요] 사람에게 종결 사실을 말한다", "cancelled" in str(e), str(e)[:160])
    cancels = [p for _u, p in seen_patch if p.get("merge_status") == "cancelled"]
    check("[중요] 실패한 work 를 cancelled 로 종결한다", len(cancels) == 1, str(seen_patch)[:200])
    if cancels:
        check("[주의] 사유를 남긴다",
              "등재 실패" in str(cancels[0].get("review_decision") or ""), str(cancels[0]))

    print("\n[16-e] [중요] 등재는 **골조를 만들지 않는다** — 마스터가 LLM 을 부르지 않는다")
    # [중요] 실측 2026-08-30 21:57: `.33` 이 `instruction` 을 실은 명세 5개를 등재하자
    #    마스터가 `claude:opus` 를 **동시 2프로세스**로 돌리기 시작했다. `#317` ①·`#319` 는
    #    골조 제작을 요청자로 옮겼는데 `_fill_skeletons` 가 등재 경로에 남아 있었다.
    #    사용자: *"골조를 니가 왜 만드는데?"* → 제거(사용자 결정 2026-08-30).
    # [주의] **내가 라우트를 만들 때 이걸 확인했어야 했다** — 내 테스트는 `instruction` 없는
    #    명세만 썼고, 그래서 이 경로가 한 번도 안 걸렸다. 첫 실전 페이로드가 밟았다.
    def _probe_skeleton(sink):
        """골조 생성기가 **불렸는지만** 잰다 — 실제 생성은 `test_skeleton` 의 몫이다."""
        from master.work.skeleton import Skeleton

        def fn(_paths, spec):
            sink.append(spec.stem)
            # [주의] `Skeleton.ok` 는 fail-closed 다 — files·pseudo·frozen 셋이 다 있어야
            #    골조로 인정된다. 프로브도 그 계약을 지킨다.
            return Skeleton(stem=spec.stem,
                            files={f: "// [PSEUDO] x\n" for f in spec.files},
                            frozen={"void F()"}, pseudo=1)
        return fn

    called = []
    spec_with_instruction = TaskSpec(stem="A", classes=["UA"], target_file="A.cpp",
                                     instruction="이걸 만들어라")   # skeleton 은 비었다
    got = register_work("t", [spec_with_instruction], paths=paths, target_repo="r",
                        poster=poster,
                        make_skeleton=_probe_skeleton(called))
    check("[중요] 주입하면 돈다 (테스트 자리는 살아 있다)", bool(called), str(called))

    called.clear()
    got = register_work("t", [TaskSpec(stem="B", classes=["UB"], target_file="B.cpp",
                                       instruction="이것도 만들어라")],
                        paths=paths, target_repo="r", poster=poster)
    check("[중요] **기본값에서는 골조를 만들지 않는다** — instruction 이 있어도",
          not called and not got.generated, f"called={called} generated={got.generated}")
    check("등재 자체는 성립한다", got.work_id and len(got.tasks) == 1, got.summary())

    print("\n[16-f] `depends_on` 은 stem 으로 받고 **task_id 로 보낸다** (`#343`)")
    # [중요] 실측 2026-08-30: `.33` 이 `depends_on=['interactable_component']`(stem)로 보냈다.
    #    큐는 `completed = {task_id …}` 와 대조하므로 stem 은 **영원히 안 들어간다** — 세 조각이
    #    조용히 안 풀렸다. 등재 시점엔 task_id 가 없으니 호출자가 쓸 이름은 stem 뿐이다.
    sent = []

    def poster_dep(url, payload):
        sent.append((url, payload))
        if url.endswith("/works"):
            return {"work_id": "wdep"}
        return {"task_id": f"id_{payload.get('stem')}"}

    got = register_work("t", [TaskSpec(stem="A", classes=["UA"]),
                              TaskSpec(stem="B", classes=["UB"], depends_on=["A"])],
                        paths=paths, target_repo="r", poster=poster_dep)
    dep_payload = [p for u, p in sent if u.endswith("/tasks") and p.get("stem") == "B"]
    check("[중요] stem 이 task_id 로 바뀌어 나간다",
          dep_payload and dep_payload[0]["depends_on"] == ["id_A"],
          str(dep_payload[:1]))
    check("등재는 성립한다", got.work_id == "wdep" and len(got.tasks) == 2)

    # [주의] 뒤엣것을 가리키면 거절한다 — 그때는 id 가 아직 없다
    sent.clear()
    got2 = register_work("t", [TaskSpec(stem="A", classes=["UA"], depends_on=["B"]),
                               TaskSpec(stem="B", classes=["UB"])],
                         paths=paths, target_repo="r", poster=poster_dep)
    bad = [t for t in got2.tasks if t.stem == "A"]
    check("[주의] 뒤에 오는 조각을 가리키면 거절한다",
          bad and "뒤에 오는 조각" in (bad[0].error or ""), str(bad[:1]))
    check("  나머지 조각은 등록된다", any(t.ok for t in got2.tasks))

    # 모르는 이름은 조용히 통과시키지 않는다
    sent.clear()
    got3 = register_work("t", [TaskSpec(stem="A", classes=["UA"], depends_on=["없는거"])],
                         paths=paths, target_repo="r", poster=poster_dep)
    check("[중요] 모르는 의존 이름은 거절한다",
          got3.tasks and "task_id 도 아니다" in (got3.tasks[0].error or ""),
          str(got3.tasks[:1]))

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

    print("\n[20] 생성 → 층2 → 인계")
    # [중요] 컨텍스트는 **호출자가 준다** (매니페스트 철거 2026-09-02) — 골조의 `[DOC]` 와
    #    base 커밋 선언부다. 비면 `generate` 가 거절한다(아래 [19] 대체 검사).
    gp = ProjectPaths(name="G", root=tmp / "G")
    CTX = "## 관련 코드\n- `A.md` 발췌"
    seen = {}

    def caller(url, payload):
        seen.update(payload)
        return f"{F}cpp\nvoid UFoo::Init(){{}}\n{F}"

    ok_v = Verdict(approved=True, failure=None)
    d = dispatch(gp, "t1", instruction="Init 구현", context=CTX, target_file="Foo.cpp",
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
    d = dispatch(gp, "t1", instruction="x", context=CTX, caller=caller, verifier=lambda f: bad)
    check("차단", not d.ok and d.verdict.blocked)
    check("  코드는 들고 있다 (진단용)", bool(d.code))
    check("  요약에 드러난다", "차단" in d.summary(), d.summary())

    d = dispatch(gp, "t1", instruction="x", context=CTX, caller=lambda u, p: "",
                 verifier=lambda f: ok_v)
    check("빈 생성 = 차단", not d.ok and "비었다" in d.error, d.error)

    d = dispatch(gp, "t1", instruction="x", context=CTX, caller=caller, verifier=lambda f: None)
    check("[중요] verdict 가 없으면 통과가 아니다", not d.ok)

    def dead(url, payload):
        raise GenerateError("브로커에 닿지 않는다")

    d = dispatch(gp, "t1", instruction="x", context=CTX, caller=dead)
    check("브로커 장애 = 차단", not d.ok and "닿지 않는다" in d.error)
    check("  층2 를 부르지 않는다", d.verdict is None)

    print("\n[21b] [중요] 컨텍스트가 비면 생성하지 않는다 (grounding 0 = 환각 조건)")
    d = dispatch(gp, "t1", instruction="x", context="   ", caller=caller,
                 verifier=lambda f: ok_v)
    check("[중요] 빈 컨텍스트는 차단", not d.ok and "컨텍스트가 비었다" in d.error, d.error)
    check("  층2 를 부르지 않는다", d.verdict is None)

    print("\n[22] 층2 에 넘기는 파일명")
    names = []
    dispatch(gp, "t1", instruction="x", context=CTX, target_file="Bar.cpp", caller=caller,
             verifier=lambda f: (names.append(f[0][0]), ok_v)[1])
    check("target_file 을 쓴다", names == ["Bar.cpp"], str(names))
    names.clear()
    dispatch(gp, "t1", instruction="x", context=CTX, caller=caller,
             verifier=lambda f: (names.append(f[0][0]), ok_v)[1])
    check("없으면 task_id 로", names == ["t1.cpp"], str(names))

    shutil.rmtree(tmp, ignore_errors=True)

    # ── 대상 파일 (#65) ─────────────────────────────
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
