"""워커 러너 — 마스터가 큐에서 집어 워커 Claude 에 밀어넣는 경로 (#21 후속).

**SSH 를 실행하지 않는다** — `runner`/`writer`/`beat` 를 주입한다. 여기서 지키는 계약은
명령이 아니라 **판정**이다: [중요] *모르는 것을 성공으로 접지 않는가.*

`.venv/bin/python master/test_runner.py`
"""
from __future__ import annotations

import ast
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
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


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

    # [중요] 산문을 성공으로 읽어주면 큐에 거짓 완료가 쌓인다
    prose = "다 했습니다! 성공적으로 완료했습니다. SUCCESS\n"
    p = R.parse_result(prose)
    check("[중요] 산문은 성공이 아니다", not p.ok and p.status == R.BLOCKED, p.summary)
    check("왜 떨어졌는지 말한다", "RESULT" in p.reason, p.reason)

    check("[중요] 빈 출력은 BLOCKED", not R.parse_result("").ok)
    check("빈 출력 사유를 적는다", "비었다" in R.parse_result("").reason)

    # [중요] 마지막 줄이 아니면 그 뒤에 무슨 일이 더 있었다는 뜻이다
    late = "RESULT: DONE\n그런데 push 에 실패했습니다\n"
    check("[중요] RESULT 가 마지막 줄이 아니면 BLOCKED", not R.parse_result(late).ok,
          R.parse_result(late).summary)

    # [중요] DONE 인데 제출할 근거가 없다
    bare = "RESULT: DONE\n"
    b = R.parse_result(bare)
    check("[중요] ATTEMPT/HEAD 없는 DONE 은 제출 불가", b.ok and not b.submittable, b.summary)
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
    check("[중요] 왜 떨어졌는지 들고 나온다",
          any("역할" in r for _, r in p.rejected), str(p.rejected))

    p2 = R.pick_worker([w43, w2], requires=["ue5"])
    check("ue5 가 필요하면 UE5 있는 쪽", p2.chosen is w2, p2.summary)
    check("능력 부족 사유를 적는다",
          any("능력 부족" in r for _, r in p2.rejected), str(p2.rejected))

    check("체크아웃 없으면 제외",
          R.pick_worker([_facts(checkout=False)]).chosen is None)
    check("claude 없으면 제외", R.pick_worker([_facts(claude="")]).chosen is None)

    empty = R.pick_worker([])
    check("[중요] 후보가 없으면 그렇게 말한다", empty.chosen is None and "후보" in empty.summary,
          empty.summary)
    none = R.pick_worker([req])
    check("아무도 못 고르면 사유를 요약한다", "파견할 워커가 없다" in none.summary, none.summary)


# ── 워커에서 도는 명령 ───────────────────────────────────────────────────────

def test_command() -> None:
    # [중요] 한글을 명령줄에 실으면 워커 콘솔 cp949 에서 깨진다 (리포트 11 실측)
    check("[중요] 지시문은 ASCII 다", R.INSTRUCTION.isascii(), R.INSTRUCTION[:60])

    c = R.worker_command(_facts(), "t1")
    check("체크아웃으로 이동한다", "/home/sim/trunk/ModularStage" in c, c)
    check("스킬을 지목한다", "ax-work" in c)
    # 🔴 정본 ⑸ (2026-09-02) — 지시서는 파일이 아니라 **골조 주석**이고, git 은 워커의 LLM 이
    #    만지지 않는다(`wcommit` 이 결정적으로 한다). 그래서 셋을 잰다:
    check("[중요] 매니페스트 경로를 주지 않는다", "manifest.md" not in c, c)
    check("[중요] 골조 주석을 읽으라고 한다", "[DOC]" in c and "[PSEUDO]" in c, c)
    check("[중요] git 을 금지한다", "Do not run any git command" in c, c)
    check("판정 마커를 요구한다", "RESULT: DONE" in c, c)
    check("승인을 연다 (사용자 결정)", "--dangerously-skip-permissions" in c)
    check("명령 전체가 ASCII", c.isascii(), c[:80])

    cw = R.worker_command(_facts("192.168.0.2", os_="windows",
                                        path="C:\\Users\\janus\\ModularStage"), "t1")
    check("윈도우는 cd /d 를 쓴다", "cd /d" in cw, cw[:50])
    # [중요] 경로를 코드에 박으면 예전처럼 '다른 머신 경로' 사고가 난다
    check("[중요] 경로는 레지스트리 값이다", "C:\\Users\\janus\\ModularStage" in cw, cw[:60])


