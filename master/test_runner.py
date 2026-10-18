"""워커 러너 — 마스터가 큐에서 집어 워커 Claude 에 밀어넣는 경로 (#21 후속).

**SSH 를 실행하지 않는다** — `runner`/`writer`/`beat` 를 주입한다. 여기서 지키는 계약은
명령이 아니라 **판정**이다: [중요] *모르는 것을 성공으로 접지 않는가.*

`.venv/bin/python master/test_runner.py`
"""
from __future__ import annotations

import ast
import json
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


def test_codex_linux_agy_writable_root() -> None:
    """🔴 **Linux 워커 codex 는 agy 상태 폴더 하나만 쓰기로 연다** (`#774`).

    실측 2026-10-09: `.43` 에서 `workspace-write` 안의 agy 가 홈 읽기 전용으로
    `~/.gemini/antigravity-cli` 쓰기에 실패(3/3). 2026-10-10: `writable_roots` 하나로 SUCCESS.
    """
    root = 'sandbox_workspace_write.writable_roots=["/home/sim/.gemini/antigravity-cli"]'
    f = _facts("192.168.0.43", path="/t/NS")
    f.home = "/home/sim/"
    lin = R.worker_command(f, "t1", mode="codex")
    check("🔴 리눅스 + home → agy 상태 폴더를 writable_roots 로 연다 (끝 / 정리)",
          f"-c '{root}'" in lin, lin[:400])
    check("  쓰기는 여전히 작업공간으로 묶는다", "-s workspace-write" in lin, lin[:160])
    check("  네트워크 손잡이가 살아 있다",
          "sandbox_workspace_write.network_access=true" in lin, lin[:200])
    check("[주의] danger-full-access 로 넓히지 않는다", "danger-full-access" not in lin)

    fw = _facts("192.168.0.2", os_="windows", path="C:\\trunk\\NS")
    fw.home = "C:\\Users\\janus"
    win = R.worker_command(fw, "t1", mode="codex")
    check("[주의] 윈도우는 싣지 않는다 (#764 세션 1 중계)", "writable_roots" not in win, win[:300])
    check("  윈도우 unelevated 못박기는 그대로", 'windows.sandbox="unelevated"' in win)

    f0 = _facts("192.168.0.43", path="/t/NS")
    f0.home = ""
    lin0 = R.worker_command(f0, "t1", mode="codex")
    check("[주의] home 을 모르면 경로를 지어내지 않는다", "writable_roots" not in lin0, lin0[:300])

    cl = R.worker_command(f, "t1", mode="claude")
    check("[중요] claude 모드에는 영향이 없다", "writable_roots" not in cl, cl[:200])


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


def test_codex_error_report() -> None:
    message = "You've hit your usage limit. Try again later."
    out = "\n".join((json.dumps({"type": "item.completed", "item": {
        "type": "agent_message", "text": "a" * 1000}}),
        json.dumps({"type": "error", "message": message}),
        json.dumps({"type": "turn.failed", "error": {"message": message}})))
    notes = R.agent_report(out, rc=1)
    check("긴 본문 뒤 Codex 오류를 별도로 요약", any(message in n for n in notes), str(notes))
    check("같은 Codex 오류는 한번만 요약", sum(message in n for n in notes) == 1, str(notes))
    message = "ERROR failed: Permission denied — usage limit"
    raw = "\n".join((json.dumps({"type": "error", "message": message}),
                     json.dumps({"type": "turn.failed", "error": {"message": message}}),
                     "ERROR unrelated failure", "Traceback: unrelated failure"))
    notes = R.agent_report(raw, rc=1)
    check("구조화 오류는 raw scan과 중복 요약 안 함",
          sum(message in n for n in notes) == 1, str(notes))
    check("구조화와 일반 오류 합계는 3개 제한", len(notes) == R.AGENT_LOG_MAX, str(notes))


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
    check("기존 claim 은 work 범위를 생략한다", "work_id" not in api.calls[0][2])
    R.claim("w1", ["ue5"], work_id="W1", api=api)
    check("지정 work 를 claim 에 전달한다", api.calls[-1][2]["work_id"] == "W1")

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


def test_instruction_forbids_python_runs() -> None:
    """🔴 `#695` P4 — Python 조각도 서버·프로그램·테스트를 돌리지 않는다(UE 빌드 금지와 같은 문장)."""
    for s in ("do not start servers", "run the program or run tests", "Do not run UE5 builds"):
        check(f"지시문이 말한다: {s}", s in R.INSTRUCTION, R.INSTRUCTION[:80])


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


