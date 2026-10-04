"""상용 CLI 사용량 — 감싼 구간 밖이던 경로들 (`#733`). pytest 없이 그대로 실행한다.

    .venv/bin/python -B master/test_usage_cli_paths.py

[중요] 지키는 불변식:
   1. claude·codex 공용 진입도 agy 와 같은 계약 — **감싼 구간만** 한 줄, 못 읽은 토큰은 `measured=False`
   2. 호출자가 받는 본문은 **종전 평문 그대로**다(claude 봉투를 벗긴다)
   3. 층2(`generate.dispatch`) → `layer2` · 게시판 → `board` · 리뷰 기본 체인 → `review` 로 남는다
   4. 🔴 **두 번 세지 않는다** — 레인(`usage.call` → `lanes.run_one`)은 파견이 직접 기록하므로
      공용 진입의 기록을 끈다. 감싼 구간 안에서 불러도 sink 줄은 0 이다
   5. 대시보드가 새 줄(claude·codex·agy)을 제 계열로 분류한다

[주의] **실제 상용 CLI 를 부르지 않는다** — `claude`·`codex`·`agy` 셋 다 가짜를 PATH 앞에 둔다.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master import layer2_verify as L2                                # noqa: E402
from master.context_search.paths import ProjectPaths                  # noqa: E402
from master.context_synth import review_gen as RG                     # noqa: E402
from master.webui import board as B                                   # noqa: E402
from master.work import lanes as LN                                   # noqa: E402
from master.work import usage                                         # noqa: E402
from master.work import usage_dashboard as UD                         # noqa: E402

generate = importlib.import_module("master.work.generate")

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def lines(p: Path) -> list:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []


_CLAUDE = r'''
import json, os, sys
open(os.environ["FAKE_ARGV"], "a").write(json.dumps(sys.argv[1:]) + "\n")
mode = os.environ.get("CLAUDE_FAKE", "json")
res = os.environ.get("FAKE_RESULT", "OK")
env = {"type": "result", "subtype": "success", "is_error": False, "result": res,
       "usage": {"input_tokens": 120, "output_tokens": 30, "cache_read_input_tokens": 900,
                 "cache_creation_input_tokens": 50},
       "total_cost_usd": 0.0123,
       "modelUsage": {"claude-haiku-4": {"outputTokens": 1}, "claude-opus-4-1": {"outputTokens": 30}}}
if mode == "json":
    print(json.dumps(env))
elif mode == "plain":
    print("평문 답")
elif mode == "limit":
    env.update(is_error=True, subtype="error", result="You've hit your session limit")
    print(json.dumps(env)); sys.exit(1)
'''

_CODEX = r'''
import json, os, sys
a = sys.argv[1:]
open(os.environ["FAKE_ARGV"], "a").write(json.dumps(["codex"] + a) + "\n")
mode = os.environ.get("CODEX_FAKE", "ok")
out = a[a.index("-o") + 1]
ev = [{"type": "thread.started"},
      {"type": "item.completed", "item": {"type": "agent_message", "text": "x"}},
      {"type": "turn.completed", "usage": {"input_tokens": 2000, "cached_input_tokens": 1500,
                                           "output_tokens": 77, "reasoning_output_tokens": 10}}]
if mode == "noevents":
    ev = []
for e in ev:
    print(json.dumps(e))
if mode == "fail":
    sys.exit(2)
open(out, "w").write(os.environ.get("FAKE_RESULT", "OK"))
'''

_AGY = r'''
import json, os, sys
open(os.environ["FAKE_ARGV"], "a").write(json.dumps(["agy"] + sys.argv[1:]) + "\n")
if os.environ.get("AGY_FAKE") == "fail":
    print("quota", file=sys.stderr); sys.exit(3)
print(json.dumps({"status": "SUCCESS", "response": os.environ.get("FAKE_RESULT", "OK"),
                  "usage": {"input_tokens": 10, "output_tokens": 2}}))
'''


def _fakes(tmp: Path) -> Path:
    d = tmp / "bin"
    d.mkdir(exist_ok=True)
    for name, body in (("claude", _CLAUDE), ("codex", _CODEX), ("agy", _AGY)):
        exe = d / name
        exe.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        exe.chmod(0o755)
    return d


def _env(**kw):
    for k in ("CLAUDE_FAKE", "CODEX_FAKE", "AGY_FAKE", "FAKE_RESULT"):
        os.environ.pop(k, None)
    os.environ.update(kw)
    L2.clear_cooldown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-usage-cli-"))
    log = tmp / "usage_log.jsonl"
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{_fakes(tmp)}{os.pathsep}{old_path}"
    os.environ["FAKE_ARGV"] = str(tmp / "argv.jsonl")
    err = io.StringIO()
    try:
        check("가짜가 먼저 잡힌다 (실제 CLI 를 부르지 않는다)",
              all(str(shutil.which(n) or "").startswith(str(tmp)) for n in ("claude", "codex", "agy")))

        print("① claude 공용 진입 (`call_claude_why`)")
        _env(CLAUDE_FAKE="json", FAKE_RESULT="OK")
        out, why = L2.call_claude_why("p", timeout=20)
        check("감싸지 않으면 안 남는다", not log.exists())
        check("[중요] 호출자는 봉투가 아니라 본문 평문을 받는다", (out, why) == ("OK", ""), repr((out, why)))
        argv = json.loads((tmp / "argv.jsonl").read_text().splitlines()[-1])
        check("`--output-format json` 으로 부른다 · 프롬프트는 맨 끝",
              argv[:3] == ["-p", "--output-format", "json"] and argv[-1] == "p", str(argv))
        with usage.sink(log, source="board", task_id="dom"):
            out, why = L2.call_claude_why("p", timeout=20, model="opus")
        r = lines(log)[-1] if lines(log) else {}
        check("감싸면 한 줄 · 레인·출처·task_id", len(lines(log)) == 1 and
              (r.get("lane"), r.get("source"), r.get("task_id"), r.get("rc")) == ("claude", "board", "dom", 0),
              str(r))
        check("토큰 항목 (입력·출력·캐시읽기·캐시쓰기)", r.get("measured") is True and
              (r.get("input_tokens"), r.get("output_tokens"), r.get("cache_read"), r.get("cache_create"))
              == (120, 30, 900, 50), str(r))
        check("claude 는 비용을 준다 → cost_known", r.get("cost_known") is True and r.get("cost_usd") == 0.0123,
              str(r))
        check("모델은 봉투의 `modelUsage` 에서 (출력 최대)", r.get("model") == "claude-opus-4-1", str(r))

        _env(CLAUDE_FAKE="plain")
        with usage.sink(log, source="board"):
            out, why = L2.call_claude_why("p", timeout=20)
        r = lines(log)[-1]
        check("봉투가 아니면 출력 전체를 종전처럼 본문으로", (out, why) == ("평문 답\n", ""), repr(out))
        check("[중요] 봉투가 아니면 measured=False (0 이 아니다)",
              r.get("measured") is False and r.get("lane") == "claude", str(r))

        _env(CLAUDE_FAKE="limit")
        with redirect_stderr(err), usage.sink(log, source="board"):
            out, why = L2.call_claude_why("p", timeout=20)
        r = lines(log)[-1]
        check("rc≠0 → 사유는 평문(봉투 JSON 이 아니다)",
              out is None and why.startswith("rc=1:") and "session limit" in why and "{" not in why,
              repr(why))
        check("rc≠0 도 한 줄 · 실패한 호출의 토큰도 실린다", r.get("rc") == 1 and r.get("measured") is True,
              str(r))

        print("② codex 공용 진입 (`call_codex_why`)")
        _env(CODEX_FAKE="ok", FAKE_RESULT="CODEX OK")
        n = len(lines(log))
        text, events, why = L2.call_codex_why("p", timeout=20)
        check("감싸지 않으면 안 남는다", len(lines(log)) == n)
        check("반환 계약 그대로 (본문·이벤트·사유)",
              text == "CODEX OK" and "turn.completed" in events and why == "", repr((text, why)))
        with usage.sink(log, source="layer2", work_id="w1", task_id="t1"):
            L2.call_codex_text_why("p", timeout=20)
        r = lines(log)[-1]
        check("감싸면 한 줄 · 레인 codex · ids", len(lines(log)) == n + 1 and
              (r.get("lane"), r.get("source"), r.get("work_id"), r.get("task_id")) == ("codex", "layer2", "w1", "t1"),
              str(r))
        check("토큰은 `turn.completed` 에서", r.get("measured") is True and
              (r.get("input_tokens"), r.get("output_tokens"), r.get("cache_read")) == (2000, 77, 1500), str(r))
        check("[중요] codex 비용은 모름 (0 이 아니다)", r.get("cost_known") is False, str(r))

        _env(CODEX_FAKE="fail")
        with redirect_stderr(err), usage.sink(log, source="layer2"):
            text, events, why = L2.call_codex_why("p", timeout=20)
        r = lines(log)[-1]
        check("rc≠0 → 반환 계약 종전 그대로 (이벤트 `\"\"`)", text is None and events == "", repr(events))
        check("rc≠0 도 한 줄 · 실패한 실행의 이벤트에서 토큰", r.get("rc") == 2 and r.get("input_tokens") == 2000,
              str(r))
        _env(CODEX_FAKE="noevents")
        with usage.sink(log, source="layer2"):
            L2.call_codex_why("p", timeout=20)
        check("이벤트가 없으면 measured=False", lines(log)[-1].get("measured") is False, str(lines(log)[-1]))

        print("③ 🔴 두 번 세지 않는다 — 레인 계측 경로")
        _env(CODEX_FAKE="ok", FAKE_RESULT="CODEX OK", CLAUDE_FAKE="json")
        n = len(lines(log))
        with usage.sink(log, source="review", task_id="outer"):
            calls = {lane: usage.call(lane, "p", timeout=20) for lane in ("codex", "claude", "agy")}
        check("[중요] `usage.call` 은 감싼 구간 안에서도 sink 줄 0 (레인 셋 다)", len(lines(log)) == n,
              str(lines(log)[n:]))
        check("레인 Call 은 토큰을 그대로 들고 온다 (기록은 파견 몫)",
              calls["codex"].usage.input_tokens == 2000 and calls["claude"].usage.input_tokens == 120
              and calls["agy"].usage.input_tokens == 10,
              str({k: v.usage for k, v in calls.items()}))
        # infer.py 와 같은 자리: 레인 결과를 파견이 record 한다 → 정확히 한 줄
        _env(CODEX_FAKE="ok", FAKE_RESULT="=== FILE: A.h ===\nint x;\n")
        dispatch_log = tmp / "dispatch_usage.jsonl"
        with usage.sink(log, source="review", task_id="outer"):
            run = LN.run_one({"A.h": "// [PSEUDO] x\n"}, "codex", timeout=20)
            usage.record(dispatch_log, usage.meta_from_usage(run.usage), lane="codex", task_id="t9",
                         mode="lane")
        check("`lanes.run_one`(codex) 성공", run.ok, run.reason)
        check("[중요] 레인 한 번 = 파견 기록 한 줄 · sink 줄 0",
              len(lines(dispatch_log)) == 1 and len(lines(log)) == n and
              lines(dispatch_log)[0].get("input_tokens") == 2000, str(lines(dispatch_log)))
        with usage.sink(log, source="review", task_id="outer"):
            usage.call("codex", "p", timeout=20)
            restored = usage._SINK.get()
        check("레인이 끝나면 바깥 sink 가 되살아난다", bool(restored) and restored["task_id"] == "outer")

        print("④ 층2 — `generate.dispatch` → source=layer2")
        _env(AGY_FAKE="ok", FAKE_RESULT="- none\nVERDICT: APPROVE")
        gp = ProjectPaths(name="G", root=tmp / "G")
        (tmp / "G").mkdir()
        broker_calls = []

        def caller(url, payload):
            broker_calls.append(url)
            return "void A::F() {}\n"
        d = generate.dispatch(gp, "task-7", instruction="x", context="CTX", target_file="A.cpp",
                              caller=caller)
        rows = lines(gp.usage_log)
        check("층2 가 실제로 돌았다 (판정이 있다)", d.verdict is not None, d.summary())
        check("[중요] 트윈 usage_log 에 layer2 한 줄 · task_id", len(rows) == 1 and
              (rows[0].get("source"), rows[0].get("lane"), rows[0].get("task_id")) == ("layer2", "agy", "task-7"),
              str(rows))
        check("생성(브로커)은 layer2 로 묶이지 않는다", all(r.get("lane") == "agy" for r in rows) and broker_calls)
        _env(AGY_FAKE="fail", CLAUDE_FAKE="json", FAKE_RESULT="VERDICT: APPROVE")
        with redirect_stderr(err):
            generate.dispatch(gp, "task-8", instruction="x", context="CTX", caller=caller)
        rows = [r for r in lines(gp.usage_log) if r.get("task_id") == "task-8"]
        check("폴백하면 시도한 백엔드마다 한 줄 (agy rc≠0 → claude)",
              [(r["lane"], r["rc"]) for r in rows] == [("agy", 3), ("claude", 0)], str(rows))

        print("⑤ 게시판 — `board.call_llm` → source=board")
        bp = ProjectPaths(name="B", root=tmp / "B")
        (tmp / "B").mkdir()
        _env(CODEX_FAKE="fail", AGY_FAKE="ok", FAKE_RESULT="게시판 답")
        with redirect_stderr(err):
            out = B.call_llm("p", timeout=20, paths=bp, task_id="전투")
        rows = lines(bp.usage_log)
        check("응답은 그대로", out == "게시판 답", repr(out))
        check("[중요] 체인 시도마다 board 한 줄 (codex 실패 → agy)",
              [(r["lane"], r["source"], r["task_id"]) for r in rows]
              == [("codex", "board", "전투"), ("agy", "board", "전투")], str(rows))
        n = len(lines(bp.usage_log))
        with redirect_stderr(err):
            B.call_llm("p", timeout=20)
        check("paths 없이 부르면 기록하지 않는다 (어느 트윈인지 모른다)", len(lines(bp.usage_log)) == n)
        # chat() 이 paths 를 넘기는지 — 실제 진입으로
        dd = bp.context / "_domains"
        dd.mkdir(parents=True)
        (dd / "전투.md").write_text("---\nstatus: draft\n---\n본문\n", encoding="utf-8")
        _env(CODEX_FAKE="ok", FAKE_RESULT="채팅 답")
        B.chat(bp, "전투", "질문")
        last = lines(bp.usage_log)[-1]
        check("`chat()` 이 트윈·도메인으로 남긴다", (last["source"], last["lane"], last["task_id"])
              == ("board", "codex", "전투"), str(last))

        print("⑥ 리뷰 기본 체인 — `review_commit(chat=None)` → source=review")
        rp = ProjectPaths(name="R", root=tmp / "R")
        rp.repo.mkdir(parents=True)

        def git(*a):
            return subprocess.run(["git", "-c", "user.name=사람", "-c", "user.email=t@t",
                                   "-c", "commit.gpgsign=false", "-C", str(rp.repo), *a],
                                  capture_output=True, text=True)
        git("init", "-q", "-b", "main")
        f = rp.repo / "Source" / "M" / "A.cpp"
        f.parent.mkdir(parents=True)
        f.write_text("int F() {\n  return 1;\n}\n", encoding="utf-8")
        git("add", "-A"); git("commit", "-q", "-m", "base")
        f.write_text("int F() {\n  int y = 2;\n  return y * 3;\n}\n", encoding="utf-8")
        git("add", "-A"); git("commit", "-q", "-m", "change")
        commit = git("rev-parse", "HEAD").stdout.strip()
        _env(CODEX_FAKE="ok", FAKE_RESULT="리뷰 본문")
        outer = tmp / "outer.jsonl"
        with usage.sink(outer, source="ontology"):
            RG.review_commit(rp, commit, ["Source/M/A.cpp"])
        rows = lines(rp.usage_log)
        check("[중요] 트윈에 review 줄 · task_id=commit[:12]", bool(rows) and
              all((r["source"], r["task_id"]) == ("review", commit[:12]) for r in rows), str(rows))
        check("형식 재시도까지 호출마다 한 줄 (codex 2회)", [r["lane"] for r in rows] == ["codex", "codex"],
              str(rows))
        check("[중요] 바깥 sink 에는 안 남는다 (한 호출 = 한 줄)", not outer.exists())
        n = len(lines(rp.usage_log))
        RG.review_commit(rp, commit, ["Source/M/A.cpp"], chat=lambda pr: "주입")
        check("chat 을 주입한 경로는 감싸지 않는다 (리뷰 큐가 따로 감싼다)", len(lines(rp.usage_log)) == n)
        with usage.sink(rp.usage_log, source="review", task_id=commit[:12]):
            RG.review_commit(rp, commit, ["Source/M/A.cpp"],
                             chat=lambda pr: L2.call_agy_why(pr, timeout=20)[0])
        rows = lines(rp.usage_log)[n:]
        check("리뷰 큐 모양(바깥 sink + 주입 chat) → 호출마다 한 줄 (agy 2회 · 형식 재시도)",
              [r["lane"] for r in rows] == ["agy", "agy"], str(rows))

        print("⑦ 대시보드 분류")
        fam = {}
        for lane in ("claude", "codex", "agy"):
            raw = {"ts": "2026-10-04 12:00:00", "lane": lane, "model": "", "measured": True, "rc": 0,
                   "input_tokens": 1, "output_tokens": 1, "source": "layer2"}
            fam[lane] = UD._normal_record(raw, session=False)["family"]
        check("claude→claude · codex→codex · agy→gemini",
              fam == {"claude": "claude", "codex": "codex", "agy": "gemini"}, str(fam))
        raw = {"ts": "2026-10-04 12:00:00", "lane": "claude", "model": "claude-opus-4-1", "measured": True,
               "rc": 0, "input_tokens": 1, "output_tokens": 1, "source": "board"}
        check("claude 모델명이 실려도 claude", UD._normal_record(raw, session=False)["family"] == "claude")
    finally:
        os.environ["PATH"] = old_path
        _env()
        os.environ.pop("FAKE_ARGV", None)
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_usage_cli_paths: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