def test_codex_windows_sandbox() -> None:
    """🔴 **Windows 워커의 codex 는 `unelevated` 샌드박스로 돈다** (실측 2026-09-09).

    `elevated` 러너는 세션 9 의 네이티브 파이프를 쓰는데 SSH 는 세션 0 이라 안 닿는다 —
    파일 쓰기 도구가 죽는데 **`codex exec` 는 rc=0 으로 끝나서** 마스터에는 「골조가 그대로」
    로만 보인다. 라이브에서 `.2` 조각 2건이 그렇게 죽었다(`.43` 은 같은 파견에서 2/2).
    """
    win = R.worker_command(_facts("192.168.0.2", os_="windows",
                                  path="C:\\trunk\\NS"), "t1", mode="codex")
    check("🔴 윈도우 워커는 샌드박스를 못 박는다",
          'windows.sandbox="unelevated"' in win, win[:160])
    check("  stdin 을 막는다 (tty 가 없다)", "< NUL" in win, win[-40:])
    check("  쓰기는 작업공간으로 묶는다", "-s workspace-write" in win, win[:160])
    check("  네트워크는 연다 (레인 위임이 브로커 HTTP 다)",
          "sandbox_workspace_write.network_access=true" in win, win[:160])

    lin = R.worker_command(_facts("192.168.0.43"), "t1", mode="codex")
    # [주의] Linux 도 같은 스키마로 파싱은 하지만 **쓰지 않는다** — 안 쓰는 손잡이는 안 보낸다
    check("[주의] 리눅스 워커에는 안 싣는다", "windows.sandbox" not in lin, lin[:160])
    check("  리눅스는 /dev/null 로 막는다", "< /dev/null" in lin, lin[-40:])


# ── 배달 ─────────────────────────────────────────────────────────────────────

# ── 하트비트 ─────────────────────────────────────────────────────────────────

def test_agent_report() -> None:
    """🔴 **지휘자가 자기 입으로 한 말을 남긴다** (`#391` · 실측 2026-09-09 `.2`).

    이 stdout 은 실제로 `.2` 에서 나온 것이다. 종전에는 통째로 버려져서 마스터에는 층1 의
    `[PSEUDO]` 한 줄만 남았고, **환경 실패가 코드 실패로 위장돼** 재시도 3회를 태웠다.
    """
    real = (
        '{"type":"thread.started","thread_id":"01a0868f"}\n'
        '2026-09-09T14:26:13Z ERROR codex_core::tools::router: error=exec_command failed: '
        'CreateProcess { message: "Rejected(\\"Failed to create unified exec process: '
        'timed out after 15000ms connecting runner pipe-in\\")" }\n'
        '{"type":"item.completed","item":{"id":"item_2","type":"agent_message",'
        '"text":"Unable to create probe.txt because the file-writing tools failed."}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":127154,"output_tokens":314}}\n'
    )
    got = R.agent_report(real, rc=0)
    joined = " | ".join(got)
    check("🔴 rc=0 이어도 남긴다 (이번 사고가 정확히 rc=0 이었다)", bool(got), joined)
    check("  지휘자의 마지막 말을 뽑는다",
          "file-writing tools failed" in joined, joined)
    check("  실패 원인 줄을 뽑는다 — 여기에 진짜 원인이 있다",
          "runner pipe-in" in joined or "Rejected(" in joined, joined)
    check("[주의] 전문을 찍지 않는다 (JSONL 수백 줄이 로그를 삼킨다)",
          len(joined) < 1200, f"{len(joined)}자")

    # [중요] **침묵을 「문제 없음」으로 읽지 않는다** — 빈 목록을 돌려주면 안 된다
    empty = R.agent_report("", rc=0)
    check("🔴 출력이 없으면 **없다고 말한다** (조용한 빈 결과 금지)",
          bool(empty) and "출력이 없다" in empty[0], str(empty))

    # claude 갈래 — `--output-format json` 의 `result`
    cj = R.agent_report('{"result":"RESULT: DONE 작업 완료","total_cost_usd":0.1}', rc=0)
    check("  claude 출력 형식도 읽는다", "RESULT: DONE" in " ".join(cj), str(cj))