def test_self_repo_note() -> None:
    """`#783` — 마운트가 AXCluster 일 때만 「이 체크아웃의 AGENTS.md 는 마스터 세션용」 사실 문장을 붙인다."""
    src = (Path(__file__).resolve().parents[1]
           / "client" / "runtime" / "session1_conductor.py")
    ns: dict = {}
    exec(compile(ast.Module(body=[n for n in ast.parse(src.read_text()).body
                                  if isinstance(n, ast.Assign)
                                  and getattr(n.targets[0], "id", "") == "SELF_REPO_NOTE"],
                            type_ignores=[]), str(src), "exec"), ns)
    check("🔴 세션1 사본의 문장이 마스터와 글자까지 같다", ns.get("SELF_REPO_NOTE") == R.SELF_REPO_NOTE)
    check("  ASCII", R.SELF_REPO_NOTE.isascii())
    check("  명령형이 아니다 (do not/must 없음)",
          not any(w in R.SELF_REPO_NOTE.lower() for w in ("do not", "must", "ignore")))
    check("  AXCluster 마운트면 참", R.self_repo_mounted("AXCluster") is True)
    check("  다른 마운트면 거짓", R.self_repo_mounted("ModularStage") is False)
    orig = R.self_repo_mounted
    try:
        R.self_repo_mounted = lambda active=None: True
        on = R.worker_command(_facts(), "t1", ["a.py"])
        R.self_repo_mounted = lambda active=None: False
        off = R.worker_command(_facts(), "t1", ["a.py"])
    finally:
        R.self_repo_mounted = orig
    check("  자기 저장소면 지시문에 들어간다", "AX master's own repository" in on)
    check("  아니면 안 들어간다", "AX master's own repository" not in off)
    import importlib.util
    spec = importlib.util.spec_from_file_location("_s1", src)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    a_on = m.build_argv(Path("."), ["a.py"], (), self_repo=True)[-1]
    a_off = m.build_argv(Path("."), ["a.py"], ())[-1]
    check("  세션1 런처도 self_repo 참일 때만 붙인다",
          a_on.endswith(R.SELF_REPO_NOTE) and "own repository" not in a_off)


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
        sent = {}

        def fake_write(facts, path, content, **kwargs):
            import json
            sent.update(json.loads(content))

        def fake_ssh(host, user, cmd, timeout=None, **kw):
            if "done.flag" in cmd:
                polls["n"] += 1
                return 0, ("DONE" if polls["n"] > done_after else "WAIT")
            return 0, ""

        def fake_read(f, p):
            if p.endswith("done.flag"):
                return sent["request_id"]
            if p.endswith("out.txt"):
                return "RESULT: DONE"
            if p.endswith("rc.txt"):
                return "0"
            if p.endswith("launcher.log") and launcher_log is not None:
                return launcher_log
            raise FileNotFoundError(p)

        B._ssh, B._remote_write, B._remote_read = fake_ssh, fake_write, fake_read
        try:
            rc, out = R.run_worker_session1(
                facts, "t1", files=["Source/A.cpp"], timeout=timeout,
                sleeper=lambda s: None, logf=lines.append, now=lambda: next(ticks),
                popup=lambda f, since: [POPUP], cancelled=lambda: False, cleanup_timeout=0)
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
    L.build_argv = lambda r, files, approvals=(), self_repo=False: [_sys.executable, "-c", "print('RESULT: DONE')"]
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
        L.build_argv = lambda r, files, approvals=(), self_repo=False: [_sys.executable, "-c",
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


def test_session1_attempt_isolation() -> None:
    """#695: retry must run a fresh subprocess without removing old evidence."""
    import json
    import tempfile
    from types import SimpleNamespace
    from unittest.mock import patch
    from master.client import bundle as B

    L = _load_launcher()
    with tempfile.TemporaryDirectory(prefix="ax-s1-retry-") as temp:
        root = Path(temp)
        legacy = root / ".ax/session1/t1"
        legacy.mkdir(parents=True)
        (legacy / "job.json").write_text('{"task_id":"t1"}')
        (legacy / "done.flag").write_text("done")
        (legacy / "out.txt").write_text("OLD FAILURE")
        paths, jobs, executions = [], [], []
        facts = SimpleNamespace(host="192.168.0.2", user="janus", windows=True,
                                path="C:\\trunk\\NS", os="windows")

        def write(f, rel, content, **kw):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            paths.append(p.parent)
            if rel.endswith("job.json"):
                jobs.append(json.loads(content))

        def argv(r, files, approvals=(), self_repo=False):
            executions.append(1)
            return [sys.executable, "-c", f"print('FRESH {len(executions)}')"]

        def ssh(host, user, cmd, **kw):
            if "done.flag" in cmd:
                return 0, "DONE" if (paths[-1] / "done.flag").exists() else "WAIT"
            L.main()
            return 0, ""

        def read(f, rel):
            relative = rel.removeprefix(f.path + "\\").replace("\\", "/")
            return (root / relative).read_text()

        with patch.object(L, "find_root", lambda: root), patch.object(L, "build_argv", argv), \
                patch.object(B, "_remote_write", write), patch.object(B, "_ssh", ssh), \
                patch.object(B, "_remote_read", read):
            results = [R.run_worker_session1(facts, "t1", files=[], popup=lambda *a: [], cancelled=lambda: False)
                       for _ in range(2)]
            check("#695 같은 task 재시도도 새 프로세스 둘", len(executions) == 2)
            check("#695 옛 출력 대신 각 시도의 새 결과", results == [(0, "FRESH 1\n"), (0, "FRESH 2\n")], str(results))
            check("#695 job 경로와 request_id 모두 다름", paths[0] != paths[1]
                  and jobs[0]["request_id"] != jobs[1]["request_id"])
            check("#695 완료 마커도 해당 request_id", all(
                (p / "done.flag").read_text() == j["request_id"] for p, j in zip(paths, jobs)))
            check("#695 옛 실패 증거 보존", (legacy / "out.txt").read_text() == "OLD FAILURE")
            L.main()
            check("#695 완료 시도를 다시 실행하지 않음", len(executions) == 2)
            original = B._remote_read
            with patch.object(B, "_remote_read", lambda f, rel:
                              "old-request" if rel.endswith("done.flag") else original(f, rel)):
                rc, out = R.run_worker_session1(facts, "t1", files=[], popup=lambda *a: [], cancelled=lambda: False, cleanup_timeout=0)
            check("#695 다른 request 결과는 성공으로 회수하지 않음", rc == 1 and "request_id" in out, out)


def test_session1_cancellation() -> None:
    """#796: abandoned attempts cannot run later; cancellation stops only their tree."""
    import json
    import tempfile
    import threading
    import time
    import subprocess
    from unittest.mock import patch
    from types import SimpleNamespace
    from master.client import bundle as B

    L = _load_launcher()
    with tempfile.TemporaryDirectory(prefix="ax-s1-cancel-") as temp:
        root = Path(temp)
        def job(name, **extra):
            d = root / L.JOB_DIR / name / "request"
            d.mkdir(parents=True)
            (d / L.JOB).write_text(json.dumps({"task_id": name, "request_id": name,
                                               "timeout": 30, **extra}))
            return d
        cancelled = job("cancelled")
        (cancelled / L.CANCEL).write_text("cancel")
        expired = job("expired", expires_at=time.time() - 1)
        executions = []
        def argv(*args, **kwargs):
            executions.append(1)
            return [sys.executable, "-c", "print('RESULT: DONE')"]
        with patch.object(L, "find_root", lambda: root), patch.object(L, "build_argv", argv):
            L.main()
            L.main()
        check("#796 취소·만료된 미실행 job은 뒤늦게 재실행하지 않음", not executions)
        check("#796 취소·만료도 해당 시도 완료 마커와 실패 결과 기록", all(
            (d / L.DONE).exists() and (d / L.RC).read_text() == "1" for d in (cancelled, expired)))

        active = job("active")
        pidfile = root / "child.pid"
        child = "import time; time.sleep(120)"
        code = ("import subprocess,time,pathlib; "
                f"p=subprocess.Popen([{sys.executable!r},'-c',{child!r}]); "
                f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); time.sleep(120)")
        with patch.object(L, "build_argv", lambda *a, **k: [sys.executable, "-c", code]):
            thread = threading.Thread(target=L.run_job, args=(root, active))
            thread.start()
            deadline = time.monotonic() + 10
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            started = pidfile.exists()
            (active / L.CANCEL).write_text("cancel")
            thread.join(timeout=10)
        check("#796 실행 중 취소는 제한시간까지 기다리지 않고 끝남", started and not thread.is_alive())
        if started and sys.platform.startswith("linux"):
            pid = pidfile.read_text()
            stat = Path(f"/proc/{pid}/stat")
            check("#796 실제 자식 프로세스도 실행 종료", not stat.exists() or stat.read_text().split()[2] == "Z")
        check("#796 취소 이유 보존·relay 표시 제거", "요청자 취소" in (active / L.OUT).read_text()
              and not (root / L.AGY_ROOT / L.AGY_MARK).exists())

        # A genuine communicate exception used to lose the running process handle.
        failed = job("exception")
        real_popen = subprocess.Popen
        processes = []
        class BrokenPipe:
            def __init__(self, *a, **kw):
                self.proc = real_popen([sys.executable, "-c", "import time; time.sleep(120)"], **kw)
                processes.append(self.proc)
            def __getattr__(self, name):
                return getattr(self.proc, name)
            def communicate(self, **kwargs):
                raise OSError("injected pipe failure")
        with patch.object(L.subprocess, "Popen", BrokenPipe), patch.object(L, "build_argv", argv):
            L.run_job(root, failed)
        check("#796 communicate 예외도 실제 실행 프로세스를 회수", processes[-1].poll() is not None
              and "injected pipe failure" in (failed / L.OUT).read_text())
        req = root / L.AGY_ROOT / "in" / "failure"
        req.mkdir(parents=True)
        (req / "BRIEF.md").write_text("test")
        # `#830` — 모델이 없으면 agy 를 부르지 않으므로(그러면 아래 검사가 공허하게 통과한다) 값을 둔다
        (root / ".ax" / "config.json").write_text(json.dumps({"backends": {"agy_model": "gemini-3.8-flash-medium"}}))
        relay = L.AgyRelay(root, failed)
        with patch.object(L.subprocess, "Popen", BrokenPipe):
            relay.serve("failure")
        check("#796 agy communicate 예외도 프로세스를 회수", processes[-1].poll() is not None
              and relay.proc is None)
        nonzero = job("nonzero")
        with patch.object(L, "build_argv", lambda *a, **k: [sys.executable, "-c",
                                      "import sys; print('quota failure'); sys.exit(3)"]):
            result = L.run_job(root, nonzero)
        check("#796 비영점 정상 종료도 원래 rc·본문·종료 로그를 보존", result == 3
              and "quota failure" in (nonzero / L.OUT).read_text()
              and "codex 종료 — rc=3" in (nonzero / L.LOG).read_text())

        facts = SimpleNamespace(host="fake", user="fake", windows=True, path="C:\\AXCluster", os="windows")
        writes = []
        def write(f, rel, content, **kw):
            writes.append((rel, content))
        with patch.object(B, "_remote_write", write), patch.object(B, "_ssh", lambda *a, **k: (1, "failed")):
            rc, _ = R.run_worker_session1(facts, "failed", cancelled=lambda: False, logf=lambda _: None, cleanup_timeout=0)
        check("#796 런처 기동 실패 시 job을 취소함", rc == 1 and writes[-1][0].endswith("cancel.flag"))
        writes.clear()
        def partial_write(f, rel, content, **kw):
            write(f, rel, content, **kw)
            if rel.endswith("job.json"):
                raise OSError("remote write completed but reply lost")
        with patch.object(B, "_remote_write", partial_write):
            rc, out = R.run_worker_session1(facts, "partial", cancelled=lambda: False,
                                          logf=lambda _: None, cleanup_timeout=0)
        check("#796 job 부분 전송 후 예외도 남은 시도를 취소함", rc == 1
              and writes[0][0].endswith("job.json") and writes[-1][0].endswith("cancel.flag")
              and writes[0][0].rsplit("/", 1)[0] == writes[-1][0].rsplit("/", 1)[0])
        writes.clear()
        with patch.object(B, "_remote_write", write), patch.object(B, "_ssh", lambda *a, **k: (0, "WAIT")), \
                patch.object(R, "_api", lambda *a, **k: {"status": "cancelled"}):
            rc, out = R.run_worker_session1(facts, "cancelled", logf=lambda _: None, cleanup_timeout=0)
        check("#796 큐의 명시 취소를 원격 시도에 전파", rc == 1 and "취소" in out
              and writes[-1][0].endswith("cancel.flag"))
        check("#796 요청 기한을 job에 전달", "expires_at" in json.loads(writes[0][1]))
        writes.clear()
        def denied(*a, **k):
            if a[1].endswith("cancel.flag"):
                raise OSError("network disconnected")
            write(*a, **k)
        with patch.object(B, "_remote_write", denied), patch.object(B, "_ssh", lambda *a, **k: (0, "WAIT")):
            rc, out = R.run_worker_session1(facts, "cancelled", cancelled=lambda: True,
                                          logf=lambda _: None, cleanup_timeout=0)
        check("#796 취소 전송 실패를 전송 성공으로 보고하지 않음", "전달 실패" in out and "미확인" in out)

        writes.clear()
        def acknowledged(*a, **k):
            if "done.flag" in a[2]:
                return 0, json.loads(writes[0][1])["request_id"]
            return 0, ""
        with patch.object(B, "_remote_write", write), patch.object(B, "_ssh", acknowledged):
            rc, out = R.run_worker_session1(facts, "cancelled", cancelled=lambda: True, logf=lambda _: None)
        check("#796 취소 반환 전 해당 시도 런처 종료 확인", "런처 종료 확인" in out and "미확인" not in out)

        writes.clear()
        def interrupted(_):
            raise RuntimeError("requester interrupted")
        with patch.object(B, "_remote_write", write), patch.object(B, "_ssh", lambda *a, **k: (0, "WAIT")), \
                patch.object(R, "_api", side_effect=OSError("unavailable")):
            try:
                R.run_worker_session1(facts, "interrupted", sleeper=interrupted,
                                      logf=lambda _: None, cleanup_timeout=0)
            except RuntimeError:
                pass
        check("#796 큐 조회 실패는 취소로 오탐하지 않고 요청자 예외에서 취소", writes[-1][0].endswith("cancel.flag")
              and "대기 중단" in writes[-1][1])


def test_delegation_calls() -> None:
    """🔴 `#764` 3a — 지휘자의 위임을 **명령 실행 이벤트로만** 센다. claude 출력은 「미상」이다."""
    def ev(cmd, status="completed", code=0, kind="item.completed"):
        return json.dumps({"type": kind, "item": {"type": "command_execution", "command": cmd,
                                                  "status": status, "exit_code": code}})
    agy = "/bin/bash -lc 'agy --dangerously-skip-permissions --output-format json -p hi'"
    out = "\n".join([
        json.dumps({"type": "thread.started"}),
        ev(agy, "in_progress", None, "item.started"), ev(agy),
        ev("codex exec --json q"), ev("curl -s http://192.168.0.57:8102/generate"),
        ev("grep -rn agy master/work/lanes.py"), ev("rg -n \"agy\" docs"),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                                                       "text": "agy -p 로 맡기겠다"}}),
    ])
    known, calls = R.delegation_calls(out)
    kinds = [k for k, _ in calls]
    check("[중요] codex 이벤트면 잴 수 있다", known)
    check("  agy·codex·local 셋 · 명령당 한 줄", kinds == ["agy", "codex", "local"], str(calls))
    check("  마지막 상태로 적는다", "상태 completed · 종료 코드 0" in calls[0][1], calls[0][1])
    check("[중요] 낱말 검색·말은 위임이 아니다", len(calls) == 3, str(calls))
    notes = R.delegation_notes(out)
    check("  노트 — 건마다 한 줄", len(notes) == 3 and notes[0].startswith("[지휘자] 위임: agy"), str(notes))
    relay = "\n".join([json.dumps({"type": "thread.started"}),
                        ev('powershell.exe -Command "Set-Content .agy-work/in/1/BRIEF.md x '
                           'New-Item -ItemType File .agy-work/in/1.go | Out-Null"'),
                        ev("powershell.exe -Command 'while (-not (Test-Path .agy-work/out/1.done)) {}'")])
    k3, c3 = R.delegation_calls(relay)
    check("[중요] 런처 기록이 없으면 .go 경로로 「중계 추정」 · 대기 명령은 아니다",
          k3 and [k for k, _ in c3] == ["agy(중계 추정)"], str(c3))
    none = "\n".join([json.dumps({"type": "thread.started"}), ev("cat src/a.py")])
    check("  이벤트는 있는데 위임이 없으면 「없음」",
          R.delegation_notes(none) == ["[지휘자] 위임 없음 — 명령 이벤트에 agy·codex exec·브로커 호출이 없다"],
          str(R.delegation_notes(none)))
    claude = json.dumps({"type": "result", "result": "RESULT: DONE", "usage": {}})
    k2, c2 = R.delegation_calls(claude)
    check("[중요] claude JSON 은 「미상」 — 0 으로 접지 않는다", not k2 and c2 == []
          and R.delegation_notes(claude)[0].startswith("[지휘자] 위임 미상"), str(R.delegation_notes(claude)))
    check("  빈 출력도 미상 · 예외 없음", R.delegation_notes("")[0].startswith("[지휘자] 위임 미상"))


