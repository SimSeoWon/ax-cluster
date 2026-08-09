"""워커 러너 — 마스터가 큐에서 집어 워커 Claude 에 밀어넣는 경로 (#21 후속).

**SSH 를 실행하지 않는다** — `runner`/`writer`/`beat` 를 주입한다. 여기서 지키는 계약은
명령이 아니라 **판정**이다: 🔴 *모르는 것을 성공으로 접지 않는가.*

`.venv/bin/python master/test_runner.py`
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client.bundle import HostFacts          # noqa: E402
from master.work import runner as R                     # noqa: E402

PASS = FAIL = 0
SHA = "bc4b38f43c23d0e898573b0a5fd89c12fee7f813"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _facts(host="192.168.0.43", *, role="worker", os_="linux", claude="2.1",
           checkout=True, ue5="", path="/home/sim/trunk/ModularStage") -> HostFacts:
    f = HostFacts(host=host, user="sim", path=path, driven="ssh", role=role)
    f.os, f.claude, f.checkout_ok, f.ue5 = os_, claude, checkout, ue5
    return f


# ── 판정 읽기 — fail-closed ──────────────────────────────────────────────────

def test_parse() -> None:
    good = "작업했다\nATTEMPT: attempt/t1/bc250/20260809\nHEAD: " + SHA + "\nRESULT: DONE\n"
    r = R.parse_result(good)
    check("정상 판정을 읽는다", r.ok and r.submittable, r.summary)
    check("브랜치를 싣는다", r.branch == "attempt/t1/bc250/20260809", r.branch)
    check("커밋을 싣는다", r.head == SHA, r.head)

    check("CRLF 도 읽는다", R.parse_result(good.replace("\n", "\r\n")).submittable)

    # 🔴 산문을 성공으로 읽어주면 큐에 거짓 완료가 쌓인다
    prose = "다 했습니다! 성공적으로 완료했습니다. SUCCESS\n"
    p = R.parse_result(prose)
    check("🔴 산문은 성공이 아니다", not p.ok and p.status == R.BLOCKED, p.summary)
    check("왜 떨어졌는지 말한다", "RESULT" in p.reason, p.reason)

    check("🔴 빈 출력은 BLOCKED", not R.parse_result("").ok)
    check("빈 출력 사유를 적는다", "비었다" in R.parse_result("").reason)

    # 🔴 마지막 줄이 아니면 그 뒤에 무슨 일이 더 있었다는 뜻이다
    late = "RESULT: DONE\n그런데 push 에 실패했습니다\n"
    check("🔴 RESULT 가 마지막 줄이 아니면 BLOCKED", not R.parse_result(late).ok,
          R.parse_result(late).summary)

    # 🔴 DONE 인데 제출할 근거가 없다
    bare = "RESULT: DONE\n"
    b = R.parse_result(bare)
    check("🔴 ATTEMPT/HEAD 없는 DONE 은 제출 불가", b.ok and not b.submittable, b.summary)
    check("그 사유를 적는다", "근거가 없다" in b.reason, b.reason)

    blk = "이유: 컴파일 툴체인이 없다\nRESULT: BLOCKED\n"
    r2 = R.parse_result(blk)
    check("BLOCKED 를 그대로 읽는다", r2.status == R.BLOCKED and not r2.ok)
    check("꼬리를 남긴다 (사람이 볼 근거)", "툴체인" in r2.tail, r2.tail[:40])

    check("소문자 result 는 안 받는다", not R.parse_result("result: done\n").ok)


# ── 워커 선택 ────────────────────────────────────────────────────────────────

def test_pick() -> None:
    w43, w2 = _facts(), _facts("192.168.0.2", os_="windows", ue5="C:\\UE\\Cmd.exe")
    req = _facts("192.168.0.33", role="requester", ue5="C:\\UE\\Cmd.exe")

    p = R.pick_worker([req, w43])
    check("요청자는 고르지 않는다", p.chosen is w43, p.summary)
    check("🔴 왜 떨어졌는지 들고 나온다",
          any("역할" in r for _, r in p.rejected), str(p.rejected))

    p2 = R.pick_worker([w43, w2], requires=["ue5"])
    check("ue5 가 필요하면 UE5 있는 쪽", p2.chosen is w2, p2.summary)
    check("능력 부족 사유를 적는다",
          any("능력 부족" in r for _, r in p2.rejected), str(p2.rejected))

    check("체크아웃 없으면 제외",
          R.pick_worker([_facts(checkout=False)]).chosen is None)
    check("claude 없으면 제외", R.pick_worker([_facts(claude="")]).chosen is None)

    empty = R.pick_worker([])
    check("🔴 후보가 없으면 그렇게 말한다", empty.chosen is None and "후보" in empty.summary,
          empty.summary)
    none = R.pick_worker([req])
    check("아무도 못 고르면 사유를 요약한다", "파견할 워커가 없다" in none.summary, none.summary)


# ── 워커에서 도는 명령 ───────────────────────────────────────────────────────

def test_command() -> None:
    # 🔴 한글을 명령줄에 실으면 워커 콘솔 cp949 에서 깨진다 (리포트 11 실측)
    check("🔴 지시문은 ASCII 다", R.INSTRUCTION.isascii(), R.INSTRUCTION[:60])

    c = R.worker_command(_facts(), "t1")
    check("체크아웃으로 이동한다", "/home/sim/trunk/ModularStage" in c, c)
    check("스킬을 지목한다", "ax-work" in c)
    check("매니페스트 경로를 준다", ".ax/work/t1/manifest.md" in c, c)
    check("판정 마커를 요구한다", "RESULT: DONE" in c and "ATTEMPT" in c and "HEAD" in c)
    check("승인을 연다 (사용자 결정)", "--dangerously-skip-permissions" in c)
    check("명령 전체가 ASCII", c.isascii(), c[:80])

    cw = R.worker_command(_facts("192.168.0.2", os_="windows",
                                        path="C:\\Users\\janus\\ModularStage"), "t1")
    check("윈도우는 cd /d 를 쓴다", "cd /d" in cw, cw[:50])
    # 🔴 경로를 코드에 박으면 예전처럼 '다른 머신 경로' 사고가 난다
    check("🔴 경로는 레지스트리 값이다", "C:\\Users\\janus\\ModularStage" in cw, cw[:60])


# ── 배달 ─────────────────────────────────────────────────────────────────────

def test_deliver() -> None:
    seen = {}

    def writer(facts, rel, content, *, base="home"):
        seen.update(rel=rel, base=base, content=content)
        return "/remote/" + rel

    R.deliver_manifest(_facts(), "t9", "매니페스트 본문", writer=writer)
    check("체크아웃 기준으로 쓴다", seen["base"] == "checkout", seen.get("base"))
    check("태스크별 디렉토리", seen["rel"] == ".ax/work/t9/manifest.md", seen.get("rel"))
    check("본문은 한글 그대로 (파일이라 안전)", seen["content"] == "매니페스트 본문")

    def boom(*a, **k):
        raise R.bundle.BundleError("해시 불일치")

    try:
        R.deliver_manifest(_facts(), "t9", "x", writer=boom)
        check("🔴 배달 실패는 예외", False, "조용히 넘어갔다")
    except R.DispatchError as e:
        check("🔴 배달 실패는 예외", "해시 불일치" in str(e), str(e)[:60])


# ── 하트비트 ─────────────────────────────────────────────────────────────────

def test_beater() -> None:
    n = []
    with R._Beater(lambda: n.append(1), interval=0.02):
        time.sleep(0.12)
    check("🔴 SSH 가 도는 동안 리스를 살린다 (하트비트가 돈다)", len(n) >= 2, f"{len(n)}회")

    # 🔴 하트비트 한 번 실패와 워커가 죽은 것은 다르다 — 전자로 작업을 죽이지 않는다
    def bad():
        raise RuntimeError("연결 끊김")

    with R._Beater(bad, interval=0.02) as b:
        time.sleep(0.08)
    check("🔴 하트비트 실패가 작업을 죽이지 않는다", len(b.errors) >= 1, str(b.errors[:1]))

    with R._Beater(None, interval=0.01):
        pass
    check("beat 가 없으면 스레드를 안 띄운다", True)


# ── 전체 한 건 ───────────────────────────────────────────────────────────────

def test_run_task() -> None:
    good = f"ATTEMPT: attempt/t1/bc250/1\nHEAD: {SHA}\nRESULT: DONE\n"
    calls = []

    def writer(facts, rel, content, *, base="home"):
        calls.append(("write", rel))
        return rel

    def runner(facts, cmd, timeout):
        calls.append(("run", timeout))
        return 0, good

    r = R.run_task(_facts(), "t1", "본문", runner=runner, writer=writer, timeout=77)
    check("배달 → 실행 순서", [c[0] for c in calls] == ["write", "run"], str(calls))
    check("타임아웃을 넘긴다", calls[1][1] == 77)
    check("성공을 제출 가능으로 본다", r.submittable, r.summary)

    # 🔴 워커는 DONE 이라는데 껍데기가 실패했다
    r2 = R.run_task(_facts(), "t1", "본문",
                           runner=lambda f, c, t: (255, good), writer=writer)
    check("🔴 ssh 실패면 DONE 이라도 BLOCKED", not r2.ok and "rc=255" in r2.reason, r2.summary)

    r3 = R.run_task(_facts(), "t1", "본문",
                           runner=lambda f, c, t: (255, "죽었다"), writer=writer)
    check("실패 + 마커 없음도 BLOCKED", not r3.ok, r3.summary)
    check("두 사유가 다 남는다", "rc=255" in r3.reason and "RESULT" in r3.reason, r3.reason)

    try:
        R.run_task(_facts(), "t1", "본문",
                          runner=lambda f, c, t: (0, good),
                          writer=lambda *a, **k: (_ for _ in ()).throw(
                              R.bundle.BundleError("못 씀")))
        check("🔴 배달 실패면 실행하지 않는다", False, "실행까지 갔다")
    except R.DispatchError:
        check("🔴 배달 실패면 실행하지 않는다", True)



# ── 큐 배선 — 🔴 집었으면 반드시 놓는다 ──────────────────────────────────────

class _Api:
    """큐를 흉내낸다. 부른 순서를 남긴다 — 순서가 계약의 일부다."""

    def __init__(self, task=None, fail_on=""):
        self.task, self.fail_on, self.calls = task, fail_on, []

    def __call__(self, method, path, payload=None, *, timeout=20):
        self.calls.append((method, path, payload))
        if self.fail_on and self.fail_on in path:
            raise R.QueueError("큐가 거부했다")
        if path.endswith("/claim"):
            return self.task
        return {"ok": True}

    @property
    def paths(self):
        return [p for _, p, _ in self.calls]


def _paths_stub():
    class P:
        name = "ModularStage"
    return P()


def _with_manifest(text="지시서"):
    orig = R._manifest_for
    R._manifest_for = lambda paths, tid: text
    return orig


def test_queue_calls() -> None:
    api = _Api()
    R.claim("w1", ["ue5"], api=api)
    check("claim 은 능력을 실어 보낸다", api.calls[0][2]["capabilities"] == ["ue5"], str(api.calls[0]))

    out = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE\n")
    R.submit("t1", out, epoch=7, api=api)
    body = api.calls[-1][2]
    check("submit 이 브랜치·커밋을 싣는다", body["branch"] == "a/b" and body["head_commit"] == SHA)
    check("🔴 epoch 을 실어 fencing 을 살린다", body["epoch"] == 7, str(body.get("epoch")))

    # 🔴 근거 없는 결과를 제출하려 하면 막는다
    try:
        R.submit("t1", R.parse_result("RESULT: DONE\n"), api=api)
        check("🔴 제출 불가한 결과는 막는다", False, "그대로 보냈다")
    except R.QueueError as e:
        check("🔴 제출 불가한 결과는 막는다", "제출 불가" in str(e), str(e)[:50])


def test_run_once_happy() -> None:
    orig = _with_manifest()
    try:
        api = _Api(task={"task_id": "t1", "epoch": 3})
        good = f"ATTEMPT: attempt/t1/bc250/1\nHEAD: {SHA}\nRESULT: DONE\n"
        r = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api,
                       runner=lambda f, c, t: (0, good), writer=lambda *a, **k: "ok")
        check("한 건이 끝까지 간다", r["submitted"] == "submit", str(r))
        check("claim → submit 순서",
              api.paths[0].endswith("/claim") and api.paths[-1].endswith("/submit"), str(api.paths))
        check("태스크 id 를 들고 나온다", r["task"] == "t1")
    finally:
        R._manifest_for = orig


def test_run_once_returns_the_task() -> None:
    orig = _with_manifest()
    try:
        # BLOCKED — 반납해야 한다
        api = _Api(task={"task_id": "t2", "epoch": 1})
        r = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api,
                       runner=lambda f, c, t: (0, "RESULT: BLOCKED\n"),
                       writer=lambda *a, **k: "ok")
        check("🔴 BLOCKED 는 반납한다", r["submitted"] == "submit-fail", str(r))
        check("submit-fail 로 갔다", api.paths[-1].endswith("/submit-fail"), str(api.paths))

        # 🔴 파견 도중 예외 — 집은 채로 죽으면 리스 1200초를 태운다
        api2 = _Api(task={"task_id": "t3", "epoch": 1})
        try:
            R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api2,
                       runner=lambda f, c, t: (_ for _ in ()).throw(RuntimeError("SSH 폭발")),
                       writer=lambda *a, **k: "ok")
            check("🔴 예외는 삼키지 않는다", False, "조용히 넘어갔다")
        except RuntimeError:
            check("🔴 예외는 삼키지 않는다", True)
        check("🔴 예외가 나도 태스크를 반납한다",
              any(p.endswith("/submit-fail") for p in api2.paths), str(api2.paths))
    finally:
        R._manifest_for = orig


def test_run_once_guards() -> None:
    # 🔴 워커가 없으면 claim 조차 하지 않는다 — 집어놓고 못 돌리는 게 더 나쁘다
    api = _Api(task={"task_id": "t4"})
    r = R.run_once(_paths_stub(), clean=None, facts=[_facts(role="requester")], api=api)
    check("🔴 워커가 없으면 claim 하지 않는다", not api.calls and r["task"] is None, str(api.paths))
    check("왜 안 했는지 말한다", "집어놓고" in r.get("note", ""), r.get("note", ""))

    api2 = _Api(task=None)
    r2 = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api2)
    check("집을 게 없으면 조용히 끝난다", r2["task"] is None and "없다" in r2["note"], str(r2))

    # 🔴 매니페스트가 없으면 파견하지 않는다 (워커가 할 일을 지어낸다)
    orig = R._manifest_for
    R._manifest_for = lambda p, t: (_ for _ in ()).throw(R.DispatchError("매니페스트가 없다"))
    try:
        api3 = _Api(task={"task_id": "t5"})
        ran = []
        try:
            R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api3,
                       runner=lambda f, c, t: (ran.append(1), (0, "RESULT: DONE"))[1],
                       writer=lambda *a, **k: "ok")
        except R.DispatchError:
            pass
        check("🔴 매니페스트가 없으면 워커를 돌리지 않는다", not ran)
        check("🔴 그래도 태스크는 반납한다",
              any(p.endswith("/submit-fail") for p in api3.paths), str(api3.paths))
    finally:
        R._manifest_for = orig



def test_refresh_base() -> None:
    """🔴 등록 시점의 기준은 정상 흐름에서 반드시 낡는다 — 파견 시점에 다시 푼다."""
    stale = ("# 태스크\n\n## 기준 (커밋·브랜치)\n\n"
             "- 작업 브랜치: `task/t1`\n"
             "- 🔴 **그 브랜치가 원격에 아직 없다.** 요청자가 먼저 만들어야 한다\n\n"
             "## 대상 클래스\n\n- UFoo\n")

    class _Base:
        commit, branch, exists, error, bare = SHA, "task/t1", True, "", "/b.git"
        checked, instruction = True, ""

    fresh = R.refresh_base(stale, _paths_stub(), "t1", resolver=lambda p, t: _Base())
    check("🔴 낡은 '아직 없다' 가 사라진다", "원격에 아직 없다" not in fresh, fresh[:200])
    check("있다고 갱신된다", "원격에 있다" in fresh, fresh[:200])
    check("🔴 뒤 절을 잘라먹지 않는다", "## 대상 클래스" in fresh and "UFoo" in fresh)
    check("절이 하나만 남는다", fresh.count(R.BASE_HEADING) == 1)

    # 🔴 못 풀면 옛 값을 지우지 않고 경고만 붙인다 — 모르는 것을 지어내지 않는다
    bad = R.refresh_base(stale, _paths_stub(), "t1",
                         resolver=lambda p, t: (_ for _ in ()).throw(RuntimeError("bare 못 읽음")))
    check("🔴 못 풀면 지우지 않는다", "task/t1" in bad and "## 대상 클래스" in bad)
    check("낡았을 수 있다고 경고한다", "낡았을 수 있다" in bad, bad[:220])

    none = R.refresh_base("# 태스크\n\n## 대상 클래스\n", _paths_stub(), "t1",
                          resolver=lambda p, t: _Base())
    check("절이 없으면 앞에 붙인다", none.startswith(R.BASE_HEADING), none[:40])



def test_result_asymmetry() -> None:
    """🔴 관대함은 **안전한 판정 쪽으로만** 연다 (실측 2026-08-09)."""
    r = R.parse_result("작업 중단\nRESULT: BLOCKED — 워킹트리가 더럽다\n")
    check("사유가 붙은 BLOCKED 는 받는다", r.status == R.BLOCKED and not r.ok, r.summary)
    check("🔴 그 사유를 살려낸다", "워킹트리가 더럽다" in r.reason, r.reason)

    # 🔴 반대 방향으로는 열지 않는다 — 거짓 완료가 큐에 쌓인다
    d = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE — 아마 됐을 것이다\n")
    check("🔴 사유가 붙은 DONE 은 받지 않는다", not d.ok, d.summary)

    bare = R.parse_result("RESULT: BLOCKED\n")
    check("맨 BLOCKED 도 여전히 받는다", bare.status == R.BLOCKED)

    noreason = R.parse_result("RESULT: BLOCKED —\n")
    check("사유가 비면 그렇게 적는다", "적지 않았다" in noreason.reason, noreason.reason)



def test_pick_skips_dirty() -> None:
    """🔴 못 돌릴 워커에게 태스크를 주지 않는다 (실측 2026-08-09: 집었다 반납한 왕복)."""
    class _C:
        def __init__(self, ok, reason=""):
            self.ok, self.reason = ok, reason

    dirty, cleanw = _facts("192.168.0.2"), _facts("192.168.0.43")
    verdict = {"192.168.0.2": _C(False, "추적 파일 3건이 더럽다"), "192.168.0.43": _C(True)}
    p = R.pick_worker([dirty, cleanw], clean=lambda f: verdict[f.host])
    check("더러운 워커는 건너뛴다", p.chosen is cleanw, p.summary)
    check("🔴 왜 건너뛰었는지 말한다",
          any("더럽다" in r for _, r in p.rejected), str(p.rejected))

    # 🔴 확인 실패는 통과가 아니다
    p2 = R.pick_worker([dirty], clean=lambda f: None)
    check("🔴 더티 확인을 못 하면 안 고른다", p2.chosen is None, p2.summary)
    check("확인 실패를 그렇게 적는다", "확인하지 못했다" in p2.summary, p2.summary)

    p3 = R.pick_worker([cleanw])
    check("clean 을 안 주면 예전대로 (하위호환)", p3.chosen is cleanw)



def test_json_usage() -> None:
    """🔴 계측이 없는 것과 작업이 실패한 것은 다르다 (--output-format json)."""
    import json as _j
    blob = _j.dumps({
        "result": f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE",
        "total_cost_usd": 0.42, "num_turns": 7, "duration_api_ms": 1234,
        "usage": {"input_tokens": 11, "output_tokens": 22,
                  "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 4000}})
    r = R.parse_result(blob)
    check("json 안의 마커를 읽는다", r.submittable, r.summary)
    check("비용을 잡는다", abs(r.cost_usd - 0.42) < 1e-9, str(r.cost_usd))
    # 🔴 캐시가 비용을 지배한다 — 뭉치지 않고 넷으로 본다
    check("토큰을 넷으로 나눠 준다", r.tokens == (11, 22, 3000, 4000), str(r.tokens))
    check("턴 수도 남는다", r.usage.get("num_turns") == 7, str(r.usage)[:60])

    # 🔴 텍스트로 떨어져도 판정은 그대로 — 계측만 비는 것이다
    txt = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE\n")
    check("🔴 json 이 아니어도 실패가 아니다", txt.submittable, txt.summary)
    check("계측만 빈다", txt.usage == {} and txt.cost_usd == 0.0, str(txt.usage))

    bad = R.parse_result('{"result": 이건깨진json')
    check("깨진 json 은 텍스트로 다룬다", not bad.ok and bad.usage == {}, bad.summary)

    cmd = R.worker_command(_facts(), "t1")
    check("🔴 명령에 --output-format json 이 있다", "--output-format json" in cmd, cmd[:90])


def main() -> int:
    for fn in (test_parse, test_pick, test_command, test_deliver, test_beater, test_run_task,
               test_queue_calls, test_run_once_happy, test_run_once_returns_the_task,
               test_run_once_guards, test_refresh_base,
               test_result_asymmetry, test_pick_skips_dirty,
               test_json_usage):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_runner: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