def test_beater() -> None:
    n = []
    with R._Beater(lambda: n.append(1), interval=0.02):
        time.sleep(0.12)
    check("[중요] SSH 가 도는 동안 리스를 살린다 (하트비트가 돈다)", len(n) >= 2, f"{len(n)}회")

    # [중요] 하트비트 한 번 실패와 워커가 죽은 것은 다르다 — 전자로 작업을 죽이지 않는다
    def bad():
        raise RuntimeError("연결 끊김")

    with R._Beater(bad, interval=0.02) as b:
        time.sleep(0.08)
    check("[중요] 하트비트 실패가 작업을 죽이지 않는다", len(b.errors) >= 1, str(b.errors[:1]))

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

    r = R.run_task(_facts(), "t1", runner=runner, timeout=77)
    # [중요] 배달 단계가 없어졌다 (매니페스트 철거 2026-09-02) — 실행 한 번만 돈다
    check("실행만 돈다 (배달 없음)", [c[0] for c in calls] == ["run"], str(calls))
    check("타임아웃을 넘긴다", calls[0][1] == 77)
    check("성공을 제출 가능으로 본다", r.submittable, r.summary)

    # [중요] 워커는 DONE 이라는데 껍데기가 실패했다
    r2 = R.run_task(_facts(), "t1", runner=lambda f, c, t: (255, good))
    check("[중요] ssh 실패면 DONE 이라도 BLOCKED", not r2.ok and "rc=255" in r2.reason, r2.summary)

    r3 = R.run_task(_facts(), "t1", runner=lambda f, c, t: (255, "죽었다"))
    check("실패 + 마커 없음도 BLOCKED", not r3.ok, r3.summary)
    check("두 사유가 다 남는다", "rc=255" in r3.reason and "RESULT" in r3.reason, r3.reason)




# ── 큐 배선 — [중요] 집었으면 반드시 놓는다 ──────────────────────────────────────

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


def test_queue_calls() -> None:
    api = _Api()
    R.claim("w1", ["ue5"], api=api)
    check("claim 은 능력을 실어 보낸다", api.calls[0][2]["capabilities"] == ["ue5"], str(api.calls[0]))

    out = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE\n")
    R.submit("t1", out, epoch=7, api=api)
    body = api.calls[-1][2]
    check("submit 이 브랜치·커밋을 싣는다", body["branch"] == "a/b" and body["head_commit"] == SHA)
    check("[중요] epoch 을 실어 fencing 을 살린다", body["epoch"] == 7, str(body.get("epoch")))

    # [중요] 근거 없는 결과를 제출하려 하면 막는다
    try:
        R.submit("t1", R.parse_result("RESULT: DONE\n"), api=api)
        check("[중요] 제출 불가한 결과는 막는다", False, "그대로 보냈다")
    except R.QueueError as e:
        check("[중요] 제출 불가한 결과는 막는다", "제출 불가" in str(e), str(e)[:50])


def test_run_once_happy() -> None:
    if True:
        api = _Api(task={"task_id": "t1", "work_id": "w1", "epoch": 3, "target_file": "Source/X.cpp", "header_file": "Source/X.h"})
        good = f"ATTEMPT: attempt/t1/bc250/1\nHEAD: {SHA}\nRESULT: DONE\n"
        r = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api,
                       runner=lambda f, c, t: (0, good))
        check("한 건이 끝까지 간다", r["submitted"] == "submit", str(r))
        check("claim → submit 순서",
              api.paths[0].endswith("/claim") and api.paths[-1].endswith("/submit"), str(api.paths))
        check("태스크 id 를 들고 나온다", r["task"] == "t1")


def test_run_once_returns_the_task() -> None:
    if True:
        # BLOCKED — 반납해야 한다
        api = _Api(task={"task_id": "t2", "work_id": "w1", "epoch": 1, "target_file": "Source/X.cpp", "header_file": "Source/X.h"})
        r = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api,
                       runner=lambda f, c, t: (0, "RESULT: BLOCKED\n"))
        check("[중요] BLOCKED 는 반납한다", r["submitted"] == "submit-fail", str(r))
        check("submit-fail 로 갔다", api.paths[-1].endswith("/submit-fail"), str(api.paths))

        # [중요] 파견 도중 예외 — 집은 채로 죽으면 리스 1200초를 태운다
        api2 = _Api(task={"task_id": "t3", "work_id": "w1", "epoch": 1, "target_file": "Source/X.cpp", "header_file": "Source/X.h"})
        try:
            R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api2,
                       runner=lambda f, c, t: (_ for _ in ()).throw(RuntimeError("SSH 폭발")))
            check("[중요] 예외는 삼키지 않는다", False, "조용히 넘어갔다")
        except RuntimeError:
            check("[중요] 예외는 삼키지 않는다", True)
        check("[중요] 예외가 나도 태스크를 반납한다",
              any(p.endswith("/submit-fail") for p in api2.paths), str(api2.paths))


def test_run_once_guards() -> None:
    # [중요] 워커가 없으면 claim 조차 하지 않는다 — 집어놓고 못 돌리는 게 더 나쁘다
    api = _Api(task={"task_id": "t4", "work_id": "w1", "target_file": "Source/X.cpp", "header_file": "Source/X.h"})
    r = R.run_once(_paths_stub(), clean=None, facts=[_facts(role="requester")], api=api)
    check("[중요] 워커가 없으면 claim 하지 않는다", not api.calls and r["task"] is None, str(api.paths))
    check("왜 안 했는지 말한다", "집어놓고" in r.get("note", ""), r.get("note", ""))

    api2 = _Api(task=None)
    r2 = R.run_once(_paths_stub(), clean=None, facts=[_facts()], api=api2)
    check("집을 게 없으면 조용히 끝난다", r2["task"] is None and "없다" in r2["note"], str(r2))



