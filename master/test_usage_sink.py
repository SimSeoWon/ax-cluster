"""브로커 사용량 기록 지점 테스트 (`#713` ①). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_usage_sink.py

[중요] 지키는 불변식:
   1. **감싼 구간만 기록한다** — 감싸지 않은 `call_broker` 는 남지 않는다(워커 파견을 두 번 세지 않는다)
   2. **로컬 모델은 비용 0 이 확정**(`cost_known=True`) — CLI 의 「모름」과 다르다
   3. **노드가 안 준 토큰은 0 으로 지어내지 않는다** — `measured=False`
   4. **스레드 풀로 넘길 때 문맥을 복사하면 따라간다** — 온톨로지 레인이 그렇게 넘긴다
   5. **옛 기록(source 없음)은 집계에서 dispatch 로 묶인다**
"""
from __future__ import annotations

import contextvars
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.work import usage                                      # noqa: E402

# [주의] `master.work` 는 같은 이름의 **함수** `generate` 를 내보낸다 — 모듈을 직접 잡는다
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


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_agy(tmp: Path) -> Path:
    """PATH 앞에 놓을 가짜 `agy`. 출력은 `AGY_FAKE` 로 고른다(2026-10-04 실측 봉투 모양)."""
    d = tmp / "bin"
    d.mkdir(exist_ok=True)
    exe = d / "agy"
    exe.write_text("""#!/bin/sh
case "$AGY_FAKE" in
  json) printf '%s\\n' '{"conversation_id":"x","status":"SUCCESS","response":"OK\\n","duration_seconds":1.0,"num_turns":1,"usage":{"input_tokens":4869,"output_tokens":26,"thinking_tokens":25,"cache_read_tokens":8136,"total_tokens":4895}}' ;;
  model) printf '%s\\n' '{"status":"SUCCESS","response":"OK","model":"gemini-2.5-pro","usage":{"input_tokens":1,"output_tokens":1}}' ;;
  empty) printf '%s\\n' '{"status":"ERROR","response":"","usage":{}}' ;;
  plain) printf '%s\\n' '평문 답' ;;
  garbled) printf '{"respo' ;;
  fail) echo '쿼터 초과' 1>&2; exit 3 ;;
esac
""", encoding="utf-8")
    exe.chmod(0o755)
    return d


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-usage-sink-"))
    log = tmp / "usage_log.jsonl"
    real = generate.urllib.request.urlopen
    try:
        print("① 감싼 구간만")
        check("감싸지 않으면 아무것도 안 한다", usage.emit_broker("m", {"in": 1, "out": 1}) is None)
        check("  파일도 안 생긴다", not log.exists())
        with usage.sink(log, source="synth", task_id="g/a"):
            rec = usage.emit_broker("gemma4:e4b", {"in": 3500, "out": 300, "ms": 17000}, seconds=17.2)
        got = lines(log)
        check("감싸면 한 줄", len(got) == 1, str(got))
        r = got[0] if got else {}
        check("출처·모델·레인", (r.get("source"), r.get("model"), r.get("lane"))
              == ("synth", "gemma4:e4b", "local:gemma4:e4b"), str(r))
        check("토큰", (r.get("input_tokens"), r.get("output_tokens")) == (3500, 300))
        check("[중요] 로컬은 비용 0 확정", r.get("cost_known") is True and r.get("cost_usd") == 0.0, str(r))
        check("task_id 가 실린다", r.get("task_id") == "g/a")
        check("반환값이 기록과 같다", rec is not None and rec.get("source") == "synth")

        print("①-b #751 구간의 상용 CLI 토큰을 돌려준다")
        check("감싸지 않으면 빈 dict", usage.sink_cli_tokens() == {})
        with usage.sink(log, source="synth", task_id="g/b"):
            check("  호출 전엔 빈 dict", usage.sink_cli_tokens() == {})
            usage.emit_cli("agy", usage.Usage(lane="agy", input_tokens=50, output_tokens=9))
            usage.emit_cli("codex", usage.Usage(lane="codex", note="못 읽음"))   # 미측정 — 더하지 않는다
            got_t = usage.sink_cli_tokens()
        check("  측정된 호출만 합친다", got_t == {"in": 50, "out": 9}, str(got_t))
        with usage.sink(log, source="synth"):
            usage.emit_cli("agy", usage.Usage(lane="agy", note="봉투 아님"))
            check("  측정이 하나도 없으면 빈 dict(0 을 지어내지 않는다)", usage.sink_cli_tokens() == {})

        print("② 노드가 안 준 값은 지어내지 않는다")
        with usage.sink(log, source="review"):
            usage.emit_broker("m", {})
        r2 = lines(log)[-1]
        check("measured=False", r2.get("measured") is False and r2.get("input_tokens") == 0, str(r2))

        print("③ 스레드 풀 — 문맥을 복사하면 따라간다")
        n0 = len(lines(log))
        with usage.sink(log, source="ontology", task_id="dom"):
            with ThreadPoolExecutor(max_workers=2) as ex:
                ex.submit(contextvars.copy_context().run, usage.emit_broker, "m", {"in": 1}).result()
                plain = ex.submit(usage.emit_broker, "m", {"in": 1}).result()
        after = lines(log)
        check("복사한 문맥은 기록된다", len(after) == n0 + 1 and after[-1]["source"] == "ontology",
              str(after[-1:]))
        check("[주의] 복사하지 않으면 안 따라간다 (그래서 온톨로지가 복사한다)", plain is None)

        print("④ call_broker 가 기록 지점을 부른다")
        generate.urllib.request.urlopen = lambda req, timeout=0: _Resp(json.dumps(
            {"response": "ok", "prompt_eval_count": 11, "eval_count": 5,
             "total_duration": 2_000_000_000}).encode())
        n1 = len(lines(log))
        generate.call_broker("p", model="gemma4:e4b", token="t")
        check("감싸지 않은 호출은 안 남는다", len(lines(log)) == n1)
        with usage.sink(log, source="synth", task_id="g/b"):
            out = generate.call_broker("p", model="gemma4:e4b", token="t")
        last = lines(log)[-1]
        check("응답은 그대로", out == "ok")
        check("감싼 호출은 남는다", len(lines(log)) == n1 + 1 and last["task_id"] == "g/b"
              and last["input_tokens"] == 11 and last["output_tokens"] == 5, str(last))

        print("⑥ agy 공용 진입(`layer2_verify.call_agy_why`)도 감싼 구간이면 남는다 (#728)")
        from master import layer2_verify as l2
        fake = _fake_agy(tmp)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake}{os.pathsep}{old_path}"
        try:
            os.environ["AGY_FAKE"] = "json"
            n2 = len(lines(log))
            out, why = l2.call_agy_why("p", timeout=10)
            check("감싸지 않으면 안 남는다", len(lines(log)) == n2)
            check("[중요] 호출자는 봉투가 아니라 본문 평문을 받는다", (out, why) == ("OK\n", ""),
                  repr((out, why)))
            with usage.sink(log, source="review", task_id="abc123"):
                out, why = l2.call_agy_why("p", timeout=10)
            r6 = lines(log)[-1]
            check("JSON → 본문 그대로", out == "OK\n" and why == "", repr(out))
            check("JSON → 한 줄 · 레인 agy · 출처·task_id", len(lines(log)) == n2 + 1 and
                  (r6.get("lane"), r6.get("source"), r6.get("task_id"), r6.get("rc"))
                  == ("agy", "review", "abc123", 0), str(r6))
            check("JSON → 토큰이 실린다", r6.get("measured") is True and
                  (r6.get("input_tokens"), r6.get("output_tokens"), r6.get("cache_read"),
                   r6.get("reasoning_tokens")) == (4869, 26, 8136, 25), str(r6))
            check("[중요] 비용은 모름(0 이 아니다)", r6.get("cost_known") is False, str(r6))
            check("모델 키가 없으면 model 은 비운다", r6.get("model") == "", str(r6))

            for mode, want in (("plain", "평문 답\n"), ("garbled", '{"respo')):
                os.environ["AGY_FAKE"] = mode
                with usage.sink(log, source="review", task_id="abc123"):
                    out, why = l2.call_agy_why("p", timeout=10)
                r7 = lines(log)[-1]
                check(f"{mode} → 출력을 종전처럼 본문으로", out == want and why == "", repr(out))
                check(f"[중요] {mode} → measured=False (0 이 아니다)",
                      r7.get("measured") is False and r7.get("lane") == "agy" and r7.get("rc") == 0,
                      str(r7))

            os.environ["AGY_FAKE"] = "model"
            with usage.sink(log, source="review"):
                l2.call_agy_why("p", timeout=10)
            check("모델 키가 생기면 실린다", lines(log)[-1].get("model") == "gemini-2.5-pro",
                  str(lines(log)[-1]))

            os.environ["AGY_FAKE"] = "empty"
            with usage.sink(log, source="review"):
                out, why = l2.call_agy_why("p", timeout=10)
            check("빈 응답 → 종전과 같은 사유", out is None and why.startswith("빈 출력 (rc=0)"),
                  repr((out, why)))

            os.environ["AGY_FAKE"] = "fail"
            buf, olderr = io.StringIO(), sys.stderr
            sys.stderr = buf
            try:
                with usage.sink(log, source="review"):
                    out, why = l2.call_agy_why("p", timeout=10)
            finally:
                sys.stderr = olderr
            r8 = lines(log)[-1]
            check("rc≠0 → 사유는 종전 형식", out is None and why.startswith("rc=3:") and "쿼터" in why,
                  repr(why))
            check("[중요] rc≠0 도 한 줄 (rc 실림 · measured=False)",
                  r8.get("rc") == 3 and r8.get("measured") is False, str(r8))
        finally:
            os.environ["PATH"] = old_path
            os.environ.pop("AGY_FAKE", None)

        print("⑤ 집계 — 출처 축")
        log.open("a", encoding="utf-8").write(json.dumps(
            {"ts": "2099-01-01 00:00:00", "lane": "codex", "input_tokens": 7, "output_tokens": 1,
             "cost_known": False, "measured": True}) + "\n")
        s = usage.summarize([log], days=100000)
        by = s.get("by_source", {})
        check("출처별로 묶인다", {"synth", "review", "ontology"} <= set(by), str(set(by)))
        check("[중요] 옛 기록(source 없음)은 dispatch", "dispatch" in by, str(set(by)))
    finally:
        generate.urllib.request.urlopen = real
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_usage_sink: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