def test_relay_events_are_authoritative() -> None:
    """🔴 `#767` — 세션1 중계 위임은 **런처가 처리한 기록**으로 센다. 실측 b3deda91: 노트 3줄 · 실제 2건 —
    `.go` 를 조회만 한 `Get-Item` 명령까지 셌다."""
    def ev(cmd):
        return json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": cmd,
                                                              "status": "completed", "exit_code": 0}})
    ll = ("2026-10-09 16:52:09 agy 중계 시작 — 요청 1 · 실행 파일 C:\\x\\agy.EXE\n"
          "2026-10-09 16:54:24 agy 중계 끝 — 요청 1 · rc=0 · 135초 · 출력 9888자\n"
          "2026-10-09 16:54:26 agy 중계 시작 — 요청 2 · 실행 파일 C:\\x\\agy.EXE\n"
          "2026-10-09 17:01:39 agy 중계 끝 — 요청 2 · rc=0 · 432초 · 출력 20968자\n"
          "2026-10-09 17:02:32 agy 중계 종료 — 처리 2건\n")
    rel = R.relay_events(ll)
    check("런처 로그 → ax.relay 이벤트 2건", len(rel) == 2
          and json.loads(rel[1]) == {"type": "ax.relay", "request": "2", "rc": 0, "seconds": 432, "chars": 20968},
          str(rel))
    cmds = [json.dumps({"type": "thread.started"}),
            ev('powershell.exe -Command "New-Item -ItemType File .agy-work\\in\\1.go"'),
            ev('powershell.exe -Command "New-Item -ItemType File .agy-work\\in\\2.go"'),
            ev("powershell.exe -Command \"Get-Item -LiteralPath '.agy-work\\in\\2.go','.agy-work\\out\\1.done'\"")]
    out = "\n".join(cmds + rel)
    known, calls = R.delegation_calls(out)
    check("[중요] 런처 기록이 있으면 그것만 센다 — 2건 (조회 명령·추정은 버린다)",
          known and [k for k, _ in calls] == ["agy(중계)", "agy(중계)"], str(calls))
    check("  노트에 요청 번호·rc·초", "요청 2 · rc=0 · 432초" in R.delegation_notes(out)[1],
          str(R.delegation_notes(out)))
    k2, c2 = R.delegation_calls("\n".join(rel))
    check("  명령 이벤트 없이 런처 기록만 있어도 잴 수 있다", k2 and len(c2) == 2, str(c2))
    check("  빈 로그는 이벤트 0", R.relay_events("") == [] and R.relay_events("agy 중계 대기 — x") == [])