def test_result_asymmetry() -> None:
    """[중요] 관대함은 **안전한 판정 쪽으로만** 연다 (실측 2026-08-09)."""
    r = R.parse_result("작업 중단\nRESULT: BLOCKED — 워킹트리가 더럽다\n")
    check("사유가 붙은 BLOCKED 는 받는다", r.status == R.BLOCKED and not r.ok, r.summary)
    check("[중요] 그 사유를 살려낸다", "워킹트리가 더럽다" in r.reason, r.reason)

    # [중요] 반대 방향으로는 열지 않는다 — 거짓 완료가 큐에 쌓인다
    d = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE — 아마 됐을 것이다\n")
    check("[중요] 사유가 붙은 DONE 은 받지 않는다", not d.ok, d.summary)

    bare = R.parse_result("RESULT: BLOCKED\n")
    check("맨 BLOCKED 도 여전히 받는다", bare.status == R.BLOCKED)

    noreason = R.parse_result("RESULT: BLOCKED —\n")
    check("사유가 비면 그렇게 적는다", "적지 않았다" in noreason.reason, noreason.reason)



def test_pick_skips_dirty() -> None:
    """[중요] 못 돌릴 워커에게 태스크를 주지 않는다 (실측 2026-08-09: 집었다 반납한 왕복)."""
    class _C:
        def __init__(self, ok, reason=""):
            self.ok, self.reason = ok, reason

    dirty, cleanw = _facts("192.168.0.2"), _facts("192.168.0.43")
    verdict = {"192.168.0.2": _C(False, "추적 파일 3건이 더럽다"), "192.168.0.43": _C(True)}
    p = R.pick_worker([dirty, cleanw], clean=lambda f: verdict[f.host])
    check("더러운 워커는 건너뛴다", p.chosen is cleanw, p.summary)
    check("[중요] 왜 건너뛰었는지 말한다",
          any("더럽다" in r for _, r in p.rejected), str(p.rejected))

    # [중요] 확인 실패는 통과가 아니다
    p2 = R.pick_worker([dirty], clean=lambda f: None)
    check("[중요] 더티 확인을 못 하면 안 고른다", p2.chosen is None, p2.summary)
    check("확인 실패를 그렇게 적는다", "확인하지 못했다" in p2.summary, p2.summary)

    p3 = R.pick_worker([cleanw])
    check("clean 을 안 주면 예전대로 (하위호환)", p3.chosen is cleanw)



