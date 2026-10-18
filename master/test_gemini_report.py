"""`ax-gemini` 실행부 테스트 (사용자 결정 2026-10-09). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_gemini_report.py

[중요] 지키는 불변식:
   1. **성공이든 실패든 `usage_log` 에 한 줄** — `source="ax-gemini"` · `lane="agy"` · 실패는 rc≠0
   2. **`-p` 는 프롬프트 바로 앞** · 프롬프트는 ASCII · `--add-dir` 는 자료 폴더
   3. **보고서는 이 모듈이 쓴다** — 머리말(작성·자료·검증 미검증·소요·토큰) + 본문
   4. **원본은 `.run/` 에 남는다** · 실패면 보고서를 만들지 않는다 · 있는 파일은 덮지 않는다
   5. **토큰을 못 읽으면 0 을 지어내지 않는다** — `measured=False`
   6. 마운트 밖 프로젝트·경로 규약 위반은 실행 전에 거절(agy 를 부르지 않는다)
   9. **agy 가 스스로 재시도해 회복했으면 성공(종료 0)** — `--log-file` 로그로만 판정 · 재시도 뒤 생성
      요청이 없거나 로그가 없으면 경고 3 · 모델은 로그 label 에서 (사용자 결정 2026-10-09 A)
   8. **봉투 status 가 SUCCESS 가 아니면 경고(종료 3)** — 보고서는 쓰되 `ok:false` · 머리말·기록에
      오류 문구 (사용자 결정 2026-10-09 (나))
  10. **모델은 정본 id(`gemini-` 로 시작) 로 명시 · 실제 모델을 로그로 대조** (`#830`) — `--model <id>` 를 싣는다(마스터는
      `agy_models.DEFAULT_MODEL`, `--remote` 는 `.ax/config.json` `backends.agy_model`) · 없음·별칭·Argon 은
      실행 전 거절(종료 2, agy 호출 0) · Argon 은 `--model`+`--allow-argon` 때만 · 실제 모델이 다르거나
      모르면 출력을 버린다(종료 1 · 보고서 없음 · 원본 `.run/` 보존 · 기록에 요청/실제)
   7. **세션이 본문을 안 읽어도 되게** — 인용 범위를 결정적으로 검사해 `citations.txt` 에 원문 줄을
      모으고, 결과 JSON 에 `summary`(요약 절)·`citations` 통계를 싣는다(`#762` 후속)
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
from unittest.mock import patch

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
LABEL = ('I1009 model_config_manager.go:327] Propagating selected model override to backend: label="'
         + os.environ.get("FAKE_AGY_LABEL", "Gemini 3.8 Flash (Medium)") + '"')
GEN = "I1009 http_helpers.go:315] URL: https://x/v1internal:streamGenerateContent?alt=sse"
RETRY = "I1009 run.go:395] Run: attempt 1 failed (UNAVAILABLE (code 503): No capacity), retrying in 4s"
logs = {"ok": [LABEL, GEN], "retryok": [LABEL, GEN, RETRY, GEN, GEN],
        "retrytail": [LABEL, GEN, RETRY], "statuserror": [LABEL, GEN], "nousage": [LABEL, GEN]}
if "--log-file" in sys.argv and mode in logs and not os.environ.get("FAKE_AGY_NOLOG"):
    open(sys.argv[sys.argv.index("--log-file") + 1], "w").write("\\n".join(logs[mode]) + "\\n")
if mode in ("retryok", "retrytail"):
    print(json.dumps({"response": "# 보고서\\n## 요약\\n요약", "status": "ERROR",
                      "error": "API error (attempt 1): UNAVAILABLE (code 503): No capacity",
                      "usage": {"input_tokens": 5, "output_tokens": 2}})); sys.exit(0)
if mode == "fail":
    print("429 quota", file=sys.stderr); sys.exit(3)
if mode == "notjson":
    print("plain text"); sys.exit(0)
if mode == "statuserror":
    print(json.dumps({"response": "# 보고서\\n## 요약\\n요약", "status": "ERROR",
                      "error": "API error (attempt 1): UNAVAILABLE (code 503): No capacity",
                      "usage": {"input_tokens": 5, "output_tokens": 2}})); sys.exit(0)
if mode == "nousage":
    print(json.dumps({"response": "# 보고서\\n본문", "status": "SUCCESS"})); sys.exit(0)
print(json.dumps({"response": "# 보고서\\n\\n## 요약\\n요약 한 줄\\n\\n## 1\\n본문 `src/a.py:1` 재인용 `src/a.py:1` 범위밖 `src/a.py:9` 없음 (`src/b.py:2`)", "status": "SUCCESS",
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
        check("[중요] 마스터 정본 모델을 --model 로 싣는다 (#830)", G.master_model() == "gemini-3.8-flash-medium"
              and "--model" in argv and argv[argv.index("--model") + 1] == "gemini-3.8-flash-medium", str(argv))
        check("  프롬프트는 ASCII", G.PROMPT.isascii())
        check("  --add-dir 는 자료 폴더", argv[argv.index("--add-dir") + 1] == str(brief.resolve()), str(argv))
        check("  --log-file 은 .run/agy.log", "--log-file" in argv
              and argv[argv.index("--log-file") + 1] == str(out.with_suffix(".run") / "agy.log"), str(argv))
        body = out.read_text(encoding="utf-8") if out.is_file() else ""
        check("보고서 본문", "본문 `src/a.py:1`" in body, body[:200])
        check("  머리말 — 범위 검사(자동)", "인용 3개 — 범위 안 1 · 범위 밖 1 · 파일 없음 1" in body, body[:400])
        check("  머리말 — 작성·버전·모델(로그 label)", "Gemini (agy 9.9.9 · gemini-3.8-flash-medium)" in body, body[:200])
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
            check("  [중요] 기록에 요청·실제 모델 (출처 log)",
                  (r[0].get("requested_model"), r[0].get("actual_model"), r[0].get("model_source"), r[0]["model"])
                  == ("gemini-3.8-flash-medium",) * 2 + ("log", "gemini-3.8-flash-medium"), str(r[0]))
        run = out.with_suffix(".run")
        res = json.loads((run / "run.json").read_text(encoding="utf-8")) if (run / "run.json").is_file() else {}
        check("[중요] 인용 통계 — 중복 1회 · 범위 밖 · 파일 없음",
              res.get("citations") == {"total": 3, "missing_file": 1, "out_of_range": 1,
                                       "unreadable_file": 0, "in_range": 1},
              str(res.get("citations")))
        check("  결과 JSON 에 요약 절만", res.get("summary") == "요약 한 줄", repr(res.get("summary")))
        check("  run.json 에 요청·실제 모델 · model_ok",
              (res.get("requested_model"), res.get("actual_model"), res.get("model_ok"), res.get("requested_from"))
              == ("gemini-3.8-flash-medium", "gemini-3.8-flash-medium", True, "agy_models.DEFAULT_MODEL"), str(res))
        ct = (run / "citations.txt").read_text(encoding="utf-8") if (run / "citations.txt").is_file() else ""
        check("  citations.txt — 원문 줄", "### src/a.py:1\n    1  x = 1" in ct, ct)
        check("  citations.txt — 범위 밖·파일 없음 표시",
              "src/a.py:9  [범위 밖 — 파일은 1줄]" in ct and "src/b.py:2  [파일 없음]" in ct, ct)
        check("원본 보관 — out.json·err.log·BRIEF.md·run.json",
              all((run / n).is_file() for n in ("out.json", "err.log", "BRIEF.md", "run.json")),
              str(list(run.iterdir()) if run.is_dir() else run))

        print("\n[1b] 인용 파일 읽기 실패 — 보고서와 뒤 정상 인용 보존")
        unreadable = brief / "src" / "a.py"
        (brief / "src" / "b.py").write_text("first\nsecond\n", encoding="utf-8")
        read_text = Path.read_text

        def read(path, *args, **kwargs):
            if path == unreadable:
                raise PermissionError("citation fixture")
            return read_text(path, *args, **kwargs)

        failed_out = research / "2026-10-09-unreadable.md"
        with patch.object(Path, "read_text", read):
            rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief),
                         "--out", str(failed_out)])
        failed_run = failed_out.with_suffix(".run")
        failed_res = json.loads((failed_run / "run.json").read_text(encoding="utf-8"))
        failed_cites = (failed_run / "citations.txt").read_text(encoding="utf-8")
        check("읽기 실패가 실행을 중단하지 않음", rc == 0 and failed_out.is_file())
        check("읽기 실패는 검증됨·파일없음으로 세지 않음", failed_res["citations"] == {
            "total": 3, "missing_file": 0, "out_of_range": 0, "unreadable_file": 2, "in_range": 1},
            str(failed_res))
        check("실패 사유와 뒤 정상 인용 보존", "[읽기 실패] PermissionError: citation fixture" in failed_cites
              and "### src/b.py:2\n    2  second" in failed_cites, failed_cites)
        check("머리말에 읽기 실패 표시·미검증 유지", "읽기 실패 2" in failed_out.read_text(encoding="utf-8")
              and "> 검증: 미검증" in failed_out.read_text(encoding="utf-8"))
        (brief / "src" / "b.py").unlink()

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
        check("  실패 사유도 기록 비고에", "rc=3" in r.get("note", ""), str(r))
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

        print("\n[4b] status=ERROR + 본문 — 경고(종료 3)")
        os.environ["FAKE_AGY_MODE"] = "statuserror"
        out6 = research / "2026-10-09-statuserror.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out6)])
        r = rows(log)[-1]
        res = json.loads((out6.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("[중요] 종료 3 · 보고서는 썼다", rc == 3 and out6.is_file(), str(rc))
        check("  ok:false · why 에 status·error", res["ok"] is False and "status=ERROR" in res["why"]
              and "503" in res["why"] and res["error"].startswith("API error"), str(res))
        check("  머리말 경고", "> [주의] agy status=ERROR: API error" in out6.read_text(encoding="utf-8"), "")
        check("  기록 — 토큰 측정 · 비고에 오류", r["measured"] and "status=ERROR" in r.get("note", ""), str(r))

        print("\n[4c] status=ERROR + 로그에 재시도 회복 — 성공(종료 0)")
        os.environ["FAKE_AGY_MODE"] = "retryok"
        out7 = research / "2026-10-09-retryok.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(out7)])
        r = rows(log)[-1]
        res = json.loads((out7.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        b7 = out7.read_text(encoding="utf-8")
        check("[중요] 종료 0 · ok · recovered · 재시도 1", rc == 0 and res["ok"] and res["recovered"]
              and res["retries"] == 1, str(res))
        check("  머리말 참고 줄 · 경고 줄 없음", "> 참고: agy 재시도 1회 후 완료" in b7 and "[주의] agy" not in b7, b7[:500])
        check("  기록 비고에 재시도 · 모델", "재시도 1회" in r.get("note", "")
              and r["model"] == "gemini-3.8-flash-medium", str(r))
        os.environ["FAKE_AGY_MODE"] = "retrytail"
        o = research / "2026-10-09-retrytail-0.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(o)])
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("  재시도 뒤 생성 요청 없음 → 경고 3 (모르면 회복으로 보지 않는다)",
              rc == 3 and not res["recovered"] and res["ok"] is False, str(res))
        # 🔴 `#830` — 로그가 없으면 실제 모델도 모른다. 종전 「경고 3」이 아니라 출력을 버린다(종료 1)
        os.environ.update({"FAKE_AGY_MODE": "retryok", "FAKE_AGY_NOLOG": "1"})
        o = research / "2026-10-09-retryok-1.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(o)])
        os.environ.pop("FAKE_AGY_NOLOG", None)
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("  [중요] 로그 없음 → 실제 모델 미상 → 종료 1 · 보고서 없음 · 원본 보존",
              rc == 1 and not o.exists() and res["model_ok"] is False and "실제 모델 미상" in res["why"]
              and (o.with_suffix(".run") / "out.json").is_file(), str(res))

        print("\n[4d] 모델 불일치 — 출력을 버린다 (#830)")
        os.environ.update({"FAKE_AGY_MODE": "ok", "FAKE_AGY_LABEL": "Gemini 4 Argon"})
        o = research / "2026-10-18-mismatch.md"
        rc = G.main(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(o)])
        os.environ.pop("FAKE_AGY_LABEL", None)
        r = rows(log)[-1]
        mrun = o.with_suffix(".run")
        res = json.loads((mrun / "run.json").read_text(encoding="utf-8"))
        check("[중요] 종료 1 · 보고서 없음", rc == 1 and not o.exists(), str(rc))
        check("  run.json — ok:false · 모델 불일치 · 요청/실제", res["ok"] is False and not res["model_ok"]
              and "모델 불일치" in res["why"] and res["requested_model"] == "gemini-3.8-flash-medium"
              and res["actual_model"] == "gemini-4-argon" and res["report"] == "", str(res))
        check("  원본 보존 — out.json·agy.log·err.log", all((mrun / n).is_file()
              for n in ("out.json", "agy.log", "err.log")), str(list(mrun.iterdir())))
        check("  [중요] 기록 — rc≠0 · 실제(태운) 모델 · 요청 모델 · 비고", r["rc"] == 1
              and r["model"] == "gemini-4-argon" and r.get("actual_model") == "gemini-4-argon"
              and r.get("requested_model") == "gemini-3.8-flash-medium" and "모델 불일치" in r.get("note", ""), str(r))
        check("  인용 파일·보고서 안 만든다", not (mrun / "citations.txt").exists())

        # [PSEUDO] #831: 절 [4d2] 를 더한다 — 가짜 agy 가 봉투 `status=ERROR` · `error="authentication failed or timed out"` ·
        #       응답 빈 값 · 로그 label 없음으로 끝나게 해서(가짜 agy 의 기존 모드 중 맞는 것을 쓰거나 하나 추가) `G.main` 을 돌리고,
        #       종료 1 · run.json `why` 가 「agy 오류: authentication failed or timed out」로 **시작**하고 그 뒤에 「실제 모델 미상」이
        #       붙는지 확인한다. 봉투 오류가 없는 기존 [4c]·[4d] 의 사유 문구는 그대로인지도 하나 확인한다.

        print("\n[4e] Argon 은 --model + --allow-argon 일 때만")
        os.environ.update({"FAKE_AGY_MODE": "ok", "FAKE_AGY_LABEL": "Gemini 4 Argon"})
        o = research / "2026-10-18-argon-explicit.md"
        rc = G.main(["--project", "AXCluster", "--model", "gemini-4-argon", "--allow-argon",
                     "--brief-dir", str(brief), "--out", str(o)])
        os.environ.pop("FAKE_AGY_LABEL", None)
        argv = json.loads(argv_file.read_text())
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("명시 Argon → rc 0 · --model gemini-4-argon · -p 는 끝", rc == 0 and o.is_file()
              and argv[argv.index("--model") + 1] == "gemini-4-argon" and argv[-2] == "-p", str(argv))
        check("  requested_from=--model", res.get("requested_from") == "--model", str(res))
        os.environ.update({"FAKE_AGY_MODE": "ok", "FAKE_AGY_LABEL": "Gemini 4 Argon (Medium)"})
        o = research / "2026-10-18-argon-medium-explicit.md"
        rc = G.main(["--project", "AXCluster", "--model", "gemini-4-argon-medium", "--allow-argon",
                     "--brief-dir", str(brief), "--out", str(o)])
        os.environ.pop("FAKE_AGY_LABEL", None)
        check("명시 Argon 변형(gemini-4-argon-medium) + --allow-argon → rc 0", rc == 0 and o.is_file(), str(rc))

        print("\n[5] 실행 전 거절 — agy 를 부르지 않는다")
        argv_file.unlink(missing_ok=True); n0 = len(rows(log))
        bad = [
            ("마운트 밖", ["--project", "NS", "--brief-dir", str(brief), "--out", str(research / "x.md")]),
            ("reports/research 밖", ["--project", "AXCluster", "--brief-dir", str(brief),
                                     "--out", str(tmp / "repo" / "reports" / "x.md")]),
            ("BRIEF.md 없음", ["--project", "AXCluster", "--brief-dir", str(tmp / "bin"),
                              "--out", str(research / "y.md")]),
            ("[#830] Argon --model 에 --allow-argon 없음", ["--project", "AXCluster", "--model", "gemini-4-argon",
                                                         "--brief-dir", str(brief), "--out", str(research / "z1.md")]),
            ("[#830] --allow-argon 만 (--model 없음)", ["--project", "AXCluster", "--allow-argon",
                                                      "--brief-dir", str(brief), "--out", str(research / "z2.md")]),
            ("[#830] 별칭 모양 --model", ["--project", "AXCluster", "--model", "Gemini Flash",
                                        "--brief-dir", str(brief), "--out", str(research / "z3.md")]),
            ("[#830] 소문자 별칭 flash (gemini- 접두 아님)", ["--project", "AXCluster", "--model", "flash",
                                        "--brief-dir", str(brief), "--out", str(research / "z6.md")]),
            ("[#830] Argon 변형 --model 에 --allow-argon 없음", ["--project", "AXCluster", "--model",
                                        "gemini-4-argon-medium", "--brief-dir", str(brief), "--out", str(research / "z7.md")]),
            ("[#830] 대문자 id", ["--project", "AXCluster", "--model", "Gemini-3.8-flash-medium",
                                "--brief-dir", str(brief), "--out", str(research / "z4.md")]),
        ]
        for label, args in bad:
            check(f"{label} → rc 2", G.main(args) == 2)
        real_mm = G.master_model
        for label, val in (("[#830] 마스터 정본 모델이 비면", ""), ("[#830] 마스터 정본이 Argon 이면", "gemini-4-argon")):
            G.master_model = lambda v=val: v
            check(f"{label} → rc 2", G.main(["--project", "AXCluster", "--brief-dir", str(brief),
                                             "--out", str(research / "z5.md")]) == 2)
        G.master_model = real_mm
        check("  agy 호출 0 · 기록 0", not argv_file.exists() and len(rows(log)) == n0, "")

        print("\n[5b] 🔴 #832 Windows 세션 0 — agy·모델 해석 전에 거절(종료 2) · 리눅스는 영향 없음")
        import contextlib
        import ctypes
        import io

        class K32:
            def __init__(self, sid):
                self.sid, self.calls = sid, []

            def GetCurrentProcessId(self):
                return 7

            def ProcessIdToSessionId(self, pid, ref):
                self.calls.append(pid); ref._obj.value = self.sid; return 1

        @contextlib.contextmanager
        def platform(plat, sid):
            k, real_plat = K32(sid), sys.platform
            had, old = hasattr(ctypes, "windll"), getattr(ctypes, "windll", None)
            ctypes.windll = type("W", (), {"kernel32": k})()
            sys.platform = plat
            try:
                yield k
            finally:
                sys.platform = real_plat
                if had:
                    ctypes.windll = old
                else:
                    delattr(ctypes, "windll")

        def run(args, **kw):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = G.main(args, **kw)
            return rc, err.getvalue()

        ws = G._winsession()
        check("판정 모듈을 저장소 경로(client/runtime)에서 찾는다", ws is not None and hasattr(ws, "REFUSAL"))
        argv_file.unlink(missing_ok=True); n0 = len(rows(log))
        qcalls = []
        with platform("win32", 0) as k:
            rc, err = run(["--project", "AXCluster", "--brief-dir", str(brief),
                           "--out", str(research / "2026-10-18-s0.md")])
            check("[중요] 세션 0 (마스터 경로) → rc 2", rc == 2, str(rc))
            check("[중요] 고정 사유 + SessionId 가 로그에 찍힌다",
                  ws.REFUSAL in err and "SessionId=0" in err and "거절" in err, err)
            rc, err = run(["--remote", "--checkout", str(tmp / "nowhere"), "--brief-dir", str(brief),
                           "--out", str(research / "2026-10-18-s0r.md")],
                          queue=lambda *a, **kw: qcalls.append(a) or {"ok": True})
            check("[중요] 세션 0 (--remote) → rc 2 · 요청자 설정보다 먼저", rc == 2 and ws.REFUSAL in err, err)
            check("  세션을 실제로 쟀다", len(k.calls) >= 1, str(k.calls))
        check("[중요] agy 호출 0 · 사용량 기록 0 · 큐 호출 0 (다른 종료 2 거절과 같은 계약)",
              not argv_file.exists() and len(rows(log)) == n0 and not qcalls, str(qcalls))
        check("  보고서·.run 없음", not (research / "2026-10-18-s0.md").exists()
              and not (research / "2026-10-18-s0.run").exists())

        with platform("win32", 18):
            check("Windows 대화형(SessionId 18) → 거절 없음", G.session0_refusal() == "")

        real_ws = G._winsession
        G._winsession = lambda: None
        try:
            with platform("win32", 18):
                r = G.session0_refusal()
                check("[주의] Windows 에서 판정 모듈을 못 찾으면 거절(fail-closed)", "재배달" in r, r)
            check("[중요] 리눅스에선 판정 모듈이 없어도 거절 없음", G.session0_refusal() == "")
        finally:
            G._winsession = real_ws

        os.environ["FAKE_AGY_MODE"] = "ok"
        argv_file.unlink(missing_ok=True); n0 = len(rows(log))
        for plat in ("linux", "darwin"):
            with platform(plat, 0) as k:       # 세션 0 을 말하는 가짜 kernel32 가 꽂혀 있어도
                check(f"[중요] {plat}: 가드는 무동작", G.session0_refusal() == "")
                o = research / f"2026-10-18-linux-{plat}.md"
                rc, err = run(["--project", "AXCluster", "--brief-dir", str(brief), "--out", str(o)])
                check(f"[중요] {plat}: 마스터 경로 그대로 — rc 0 · 보고서 · 기록 한 줄",
                      rc == 0 and o.is_file() and len(rows(log)) == n0 + 1, f"rc={rc} {err[-300:]}")
                check(f"  {plat}: kernel32 를 부르지 않았다 · 세션 사유 없음",
                      k.calls == [] and "#832" not in err, str(k.calls))
                n0 = len(rows(log))
        check("  agy 는 불렸다(가드가 막지 않았다)", argv_file.exists())

        print("\n[6] 요청자 --remote (#763) — 기록 한 줄은 큐로 · 성공·실패 모두 · 전송 실패는 실행 실패가 아니다")
        co = tmp / "checkout"; (co / ".ax").mkdir(parents=True)
        (co / ".ax" / "config.json").write_text(json.dumps({
            "project": "AXCluster", "this_host": {"host": "DESKTOP-FU2GNGL", "role": "requester"},
            "backends": {"agy_model": "gemini-3.8-flash-medium"},
            "master": {"host": "127.0.0.1", "services": {"task_queue": 1}}}), encoding="utf-8")
        sent = []

        def fake_queue(method, path, payload=None):
            sent.append((method, path, payload))
            return {"ok": True, "record": {"source": payload["source"], "rc": payload["rc"]}}

        n_local = len(rows(log))
        os.environ["FAKE_AGY_MODE"] = "ok"
        o = research / "2026-10-17-remote-ok.md"

        def no_master_model():
            raise AssertionError("--remote 가 agy_models 경로를 탔다")

        G.master_model = no_master_model       # 🔴 Windows 에서 fcntl 을 임포트하면 죽는다
        rc = G.main(["--remote", "--checkout", str(co), "--brief-dir", str(brief), "--out", str(o)],
                    queue=fake_queue)
        check("rc 0 · 보고서", rc == 0 and o.is_file(), str(rc))
        argv = json.loads(argv_file.read_text())
        check("[중요] --remote 는 backends.agy_model 을 --model 로 (agy_models 안 탐)",
              argv[argv.index("--model") + 1] == "gemini-3.8-flash-medium", str(argv))
        check("[중요] POST /api/v1/usage 한 번", [(m, p_) for m, p_, _ in sent] == [("POST", "/api/v1/usage")],
              str(sent))
        if sent:
            b = sent[0][2]
            check("  source·lane·rc·worker(this_host.host)",
                  (b["source"], b["lane"], b["rc"], b["worker"]) == ("ax-gemini", "agy", 0, "DESKTOP-FU2GNGL"), str(b))
            check("  토큰은 usage 안쪽 키 그대로 · 비용은 안 보낸다(미상)",
                  b.get("usage") == {"input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 7}
                  and "total_cost_usd" not in b, str(b))
            check("  모델은 로그 label", b.get("model") == "gemini-3.8-flash-medium", str(b))
            check("  비고에 요청 모델 (큐 모델엔 칸이 없다)", "요청 모델 gemini-3.8-flash-medium" in b.get("note", ""), str(b))
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("  결과 JSON 의 usage_log 는 마스터 트윈 경유 · usage_error 없음",
              "POST /api/v1/usage" in res["usage_log"] and "usage_error" not in res, str(res))
        check("  머리말 프로젝트는 체크아웃 설정값", "프로젝트 AXCluster" in o.read_text(encoding="utf-8"), "")
        check("[중요] 마스터 로컬 usage_log 는 건드리지 않는다", len(rows(log)) == n_local, str(len(rows(log))))

        sent.clear()
        os.environ["FAKE_AGY_MODE"] = "fail"
        o = research / "2026-10-17-remote-fail.md"
        rc = G.main(["--remote", "--checkout", str(co), "--brief-dir", str(brief), "--out", str(o)],
                    queue=fake_queue)
        check("[중요] agy 실패도 한 줄 — rc≠0 · 비고에 사유", rc == 1 and len(sent) == 1
              and sent[0][2]["rc"] == 3 and "rc=3" in sent[0][2]["note"], str(sent))

        sent.clear()
        os.environ.update({"FAKE_AGY_MODE": "ok", "FAKE_AGY_LABEL": "Gemini 4 Argon"})
        o = research / "2026-10-18-remote-mismatch.md"
        rc = G.main(["--remote", "--checkout", str(co), "--brief-dir", str(brief), "--out", str(o)],
                    queue=fake_queue)
        os.environ.pop("FAKE_AGY_LABEL", None)
        check("[중요] 요청자 모델 불일치 → rc 1 · 보고서 없음 · 한 줄 rc≠0 · 실제 모델 · 비고",
              rc == 1 and not o.exists() and len(sent) == 1 and sent[0][2]["rc"] == 1
              and sent[0][2]["model"] == "gemini-4-argon" and "모델 불일치" in sent[0][2]["note"]
              and "요청 모델 gemini-3.8-flash-medium · 실제 gemini-4-argon" in sent[0][2]["note"], str(sent))

        for label, backends in (("agy_model 없음", {}), ("Argon 설정", {"agy_model": "gemini-4-argon"}),
                                ("별칭 설정", {"agy_model": "flash"}), ("이름 표기", {"agy_model": "Gemini 3.8 Flash"}),
                                ("Argon 변형 설정", {"agy_model": "gemini-4-argon-medium"})):
            co2 = tmp / f"checkout-{len(backends)}-{label.replace(' ', '')}"; (co2 / ".ax").mkdir(parents=True)
            (co2 / ".ax" / "config.json").write_text(json.dumps({
                "project": "AXCluster", "this_host": {"host": "h"}, "backends": backends,
                "master": {"host": "127.0.0.1", "services": {"task_queue": 1}}}), encoding="utf-8")
            sent.clear(); argv_file.unlink(missing_ok=True)
            rc = G.main(["--remote", "--checkout", str(co2), "--brief-dir", str(brief),
                         "--out", str(research / f"2026-10-18-remote-{label}.md")], queue=fake_queue)
            check(f"[#830] 요청자 {label} → rc 2 · agy 호출 0 · 전송 0",
                  rc == 2 and not argv_file.exists() and not sent, f"{rc} {sent}")
        G.master_model = real_mm

        def dead_queue(method, path, payload=None):
            raise RuntimeError("[미연결] 마스터에 연결할 수 없다")

        os.environ["FAKE_AGY_MODE"] = "ok"
        o = research / "2026-10-17-remote-postfail.md"
        rc = G.main(["--remote", "--checkout", str(co), "--brief-dir", str(brief), "--out", str(o)],
                    queue=dead_queue)
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("[중요] 전송 실패 → 실행은 성공(rc 0 · 보고서)", rc == 0 and o.is_file(), str(rc))
        check("  결과 JSON usage_error 에 사유 (조용히 넘기지 않는다)",
              "[미연결]" in res.get("usage_error", ""), str(res))

        def refusing_queue(method, path, payload=None):
            return {"ok": False, "status": "not_mounted", "reason": "마운트되지 않은 프로젝트다"}

        o = research / "2026-10-17-remote-refused.md"
        rc = G.main(["--remote", "--checkout", str(co), "--brief-dir", str(brief), "--out", str(o)],
                    queue=refusing_queue)
        res = json.loads((o.with_suffix(".run") / "run.json").read_text(encoding="utf-8"))
        check("  큐 거절(ok:false) 도 usage_error 로 · 실행은 rc 0",
              rc == 0 and "not_mounted" in res.get("usage_error", ""), str(res))

        sent.clear()
        rc = G.main(["--remote", "--checkout", str(co), "--project", "NS", "--brief-dir", str(brief),
                     "--out", str(research / "2026-10-17-remote-mismatch.md")], queue=fake_queue)
        check("--project 가 체크아웃 설정과 다르면 rc 2 · 전송 0", rc == 2 and not sent, str(rc))
        rc = G.main(["--remote", "--checkout", str(tmp / "nowhere"), "--brief-dir", str(brief),
                     "--out", str(research / "2026-10-17-remote-nocfg.md")], queue=fake_queue)
        check("체크아웃 설정이 없으면 rc 2 (실행 전 거절)", rc == 2 and not sent, str(rc))
        rc = G.main(["--brief-dir", str(brief), "--out", str(research / "2026-10-17-noproj.md")])
        check("마스터 모드는 --project 필수 → rc 2", rc == 2, str(rc))

        # 실물 `queue_api` 가 프로젝트 태그를 싣는다 — 전송 함수만 가로챈다
        (co / ".ax" / "token").write_text("t" * 40, encoding="utf-8")
        cm = G._client_mcp()
        wire = []
        cm._call = lambda method, url, token, payload=None, root_hint=None: (
            wire.append((method, url, payload)) or {"ok": True, "record": {}})
        cm.tool_log_usage(cm.queue_api(co), G.usage_payload(
            {"cost_unknown": True}, lane="agy", rc=0, source=G.SOURCE, worker="h"))
        check("[중요] 실물 queue_api — URL·프로젝트 태그", wire and wire[0][1] == "http://127.0.0.1:1/api/v1/usage"
              and wire[0][2].get("project") == "AXCluster", str(wire))
        try:
            cm.tool_log_usage(lambda *a: {}, {"source": " "})
            check("source 비면 ClientError", False, "통과해버렸다")
        except cm.ClientError:
            check("source 비면 ClientError", True)
    finally:
        P.resolve_mounted_only = real_resolve
        os.environ["PATH"] = real_path
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_gemini_report: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