def test_session1_after_appends_relay_events() -> None:
    """`#767` — `_session1_after` 가 런처 로그의 중계 기록을 결과 끝에 싣는다(조각 기록까지 가게)."""
    import types as _types
    from master.client import bundle as _b
    ll = "2026-10-09 16:54:24 agy 중계 끝 — 요청 1 · rc=0 · 135초 · 출력 9888자\n"
    saved = _b._remote_read
    _b._remote_read = lambda f, p: ll
    try:
        got = R._session1_after(_types.SimpleNamespace(host="h"), "t", "b", "/", "", "BODY",
                                log=lambda m: None, popup=lambda f, since: [])
    finally:
        _b._remote_read = saved
    check("[중요] 결과 끝에 ax.relay 줄이 붙는다", got.startswith("BODY")
          and '"type": "ax.relay"' in got and '"request": "1"' in got, got)
    check("  위임 노트가 그것을 센다", R.delegation_notes(got)[0].startswith("[지휘자] 위임: agy(중계) — 요청 1"),
          str(R.delegation_notes(got)))


def test_instruction_asks_delegation() -> None:
    """`#764` — 지시문이 위임과 그 보고를 말한다(ASCII 유지 · 세션1 사본과 같은 글자는 별도 검사)."""
    for s_ in ("Read and edit the target files yourself",
               "delegate research to agy only when you judge it necessary",
               "file size is not a reason to delegate", "not delegating is not a failure",
               "write their bodies yourself - do not delegate body drafts",
               ".agents/skills/ax-work/SKILL.md", ".ax/config.json",
               "will not list them; open them directly",
               "list what you delegated", ".agy-work/out/"):
        check(f"지시문이 말한다: {s_}", s_ in R.INSTRUCTION, R.INSTRUCTION[:80])
    check("  여전히 ASCII", R.INSTRUCTION.isascii())
    check("  본문 초안 위임 문장이 없다 (#784)", "Delegate bulk body drafts" not in R.INSTRUCTION)


