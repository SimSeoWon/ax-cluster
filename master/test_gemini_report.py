"""`ax-gemini` 실행부 테스트 (사용자 결정 2026-10-09). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_gemini_report.py

[중요] 지키는 불변식:
   1. **성공이든 실패든 `usage_log` 에 한 줄** — `source="ax-gemini"` · `lane="agy"` · 실패는 rc≠0
   2. **`-p` 는 프롬프트 바로 앞** · 프롬프트는 ASCII · `--add-dir` 는 자료 폴더
   3. **보고서는 이 모듈이 쓴다** — 머리말(작성·자료·검증 미검증·소요·토큰) + 본문
   4. **원본은 `.run/` 에 남는다** · 실패면 보고서를 만들지 않는다 · 있는 파일은 덮지 않는다
   5. **토큰을 못 읽으면 0 을 지어내지 않는다** — `measured=False`
   6. 마운트 밖 프로젝트·경로 규약 위반은 실행 전에 거절(agy 를 부르지 않는다)
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search import paths as P                       # noqa: E402
from master.work import gemini_report as G                          # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label} — {detail}")


FAKE = """#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] == ["--version"]:
    print("9.9.9"); sys.exit(0)
open(os.environ["FAKE_AGY_ARGV"], "w").write(json.dumps(sys.argv[1:]))
mode = os.environ.get("FAKE_AGY_MODE", "ok")
if mode == "fail":
    print("429 quota", file=sys.stderr); sys.exit(3)
if mode == "notjson":
    print("plain text"); sys.exit(0)
if mode == "nousage":
    print(json.dumps({"response": "# 보고서\\n본문", "status": "SUCCESS"})); sys.exit(0)
print(json.dumps({"response": "# 보고서\\n본문 `src/a.py:1`", "status": "SUCCESS",
                  "usage": {"input_tokens": 120, "output_tokens": 45, "cache_read_tokens": 7}}))
"""


def rows(log: Path) -> list:
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="test_gemini_report_"))
    real_resolve, real_path = P.resolve_mounted_only, os.environ.get("PATH", "")
    try:
        bindir = tmp / "bin"; bindir.mkdir()
        agy = bindir / "agy"; agy.write_text(FAKE); agy.chmod(agy.stat().st_mode | stat.S_IEXEC)
        os.environ["PATH"] = f"{bindir}{os.pathsep}{real_path}"
        argv_file = tmp / "argv.json"; os.environ["FAKE_AGY_ARGV"] = str(argv_file)
        log = tmp / "twin" / "usage_log.jsonl"
        P.resolve_mounted_only = lambda name="", **k: (
            SimpleNamespace(usage_log=log) if name == "AXCluster"
            else (_ for _ in ()).throw(P.ConfigError(f"마운트되지 않은 프로젝트다: {name}")))
        brief = tmp / "brief"; (brief / "src").mkdir(parents=True)
        (brief / "BRIEF.md").write_text("질문", encoding="utf-8")
        (brief / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        research = tmp / "repo" / "reports" / "research"

        print("\n[1] 성공 — 보고서·머리말·기록·원본")
        os.environ["FAKE_AGY_MODE"] = "ok"
        out = research / "2026-10-09-ok.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out)])
        check("rc 0", rc == 0, str(rc))
        argv = json.loads(argv_file.read_text())
        check("[중요] -p 가 프롬프트 바로 앞", argv[-2] == "-p" and argv[-1] == G.PROMPT, str(argv))
        check("  프롬프트는 ASCII", G.PROMPT.isascii())
        check("  --add-dir 는 자료 폴더", argv[argv.index("--add-dir") + 1] == str(brief.resolve()), str(argv))
        body = out.read_text(encoding="utf-8") if out.is_file() else ""
        check("보고서 본문", "본문 `src/a.py:1`" in body, body[:200])
        check("  머리말 — 작성·버전", "Gemini (agy 9.9.9" in body, body[:200])
        check("  머리말 — 자료 목록", "src/a.py" in body.split("\n")[1], body[:300])
        check("  머리말 — 검증은 미검증으로 시작", "> 검증: 미검증" in body, body[:300])
        check("  머리말 — 토큰", "입력 120 / 출력 45" in body, body[:300])
        r = rows(log)
        check("[중요] usage_log 한 줄", len(r) == 1, str(r))
        if r:
            check("  source=ax-gemini · lane=agy · rc 0",
                  r[0]["source"] == "ax-gemini" and r[0]["lane"] == "agy" and r[0]["rc"] == 0, str(r[0]))
            check("  토큰 측정됨", r[0]["measured"] and r[0]["input_tokens"] == 120
                  and r[0]["output_tokens"] == 45 and r[0]["cache_read"] == 7, str(r[0]))
            check("  비용은 미상(0 아님)", r[0]["cost_known"] is False, str(r[0]))
        run = out.with_suffix(".run")
        check("원본 보관 — out.json·err.log·BRIEF.md·run.json",
              all((run / n).is_file() for n in ("out.json", "err.log", "BRIEF.md", "run.json")),
              str(list(run.iterdir()) if run.is_dir() else run))

        print("\n[2] 덮어쓰지 않는다")
        n0 = len(rows(log))
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out)])
        check("rc 2 · 기록 늘지 않음", rc == 2 and len(rows(log)) == n0, f"{rc} {len(rows(log))}")

        print("\n[3] agy 실패 — 보고서 없음 · 기록은 남는다")
        os.environ["FAKE_AGY_MODE"] = "fail"
        out3 = research / "2026-10-09-fail.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out3)])
        r = rows(log)[-1]
        check("rc 1 · 보고서 없음", rc == 1 and not out3.exists(), str(rc))
        check("[중요] 실패도 기록 — rc≠0", r["rc"] == 3 and r["source"] == "ax-gemini", str(r))
        check("  토큰 미측정(0 을 지어내지 않음)", r["measured"] is False, str(r))
        check("  stderr 보관", "429" in (out3.with_suffix(".run") / "err.log").read_text(), "")

        print("\n[4] 봉투 아님 · usage 없음")
        os.environ["FAKE_AGY_MODE"] = "notjson"
        out4 = research / "2026-10-09-notjson.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out4)])
        r = rows(log)[-1]
        check("봉투 아님 → 실패 · rc≠0 기록", rc == 1 and r["rc"] != 0 and not out4.exists(), str(r))
        os.environ["FAKE_AGY_MODE"] = "nousage"
        out5 = research / "2026-10-09-nousage.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out5)])
        r = rows(log)[-1]
        check("usage 없음 → 보고서는 쓰고 토큰은 미상", rc == 0 and r["measured"] is False
              and "토큰 미상" in out5.read_text(encoding="utf-8"), str(r))

        print("\n[5] 실행 전 거절 — agy 를 부르지 않는다")
        argv_file.unlink(missing_ok=True); n0 = len(rows(log))
        bad = [
            ("마운트 밖", ["--project", "NS", "--brief-dir", str(brief), "--out", str(research / "x.md")]),
            ("reports/research 밖", ["--project", "AXCluster", "--brief-dir", str(brief),
                                     "--out", str(tmp / "repo" / "reports" / "x.md")]),
            ("BRIEF.md 없음", ["--project", "AXCluster", "--brief-dir", str(tmp / "bin"),
                              "--out", str(research / "y.md")]),
        ]
        for label, args in bad:
            check(f"{label} → rc 2", G.main(args) == 2)
        check("  agy 호출 0 · 기록 0", not argv_file.exists() and len(rows(log)) == n0, "")
    finally:
        P.resolve_mounted_only = real_resolve
        os.environ["PATH"] = real_path
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_gemini_report: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