def test_json_usage() -> None:
    """[중요] 계측이 없는 것과 작업이 실패한 것은 다르다 (--output-format json)."""
    import json as _j
    blob = _j.dumps({
        "result": f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE",
        "total_cost_usd": 0.42, "num_turns": 7, "duration_api_ms": 1234,
        "usage": {"input_tokens": 11, "output_tokens": 22,
                  "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 4000}})
    r = R.parse_result(blob)
    check("json 안의 마커를 읽는다", r.submittable, r.summary)
    check("비용을 잡는다", abs(r.cost_usd - 0.42) < 1e-9, str(r.cost_usd))
    # [중요] 캐시가 비용을 지배한다 — 뭉치지 않고 넷으로 본다
    check("토큰을 넷으로 나눠 준다", r.tokens == (11, 22, 3000, 4000), str(r.tokens))
    check("턴 수도 남는다", r.usage.get("num_turns") == 7, str(r.usage)[:60])

    # [중요] 텍스트로 떨어져도 판정은 그대로 — 계측만 비는 것이다
    txt = R.parse_result(f"ATTEMPT: a/b\nHEAD: {SHA}\nRESULT: DONE\n")
    check("[중요] json 이 아니어도 실패가 아니다", txt.submittable, txt.summary)
    check("계측만 빈다", txt.usage == {} and txt.cost_usd == 0.0, str(txt.usage))

    bad = R.parse_result('{"result": 이건깨진json')
    check("깨진 json 은 텍스트로 다룬다", not bad.ok and bad.usage == {}, bad.summary)

    cmd = R.worker_command(_facts(), "t1")
    check("[중요] 명령에 --output-format json 이 있다", "--output-format json" in cmd, cmd[:90])


def test_codex_mcp_approval() -> None:
    """🔴 **MCP 도구는 승인 없이는 안 불린다** (`#402`, 실측 2026-09-12).

    비대화형 `codex exec` 는 `approval: never` 라 호출이 거절된다 —
    *"MCP tool call requires approval, but approval policy is never"*. 🔴 **서버 단위 키는
    안 먹는다**(`-c mcp_servers.<서버>.approval_mode` 로 그대로 거절당했다). 도구 단위만 통과다.
    """
    from master.client import bundle as B
    names = B.client_tool_names()
    check("[중요] 도구 이름을 클라 MCP 의 TOOLS 에서 읽는다 (여기 베끼지 않는다)",
          len(names) > 20 and "list_works" in names and "search_context" in names,
          f"{len(names)}종")

    for host, win in (("192.168.0.2", True), ("192.168.0.43", False)):
        cmd = R.worker_command(_facts(host, os_=("windows" if win else "linux"),
                                      path=("C:\\trunk\\NS" if win else "/t/NS")),
                               "t1", mode="codex")
        check(f"  {host}: 도구마다 승인 플래그가 실린다",
              cmd.count("approval_mode") == len(names), str(cmd.count("approval_mode")))
        check(f"  {host}: 종전 플래그가 살아 있다 (network_access)",
              "network_access=true" in cmd)
        # [주의] `--approve-for-me` 는 승인 경로에 LLM 자동 검토를 넣는다 — 결정론 원칙과 어긋난다
        check(f"  {host}: `--approve-for-me` 를 쓰지 않는다", "--approve-for-me" not in cmd)

    win_cmd = R.worker_command(_facts("192.168.0.2", os_="windows", path="C:\\trunk\\NS"),
                               "t1", mode="codex")
    check("🔴 [주의] Windows 의 `unelevated` 못박기가 승인 플래그에 밀려나지 않았다",
          'windows.sandbox="unelevated"' in win_cmd)
    # lane/claude 모드는 MCP 승인과 무관하다 — 섞이면 안 된다
    cl = R.worker_command(_facts("192.168.0.43", path="/t/NS"), "t1", mode="claude")
    check("[중요] claude 모드에는 codex 승인 플래그가 안 붙는다", "approval_mode" not in cl)


def test_dispatch_is_not_a_consent_prompt() -> None:
    """🔴 파견은 **묻는 자리가 아니다** — 지시문이 그것을 말한다 (실측 2026-09-13).

    [중요] **`AGENTS.md` 로는 못 막는다.** `#402` 가 심은 동의 규칙(*"게임 소스 수정은 계획
    승인 후에만"*)을 `.2` 의 codex 가 **따랐고**, `melee_hit_notify` 가 4회 연속 이렇게 죽었다:

        "AGENTS.md 규약상 게임 소스 수정과 빌드는 계획 승인 후에만 진행합니다."
        "이 계획대로 진행해도 되는지 승인해 주세요."
        RESULT: BLOCKED

    문서에 예외를 넣는 것으로 끝내지 않는 이유 셋 — 모두 실측이다:
      ⑴ `AGENTS.md` 는 **배달물**이라 사람이 본문을 고치면 날아가고, 배달이 밀린 기계는 옛 문구를 본다
      ⑵ `role: worker` 는 **마스터 레지스트리에만** 있다 — 워커 `config.json` 의 `this_host` 는
         `host`/`user`/`os` 뿐이라 워커 안에서는 자기가 워커인지 읽을 수 없다
      ⑶ 설령 읽어도 「이 기계가 워커다」이지 「이 프롬프트가 파견이다」가 아니다 — 같은
         체크아웃에서 사람이 직접 codex 를 열 수도 있다
      ⑷ 🔴 **승인 플래그로도 못 막는다** — codex 는 도구 승인 채널이 아니라 **산문으로** 물었다.
         `approval_mode="approve"` 29개도 `--dangerously-skip-permissions` 도 텍스트 질문은 못 막는다

    🔴 그래서 원천은 **지시문 하나뿐이다** — 마스터가 만들고, 파견마다 나가고, 모델이 무조건 읽는다.
    """
    check("[중요] 파견임을 지시문이 선언한다", "dispatched work" in R.INSTRUCTION, R.INSTRUCTION)
    check("[중요] 승인이 이미 났다고 말한다", "already approved" in R.INSTRUCTION)
    check("[중요] 묻지 말라고 말한다", "Do not ask for approval" in R.INSTRUCTION)
    check("계획 제출도 막는다", "do not propose a plan" in R.INSTRUCTION)

    c = R.worker_command(_facts(), "t1")
    check("실제 명령줄에 실린다", "Do not ask for approval" in c, c[:120])


def test_session1_instruction_matches() -> None:
    """🔴 **배달물의 지시문이 마스터와 같은 글자인가.** 주석으로만 적혀 있던 계약을 잰다.

    `client/runtime/session1_conductor.py` 는 `clientside` 규약상 마스터를 import 하지 않아
    값을 **복사**한다. 갈리면 세션1 경로(윈도우 워커)만 **다른 계약으로** 일하는데, 그 차이는
    마스터 로그에 안 보인다 — 산출물이 조금 다를 뿐이라 층1 이 잡지도 못한다.
    """
    src = (Path(__file__).resolve().parents[1]
           / "client" / "runtime" / "session1_conductor.py")
    ns: dict = {}
    exec(compile(ast.Module(body=[n for n in ast.parse(src.read_text()).body
                                  if isinstance(n, ast.Assign)
                                  and getattr(n.targets[0], "id", "") == "INSTRUCTION"],
                            type_ignores=[]), str(src), "exec"), ns)
    check("[중요] 세션1 런처가 지시문을 갖는다", "INSTRUCTION" in ns, sorted(ns))
    check("🔴 [중요] 마스터 지시문과 글자까지 같다", ns.get("INSTRUCTION") == R.INSTRUCTION,
          f"launcher={ns.get('INSTRUCTION', '')[:80]!r}\nmaster={R.INSTRUCTION[:80]!r}")


def test_session1_master_logs() -> None:
    """🔴 **세션 1 경로는 기다리는 동안에도, 끝난 뒤에도 로그를 남긴다** (실측 2026-09-13).

    실증 7분(18:54~19:02) 동안 마스터 저널이 비어 있었고, 워커에서 UnrealBuildTool 이 두 번 죽어
    오류 창이 뜬 것을 사람이 SSH 로 들어가서야 찾았다. 이 테스트는 **실 SSH·실 codex 없이**
    그 로그 줄들이 실제로 나오는지 잰다.
    """
    from types import SimpleNamespace
    from master.client import bundle as B

    facts = SimpleNamespace(host="192.168.0.2", user="janus", windows=True,
                            path="E:\\trunk\\NS", os="windows")
    POPUP = ("18:55:34 Application popup: dotnet.exe - 응용 프로그램 오류 : 예외 알 수 없는 "
             "소프트웨어 예외 (0xe0434352)")
    saved = (B._ssh, B._remote_write, B._remote_read)
    ticks = iter(range(0, 100000, 7))

    def run(*, done_after: int, launcher_log, timeout: int = 600):
        polls = {"n": 0}
        lines: list = []

        def fake_ssh(host, user, cmd, timeout=None, **kw):
            if "done.flag" in cmd:
                polls["n"] += 1
                return 0, ("DONE" if polls["n"] > done_after else "WAIT")
            return 0, ""

        def fake_read(f, p):
            if p.endswith("out.txt"):
                return "RESULT: DONE"
            if p.endswith("rc.txt"):
                return "0"
            if p.endswith("launcher.log") and launcher_log is not None:
                return launcher_log
            raise FileNotFoundError(p)

        B._ssh, B._remote_write, B._remote_read = fake_ssh, (lambda *a, **k: ""), fake_read
        try:
            rc, out = R.run_worker_session1(
                facts, "t1", files=["Source/A.cpp"], timeout=timeout,
                sleeper=lambda s: None, logf=lines.append, now=lambda: next(ticks),
                popup=lambda f, since: [POPUP])
        finally:
            B._ssh, B._remote_write, B._remote_read = saved
        return rc, out, lines

    rc, out, lines = run(done_after=14, launcher_log=(
        "2026-09-13 18:54:58 job 집음 — task=t1 · 파일 1 · 제한 600초\n"
        "2026-09-13 19:02:14 codex 종료 — rc=0 · 436초 · 출력 42706자\n"))
    joined = "\n".join(lines)
    check("job 전송을 찍는다", "t1 @192.168.0.2 job 전송" in joined, joined[:300])
    check("런처를 깨웠다고 찍는다", "런처를 깨웠다" in joined)
    check("🔴 [중요] 기다리는 동안에도 찍는다 (7분 침묵의 자리)", "초째 대기" in joined, joined)
    check("결과 회수 줄에 rc 와 걸린 시간이 있다",
          any("결과 회수 — rc=0" in l and "초 · 출력" in l for l in lines), joined)
    check("🔴 [중요] 런처 로그가 저널로 온다", "런처: 2026-09-13 18:54:58 job 집음" in joined, joined)
    check("🔴 [중요] 오류 창이 저널에 찍힌다", "오류 창 감지 — 18:55:34" in joined, joined)
    check("  결과 rc 는 그대로다 (로그가 판정을 바꾸지 않는다)", rc == 0, str(rc))
    check("🔴 오류 창이 결과에도 붙는다 — 조각 기록까지 가야 한다",
          "ERROR [세션1] 오류 창 감지" in out, out)
    rep = R.agent_report(out, rc=rc)
    check("  `agent_report` 가 그것을 오류 줄로 뽑는다 (c.notes 로 간다)",
          any("오류 창 감지" in l for l in rep), str(rep))

    _rc2, _out2, lines2 = run(done_after=0, launcher_log=None)
    check("[주의] 런처 로그가 없으면 그 사실을 말한다 (옛 배달본 · job 을 안 집음)",
          any("launcher.log 를 못 읽었다" in l for l in lines2), "\n".join(lines2))

    rc3, out3, lines3 = run(done_after=10**6, launcher_log="", timeout=30)
    check("🔴 시간 초과를 찍는다", any("시간 초과 — 결과를 못 받았다" in l for l in lines3),
          "\n".join(lines3))
    check("  시간 초과 뒤에도 오류 창을 가져온다 (멈춘 이유가 거기 있다)",
          rc3 == 1 and "오류 창 감지" in out3, out3)


def _load_launcher():
    import importlib.util
    src = Path(__file__).resolve().parents[1] / "client" / "runtime" / "session1_conductor.py"
    spec = importlib.util.spec_from_file_location("_s1_launcher_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_session1_launcher_logs() -> None:
    """🔴 **런처가 사건마다 `launcher.log` 에 남긴다** (실측 2026-09-13 — 종전 런처는 로그 0줄).

    [주의] 실 codex 를 부르지 않는다 — `build_argv` 를 파이썬 한 줄로 바꿔 끼운다.
    """
    import json as _json
    import os
    import sys as _sys
    import tempfile
    import time as _time

    L = _load_launcher()
    root = Path(tempfile.mkdtemp(prefix="ax-s1-"))
    d = root / ".ax" / "session1" / "t1"
    d.mkdir(parents=True)
    (d / "job.json").write_text(_json.dumps({"task_id": "t1", "files": ["Source/A.cpp"],
                                             "timeout": 60}), encoding="utf-8")
    saved = (L.build_argv, L.find_root)
    L.build_argv = lambda r, files, approvals=(): [_sys.executable, "-c", "print('RESULT: DONE')"]
    try:
        rc = L.run_job(root, d)
        log = (d / "launcher.log").read_text(encoding="utf-8")
        check("런처가 job 을 돌렸다", rc == 0 and "RESULT: DONE" in (d / "out.txt").read_text())
        for want in ("job 집음 — task=t1", "codex 시작 — pid=", "codex 종료 — rc=0", "결과 기록 — rc=0"):
            check(f"🔴 launcher.log 에 「{want}」", want in log, log)
        check("  done.flag 는 여전히 쓴다", (d / "done.flag").exists())

        # 🔴 관찰 로그 — 완료 뒤 job.json 이 다시 쓰이면 **돌리지 않고** 그 사실을 남긴다
        later = (d / "done.flag").stat().st_mtime + 10
        os.utime(d / "job.json", (later, later))
        L.find_root = lambda: root
        L.main()
        log2 = (d / "launcher.log").read_text(encoding="utf-8")
        check("🔴 [중요] 재시도 job 을 건너뛸 때 그 사실이 남는다 (가설 확인용)",
              "job.json 이 done.flag 보다 새롭다" in log2, log2)
        check("  동작은 그대로 — 다시 돌리지 않았다 (관찰만 더했다)",
              log2.count("codex 시작") == 1, log2)

        # 시간 초과
        d3 = root / ".ax" / "session1" / "t3"
        d3.mkdir(parents=True)
        (d3 / "job.json").write_text(_json.dumps({"task_id": "t3", "timeout": 1}), encoding="utf-8")
        L.build_argv = lambda r, files, approvals=(): [_sys.executable, "-c",
                                                       "import time; time.sleep(30)"]
        t0 = _time.monotonic()
        L.run_job(root, d3)
        log3 = (d3 / "launcher.log").read_text(encoding="utf-8")
        check("🔴 시간 초과가 launcher.log 에 남는다", "시간 초과 1초" in log3, log3)
        check("  그리고 오래 매달리지 않는다", _time.monotonic() - t0 < 20)
    finally:
        L.build_argv, L.find_root = saved


def test_worker_does_not_build() -> None:
    """🔴 **워커는 UE5 빌드를 돌리지 않는다** — 지시문이 말하고, 돌렸는지는 따로 잰다 (실측 2026-09-13).

    `.2` 의 codex 지휘자가 본문을 채운 직후 스스로 `Build.bat NSEditor …` 를 돌렸고, 샌드박스 안에서
    UnrealBuildTool 이 시작하자마자 두 번 죽어 오류 창이 7분을 붙잡았다. 원전 워커는 빌드하지 않는다.
    """
    check("🔴 [중요] 지시문이 빌드를 금지한다", "Do not run UE5 builds" in R.INSTRUCTION, R.INSTRUCTION)
    check("  빌드 판정이 누구 몫인지 말한다", "done later by the requester" in R.INSTRUCTION)
    check("  [중요] ASCII 만이다 (워커 콘솔에서 깨지지 않는다)", R.INSTRUCTION.isascii())
    c = R.worker_command(_facts(), "t1")
    check("실제 명령줄에 실린다", "Do not run UE5 builds" in c, c[:160])

    # [중요] **`.2` 의 실제 출력이다** (조각 ed833ab2 · out.txt). 지어낸 문자열이 아니다.
    agent_msg = r'''{"type":"item.completed","item":{"id":"item_8","type":"agent_message","text":"빌드는 아직 진행 중이며 추가 오류 출력은 없습니다. 완료 코드와 UnrealBuildTool 최종 문구까지 확인하겠습니다."}}'''
    build1 = r'''{"type":"item.completed","item":{"id":"item_6","type":"command_execution","command":"\"C:\\\\WINDOWS\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command \"rg -n \\\"\\\\[PSEUDO\\\\]|\\\\[FEEDBACK\\\\]\\\" Source/NS/NSCharacterBase.cpp Source/NS/NSCharacterBase.h; \"'$build = '\"'C:\\\\Program Files\\\\UE_5.8\\\\Engine\\\\Build\\\\BatchFiles\\\\Build.bat'; & \"'$build NSEditor Win64 Development '\"'E:\\\\trunk\\\\NS\\\\NS.uproject' -WaitMutex -FromMsBuild\"","aggregated_output":"Using bundled DotNet SDK version: 10.0 win-x64\r\nRunning UnrealBuildTool: dotnet \"..\\..\\Engine\\Binaries\\DotNET\\UnrealBuildTool\\UnrealBuildTool.dll\" NSEditor Win64 Development E:\\trunk\\NS\\NS.uproject -WaitMutex -FromMsBuild\r\n","exit_code":1,"status":"failed"}}'''
    log_read = r'''{"type":"item.started","item":{"id":"item_10","type":"command_execution","command":"\"C:\\\\WINDOWS\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command '$logs = @('\"'C:\\\\Users\\\\janus\\\\AppData\\\\Local\\\\UnrealBuildTool\\\\Log.txt','C:\\\\Users\\\\janus\\\\AppData\\\\Local\\\\UnrealBuildTool\\\\Log.json','C:\\\\Users\\\\janus\\\\AppData\\\\Local\\\\UnrealBuildTool\\\\Log.xml'); foreach (\"'$log in $logs) { if (Test-Path $log) { Write-Output \"=== $log ===\"; Get-Content -Tail 160 $log } }'","aggregated_output":"","exit_code":null,"status":"in_progress"}}'''
    build2 = r'''{"type":"item.completed","item":{"id":"item_13","type":"command_execution","command":"\"C:\\\\WINDOWS\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command \"& 'C:\\\\Program Files\\\\UE_5.8\\\\Engine\\\\Build\\\\BatchFiles\\\\Build.bat' NSEditor Win64 Development 'E:\\\\trunk\\\\NS\\\\NS.uproject' -WaitMutex -FromMsBuild\"","aggregated_output":"Using bundled DotNet SDK version: 10.0 win-x64\r\nRunning UnrealBuildTool: dotnet \"..\\..\\Engine\\Binaries\\DotNET\\UnrealBuildTool\\UnrealBuildTool.dll\" NSEditor Win64 Development E:\\trunk\\NS\\NS.uproject -WaitMutex -FromMsBuild\r\n","exit_code":1,"status":"failed"}}'''
    got = R.build_attempts("\n".join([agent_msg, build1, log_read, build2, build2]))
    check("🔴 [중요] 실측 출력에서 실제 빌드 실행 두 번을 잡는다", len(got) == 2, str(got))
    check("  각 줄에 최종 상태와 종료 코드가 있다",
          all("상태 failed" in g and "종료 코드 1" in g for g in got), str(got))
    check("[중요] 로그를 **읽는** 명령은 빌드가 아니다 (오탐 금지)",
          R.build_attempts(log_read) == [], str(R.build_attempts(log_read)))
    check("[중요] 지휘자가 **말로** UnrealBuildTool 을 언급한 것은 빌드가 아니다",
          R.build_attempts(agent_msg) == [])
    check("  빈 출력·비 JSON 은 빈 목록이다 (예외 없음)",
          R.build_attempts("") == [] and R.build_attempts("RESULT: DONE\nBuild.bat") == [])


def main() -> int:
    for fn in (test_parse, test_pick, test_command, test_codex_windows_sandbox,
               test_agent_report, test_beater, test_run_task,
               test_queue_calls, test_run_once_happy, test_run_once_returns_the_task,
               test_run_once_guards, test_result_asymmetry, test_pick_skips_dirty,
               test_json_usage,
               test_codex_mcp_approval,
               test_dispatch_is_not_a_consent_prompt,
               test_session1_instruction_matches,
               test_session1_master_logs,
               test_session1_launcher_logs,
               test_worker_does_not_build):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_runner: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