def test_delegation_failure_blocks() -> None:
    """`#774` D — 위임 실패는 다음 활성 레인으로 넘길 수 있고, 시도한 백엔드가 모두 실패하면
    직접 하지 않고 `RESULT: BLOCKED` 로 멈춘다(10-09 `#764` 를 뒤집음 · 사용자 결정 2026-10-10)."""
    for s_ in ("If a delegation you attempt fails", "non-zero exit, timeout, or an empty or unusable response",
               "retry that work with the next enabled backend in the lane order",
               "if every backend you tried fails, do not do that work yourself",
               "keep the raw response files in .agy-work/out/", "state each backend, exit code and error",
               "stop with RESULT: BLOCKED", "not enabled in .ax/config.json is not a failure"):
        check(f"지시문이 말한다: {s_}", s_ in R.INSTRUCTION, R.INSTRUCTION[:80])
    check("[중요] 옛 「직접 하라」 문구가 없다",
          "do that work yourself - it is not a reason to stop" not in R.INSTRUCTION)
    check("  여전히 ASCII", R.INSTRUCTION.isascii())
    src = (Path(__file__).resolve().parents[1] / "client" / "runtime"
           / "session1_conductor.py").read_text(encoding="utf-8")
    check("[중요] 세션1 사본도 같은 문구다", "stop with RESULT: BLOCKED" in src
          and "if every backend you tried fails" in src
          and "next enabled backend in the lane order" in src
          and "it is not a reason to stop" not in src)


def test_session1_agy_relay() -> None:
    """🔴 `#764` ⓑ — 런처가 codex 가 도는 동안 `.agy-work/in/<n>.go` 를 받아 **샌드박스 밖에서** agy 를 돌린다.

    [주의] 실 codex·agy 를 부르지 않는다 — 지휘자는 파이썬 한 줄(요청을 쓰고 `.done` 을 기다린다),
    agy 는 PATH 앞의 가짜 스크립트다. 표시 파일(`VIA_LAUNCHER`)은 중계가 도는 동안에만 있다.
    """
    import json as _json
    import os
    import stat
    import sys as _sys
    import tempfile

    L = _load_launcher()
    with tempfile.TemporaryDirectory(prefix="ax-s1-agy-") as tmp:
        root = Path(tmp)
        d = root / ".ax" / "session1" / "t2"
        d.mkdir(parents=True)
        (d / "job.json").write_text(_json.dumps({"task_id": "t2", "files": ["a.py"], "timeout": 60}),
                                    encoding="utf-8")
        (root / ".ax" / "config.json").write_text(
            _json.dumps({"backends": {"agy_model": "gemini-3.8-flash-medium"}}), encoding="utf-8")
        bindir = root / "bin"
        bindir.mkdir()
        fake = bindir / "agy"
        fake.write_text("#!/usr/bin/env python3\nimport json,sys,os\n"
                        # `#830` — 실제 agy 처럼 --log-file 에 모델 label 줄을 남긴다
                        "a=sys.argv[1:]\n"
                        "open(a[a.index('--log-file')+1],'w').write("
                        "'Propagating selected model override to backend: label=\"Gemini 3.8 Flash (Medium)\"\\n')\n"
                        "print(json.dumps({'status':'SUCCESS','response':'ok:'+os.path.basename(os.getcwd()),"
                        "'argv':sys.argv[1:]}))\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        conductor = (
            "import pathlib,time,sys\n"
            "b=pathlib.Path('.agy-work')\n"
            "print('mark', (b/'VIA_LAUNCHER').exists())\n"
            "(b/'in'/'1').mkdir(parents=True,exist_ok=True); (b/'in'/'1'/'BRIEF.md').write_text('q')\n"
            "(b/'in'/'1.go').write_text('')\n"
            "(b/'in'/'bad name.go').write_text('')\n"
            "(b/'in'/'2.go').write_text('')\n"
            "t=0\n"
            "while not ((b/'out'/'1.done').exists() and (b/'out'/'2.done').exists()) and t<200:\n"
            "    time.sleep(0.1); t+=1\n"
            "print('one', (b/'out'/'1.done').read_text(), (b/'out'/'1.json').read_text().strip())\n"
            "print('two', (b/'out'/'2.done').read_text(), (b/'out'/'2.err').read_text())\n"
            "print('RESULT: DONE')\n")
        saved_argv, saved_path = L.build_argv, os.environ.get("PATH", "")
        L.build_argv = lambda r, files, approvals=(), self_repo=False: [_sys.executable, "-c", conductor]
        os.environ["PATH"] = f"{bindir}{os.pathsep}{saved_path}"
        saved_poll = L.AGY_POLL
        L.AGY_POLL = 0.1
        try:
            rc = L.run_job(root, d)
            out = (d / "out.txt").read_text(encoding="utf-8")
            log = (d / "launcher.log").read_text(encoding="utf-8")
            check("지휘자가 끝났다", rc == 0 and "RESULT: DONE" in out, out[-300:])
            check("[중요] 중계가 도는 동안 VIA_LAUNCHER 가 있다", "mark True" in out, out[:200])
            check("  끝나면 표시를 지운다", not (root / ".agy-work" / "VIA_LAUNCHER").exists())
            one = [ln for ln in out.splitlines() if ln.startswith("one ")]
            check("[중요] 요청 1 → agy 응답 · done=0", bool(one) and one[0].startswith("one 0 ")
                  and '"ok:1"' in one[0], str(one))
            if one:
                args = _json.loads(one[0].split(" ", 2)[2]).get("argv", [])
                check("  고정 플래그 · --add-dir 는 그 요청 폴더 · -p 는 프롬프트 바로 앞",
                      args[:3] == ["--dangerously-skip-permissions", "--output-format", "json"]
                      and Path(args[args.index("--add-dir") + 1]).name == "1"
                      and args[-2] == "-p" and args[-1] == L.AGY_PROMPT, str(args))
                check("[중요] #830 --model 은 설정의 정본 id",
                      "--model" in args and args[args.index("--model") + 1] == "gemini-3.8-flash-medium",
                      str(args))
                check("  #830 --log-file 은 out/<요청>.log",
                      "--log-file" in args
                      and Path(args[args.index("--log-file") + 1]) == root / ".agy-work" / "out" / "1.log",
                      str(args))
            two = [ln for ln in out.splitlines() if ln.startswith("two ")]
            check("  BRIEF.md 없는 요청은 rc 2 · 사유", bool(two) and two[0].startswith("two 2 ")
                  and "BRIEF.md" in two[0], str(two))
            check("[중요] 이름 규칙 밖 요청은 처리하지 않는다",
                  not (root / ".agy-work" / "out" / "bad name.done").exists())
            for want in ("agy 중계 대기", "agy 중계 시작 — 요청 1", "agy 중계 끝 — 요청 1 · rc=0",
                         "모델 gemini-3.8-flash-medium", "요청 모델 gemini-3.8-flash-medium",
                         "실제 gemini-3.8-flash-medium (출처 log)", "판정 일치",
                         "agy 중계 종료 — 처리"):
                check(f"  launcher.log 에 「{want}」", want in log, log[-600:])
        finally:
            L.build_argv, L.AGY_POLL = saved_argv, saved_poll
            os.environ["PATH"] = saved_path
    check("중계 테스트 임시 루트 정리", not root.exists(), str(root))


def test_session1_agy_model_refusal() -> None:
    """🔴 `#830` — `backends.agy_model` 이 없거나 정본 id 가 아니거나 Argon 이면 agy 를 **부르지 않는다**.

    별칭이 조용히 Argon 으로 풀려 한도를 태웠다. 폴백 없음 — 실패 결과(rc 78 · `.err` 사유)와 로그 줄만 남긴다.
    """
    import json as _json
    import tempfile
    from unittest.mock import patch

    L = _load_launcher()
    cases = (("설정 파일 없음", None, "를 못 읽었다"),
             ("backends 없음", {}, "agy_model 이 없다"),
             ("빈 값", {"backends": {"agy_model": ""}}, "agy_model 이 없다"),
             ("별칭(공백·대문자)", {"backends": {"agy_model": "Gemini 3.8 Flash"}}, "정본 id 모양이 아니다"),
             ("옵션 주입 모양", {"backends": {"agy_model": "--yolo"}}, "정본 id 모양이 아니다"),
             ("문자열 아님", {"backends": {"agy_model": ["gemini-3.8-flash-medium"]}}, "정본 id 모양이 아니다"),
             ("gemini- 아님", {"backends": {"agy_model": "claude-sonnet-4"}}, "gemini- 로 시작하지 않는다"),
             ("Argon", {"backends": {"agy_model": "gemini-4-argon"}}, "Argon"))
    for label, cfg, why in cases:
        with tempfile.TemporaryDirectory(prefix="ax-s1-model-") as tmp:
            root = Path(tmp)
            d = root / ".ax" / "session1" / "t" / "r"
            d.mkdir(parents=True)
            if cfg is not None:
                (root / ".ax" / "config.json").write_text(_json.dumps(cfg), encoding="utf-8")
            req = root / L.AGY_ROOT / "in" / "1"
            req.mkdir(parents=True)
            (req / "BRIEF.md").write_text("q", encoding="utf-8")
            calls = []
            with patch.object(L.subprocess, "Popen", lambda *a, **k: calls.append(a) or 1 / 0):
                L.AgyRelay(root, d).serve("1")
            out = root / L.AGY_ROOT / "out"
            log = (d / L.LOG).read_text(encoding="utf-8")
            err = (out / "1.err").read_text(encoding="utf-8")
            check(f"[중요] #830 {label} → agy 를 부르지 않는다", not calls, str(calls))
            check(f"  {label} → rc {L.AGY_BAD_MODEL_RC} · .err 에 사유",
                  (out / "1.done").read_text() == str(L.AGY_BAD_MODEL_RC) and why in err, err)
            check(f"  {label} → 거절 로그 줄 · 끝 줄은 마스터 정규식 그대로",
                  "agy 중계 거절 — 요청 1" in log and why in log
                  and R._RELAY_DONE.search(log) is not None
                  and R._RELAY_DONE.search(log).group(2) == str(L.AGY_BAD_MODEL_RC), log)
    with tempfile.TemporaryDirectory(prefix="ax-s1-model-") as tmp:
        root = Path(tmp)
        (root / ".ax").mkdir()
        (root / ".ax" / "config.json").write_text(
            _json.dumps({"backends": {"agy_model": "gemini-3.8-flash-medium"}}), encoding="utf-8")
        check("#830 정본 id 는 통과 — agy_model() → (id, 빈 사유)", L.agy_model(root) == ("gemini-3.8-flash-medium", ""),
              str(L.agy_model(root)))


def test_session1_agy_model_verdict() -> None:
    """🔴 `#830` ⓐ — 중계가 `--log-file` 로그(배달된 `work/usage.py` 파서)로 **실제 모델**을 대조한다.

    실제 ≠ 요청 · 실제 미상 · 파서 로드 실패는 거절(rc 79)이다. `.json`·`.log` 는 증거로 남는다.
    [주의] 실 agy 를 부르지 않는다 — 환경변수로 움직이는 가짜 스크립트다.
    """
    import json as _json
    import os
    import stat
    import tempfile
    from unittest.mock import patch

    L = _load_launcher()
    want = "gemini-3.8-flash-medium"
    fake_src = ("#!/usr/bin/env python3\nimport json,os,sys\n"
                "a=sys.argv[1:]\nlabel=os.environ.get('AX_FAKE_LABEL','')\n"
                "if label:\n"
                "    open(a[a.index('--log-file')+1],'w').write("
                "'x\\nPropagating selected model override to backend: label=\"'+label+'\"\\n')\n"
                "env={'status':'SUCCESS','response':'BODY'}\n"
                "if os.environ.get('AX_FAKE_ENV_MODEL'): env['model']=os.environ['AX_FAKE_ENV_MODEL']\n"
                "print(json.dumps(env)); sys.exit(int(os.environ.get('AX_FAKE_RC','0')))\n")

    def run(label="", env_model="", fake_rc=0, load=None):
        tmp = tempfile.mkdtemp(prefix="ax-s1-verdict-")
        root = Path(tmp)
        d = root / ".ax" / "session1" / "t" / "r"
        d.mkdir(parents=True)
        (root / ".ax" / "config.json").write_text(_json.dumps({"backends": {"agy_model": want}}))
        req = root / L.AGY_ROOT / "in" / "1"
        req.mkdir(parents=True)
        (req / "BRIEF.md").write_text("q")
        fake = root / "agy"
        fake.write_text(fake_src)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = {"AX_FAKE_LABEL": label, "AX_FAKE_ENV_MODEL": env_model, "AX_FAKE_RC": str(fake_rc)}
        calls = []
        real_popen = L.subprocess.Popen
        def popen(*a, **k):
            calls.append(a)
            return real_popen(*a, **k)
        with patch.dict(os.environ, env), patch.object(L, "_agy_exe", lambda: str(fake)), \
                patch.object(L.subprocess, "Popen", popen), \
                patch.object(L, "_load_usage", load or L._load_usage):
            L.AgyRelay(root, d).serve("1")
        out = root / L.AGY_ROOT / "out"
        res = {"rc": (out / "1.done").read_text(), "json": (out / "1.json").read_text() if (out / "1.json").exists() else "",
               "err": (out / "1.err").read_text(), "log_kept": (out / "1.log").exists(),
               "launcher": (d / L.LOG).read_text(encoding="utf-8"), "calls": len(calls)}
        import shutil as _sh
        _sh.rmtree(tmp)
        return res

    r = run(label="Gemini 3.8 Flash (Medium)")
    check("[중요] #830 로그 모델 = 요청 → rc 0 · 판정 일치", r["rc"] == "0" and "판정 일치" in r["launcher"]
          and "출력을 버린다" not in r["err"], str(r))
    r = run(label="Gemini 4 Argon")
    check("🔴 [중요] #830 로그 모델 ≠ 요청 → rc 79", r["rc"] == str(L.AGY_MODEL_REJECT_RC), str(r))
    check("  불일치 — .json·.log 증거 보존 · .err 에 사유",
          '"BODY"' in r["json"] and r["log_kept"] and "모델 불일치 — 요청 gemini-3.8-flash-medium · 실제 gemini-4-argon"
          in r["err"], str(r))
    check("  불일치 — 런처 로그에 요청·실제·판정 거절 · 끝 줄은 마스터 정규식 그대로",
          "실제 gemini-4-argon (출처 log)" in r["launcher"] and "판정 거절" in r["launcher"]
          and R._RELAY_DONE.search(r["launcher"]).group(2) == str(L.AGY_MODEL_REJECT_RC), r["launcher"])
    r = run(env_model="Gemini 3.8 Flash (Medium)")
    check("#830 로그에 모델이 없으면 봉투 모델(정규화)로 판정 → 일치",
          r["rc"] == "0" and "(출처 envelope)" in r["launcher"] and "판정 일치" in r["launcher"], str(r))
    r = run()
    check("🔴 [중요] #830 실제 모델 미상 → 거절 rc 79", r["rc"] == str(L.AGY_MODEL_REJECT_RC)
          and "실제 모델 미상" in r["err"] and "실제 (미상)" in r["launcher"] and '"BODY"' in r["json"], str(r))
    r = run(label="Gemini 4 Argon", fake_rc=3)
    check("#830 agy 자체 실패(rc 3)는 rc 를 그대로 두고 사유만 덧붙인다",
          r["rc"] == "3" and "모델 불일치" in r["err"], str(r))
    def broken():
        raise FileNotFoundError("work/usage.py 가 배달되지 않았다")
    r = run(label="Gemini 3.8 Flash (Medium)", load=broken)
    check("🔴 [중요] #830 파서 로드 실패 → agy 를 부르지 않고 rc 79",
          r["calls"] == 0 and r["rc"] == str(L.AGY_MODEL_REJECT_RC)
          and "파서(work/usage.py)를 못 불러왔다" in r["err"]
          and "agy 중계 거절 — 요청 1" in r["launcher"], str(r))
    check("#830 저장소에서 실행하면 master/work/usage.py 를 로드한다",
          hasattr(L._load_usage(), "parse_agy_log"))


def test_session1_relay_start_failure() -> None:
    """표시·로그 쓰기 실패 뒤 실제 시작된 중계 스레드를 남기지 않는다."""
    import tempfile
    from unittest.mock import patch

    L = _load_launcher()
    for failure in ("marker", "log", "start"):
        with tempfile.TemporaryDirectory(prefix="ax-s1-start-") as tmp:
            root = Path(tmp)
            d = root / "job"
            d.mkdir()
            relays = []
            original = L.AgyRelay

            def make_relay(*args):
                relay = original(*args)
                relays.append(relay)
                return relay

            marker = root / L.AGY_ROOT / L.AGY_MARK
            write_text = Path.write_text

            def write(path, *args, **kwargs):
                if failure == "marker" and path == marker:
                    raise OSError("marker fixture")
                return write_text(path, *args, **kwargs)

            try:
                with patch.object(L, "AgyRelay", side_effect=make_relay), \
                        patch.object(Path, "write_text", write), \
                        patch.object(L, "_log", side_effect=OSError("log fixture")
                                     if failure == "log" else None), \
                        patch.object(original, "start", side_effect=RuntimeError("start fixture")) \
                        if failure == "start" else patch.object(L, "AGY_POLL", 0.1):
                    result = L._start_relay(root, d)
                check(f"{failure} 실패는 None", result is None)
                check(f"{failure} 실패 뒤 스레드 없음", len(relays) == 1
                      and not relays[0].is_alive())
                check(f"{failure} 실패 뒤 표시 없음", not marker.exists())
                if failure != "start":
                    check(f"{failure} 실패 전에 실제 시작됨", relays[0].ident is not None)
            finally:
                for relay in relays:
                    if relay.ident is not None:
                        relay.shutdown()


def test_claude_auth_runtime() -> None:
    from unittest.mock import patch
    raw = "Failed to authenticate: OAuth session expired and could not be refreshed"
    with patch("master.work.conductor_auth.check_claude_auth", return_value={"ok": False, "reason": "검사 저장 경로 확인 필요"}), \
         patch.object(R.bundle, "_ssh") as ssh:
        rc, out = R.run_worker(_facts(), "t1")
        check("인증 사전 검사 실패는 실제 실행을 막는다", rc == 1 and not ssh.called)
        check("검사 실패 원인과 고정 표식 보존", "AX_CLAUDE_AUTH_FAILED" in out and "저장 경로" in out)
    for process_rc, output in ((1, raw), (1, '{"result":"' + raw + '"}' + "x" * 500),
                               (0, '{"is_error":true,"result":"' + raw + '"}')):
        with patch("master.work.conductor_auth.check_claude_auth", return_value={"ok": True}), \
             patch("master.work.conductor_auth.invalidate_claude_auth", return_value={"ok": False}) as invalidate, \
             patch.object(R.bundle, "_ssh", return_value=(process_rc, output)) as ssh:
            rc, out = R.run_worker(_facts(), "t1")
            check("실제 OAuth 실패는 정상 캐시를 무효화", rc == 1 and invalidate.call_count == 1)
            check("stderr 회수와 마지막300자 인증 표식 보존",
                  ssh.call_args.args[2].endswith(" 2>&1") and "AX_CLAUDE_AUTH_FAILED" in out[-300:])
    with patch("master.work.conductor_auth.check_claude_auth", return_value={"ok": True}), \
         patch("master.work.conductor_auth.invalidate_claude_auth") as invalidate, \
         patch.object(R.bundle, "_ssh", return_value=(0, "authenticate 기능 구현\nRESULT: DONE")):
        rc, out = R.run_worker(_facts(), "t1")
        check("일반 인증 코드 설명은 오탐 없음", rc == 0 and not invalidate.called)
    with patch("master.work.conductor_auth.check_claude_auth") as check_auth:
        R.run_worker(_facts(), "t1", runner=lambda *a: (0, "RESULT: DONE"))
        check("주입 runner는 실 워커 인증 경로 호출 없음", not check_auth.called)
    check("실측 OAuth 오류는 agent notes에 추출", any(raw in note for note in R.agent_report(raw, rc=1)))


def main() -> int:
    for fn in (test_parse, test_pick, test_command, test_codex_windows_sandbox,
               test_codex_linux_agy_writable_root,
               test_agent_report, test_codex_error_report, test_beater, test_run_task,
               test_queue_calls, test_run_once_happy, test_run_once_returns_the_task,
               test_run_once_guards, test_result_asymmetry, test_pick_skips_dirty,
               test_json_usage,
               test_codex_mcp_approval,
               test_dispatch_is_not_a_consent_prompt,
               test_instruction_forbids_python_runs,
               test_session1_instruction_matches, test_self_repo_note,
               test_session1_master_logs,
               test_session1_launcher_logs,
               test_session1_attempt_isolation,
               test_session1_cancellation,
               test_worker_does_not_build, test_claude_auth_runtime,
               test_delegation_calls, test_instruction_asks_delegation,
               test_delegation_failure_blocks,
               test_session1_agy_relay, test_session1_agy_model_refusal,
               test_session1_agy_model_verdict,
               test_session1_relay_start_failure,
               test_relay_events_are_authoritative,
               test_session1_after_appends_relay_events):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_runner: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
