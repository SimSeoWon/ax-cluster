"""`ax-gemini` 스킬의 실행부 — agy 로 리서치·보고서를 만들고 **기록을 강제한다** (사용자 결정 2026-10-09).

    AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.work.gemini_report --project AXCluster \\
        --brief-dir <scratch>/ax-gemini-<주제> --out reports/research/2026-10-09-<주제>.md

[중요] **왜 스킬 문서가 아니라 코드인가** — 「기록해라」를 절차서에 적으면 세션이 「해당 없음」을
판정할 수 있다(최상위 원칙: 필수 과정은 파이썬이 강제한다). 이 모듈을 거치면 성공이든 실패든
① 진행 로그(stderr, 30초 하트비트) ② 트윈 `usage_log.jsonl` 한 줄(`source="ax-gemini"`, `lane="agy"`)
③ 원본 봉투·stderr 보관(`<보고서>.run/`, 커밋하지 않는다 — `.gitignore`)이 **반드시** 남는다.

[주의] 형식 지식은 `usage.parse_agy_json` 한 곳이다 — 여기서 봉투를 따로 읽지 않는다.
[주의] 보고서 본문은 **이 모듈이 쓴다** — agy 가 파일을 쓰게 하지 않는다(지시와 다른 경로에 쓴
실측이 있다). 인용 대조는 세션의 몫이고, 머리말의 검증 줄은 「미검증」으로 시작한다.
[주의] 마스터 전용이다 — 트윈 `usage_log` 는 마스터에 있다. `.33` 기록 경로는 별도 일감(사용자 결정 (가)).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from master.work import usage as U

BRIEF = "BRIEF.md"
PROMPT = ("Read BRIEF.md in the added directory and follow it exactly. "
          "Return the full report as your response. Do not create or modify files.")
HEARTBEAT = 30
SOURCE = "ax-gemini"


def log(msg: str) -> None:
    print(f"[ax-gemini] {datetime.now():%H:%M:%S} {msg}", file=sys.stderr, flush=True)


def materials(brief_dir: Path) -> list:
    """지시서를 뺀 자료 파일 목록(상대 경로). 머리말과 시작 로그에 쓴다."""
    return sorted(str(p.relative_to(brief_dir)) for p in brief_dir.rglob("*")
                  if p.is_file() and p.name != BRIEF)


def agy_version(exe: str) -> str:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "미상"
    except (OSError, subprocess.TimeoutExpired):
        return "미상"


def run_agy(exe: str, brief_dir: Path, *, timeout: int) -> tuple:
    """agy 를 돌린다 → `(rc, stdout, stderr, seconds)`. 도는 동안 하트비트를 찍는다.

    [중요] **`-p` 는 프롬프트 바로 앞이다** (실측 2026-08-08). 프롬프트는 ASCII 한 문장 —
    내용은 `BRIEF.md` 파일이 나른다(백틱·CP949 회피).
    """
    cmd = [exe, "--dangerously-skip-permissions", "--output-format", "json",
           "--add-dir", str(brief_dir), "-p", PROMPT]
    t0 = time.monotonic()
    done = threading.Event()

    def beat():
        while not done.wait(HEARTBEAT):
            log(f"실행 중 — 경과 {time.monotonic() - t0:.0f}초")

    threading.Thread(target=beat, daemon=True).start()
    try:
        r = subprocess.run(cmd, cwd=brief_dir, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        rc, out, err = r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, _text(e.stdout), _text(e.stderr) + f"\n시간 초과 ({timeout}초)"
    except OSError as e:
        rc, out, err = 127, "", f"{type(e).__name__}: {e}"
    finally:
        done.set()
    return rc, out, err, time.monotonic() - t0


def _text(b) -> str:
    if b is None:
        return ""
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)


def header(*, version: str, model: str, mats: list, seconds: float, u, project: str) -> str:
    tok = ("미상" if u is None or not u.known else
           f"입력 {u.input_tokens if u.input_tokens is not None else '미상'} / "
           f"출력 {u.output_tokens if u.output_tokens is not None else '미상'}"
           + (f" / 캐시읽기 {u.cache_read}" if u.cache_read else ""))
    return "\n".join([
        f"> 작성: Gemini (agy {version}{' · ' + model if model else ''}) · 실행: `master.work.gemini_report` · "
        f"{datetime.now():%Y-%m-%d %H:%M} · 프로젝트 {project}",
        f"> 자료: {', '.join(mats) if mats else '(없음)'}",
        "> 검증: 미검증 — 위임한 세션이 인용을 원본과 대조한 뒤 이 줄을 갱신한다",
        f"> 소요 {seconds:.0f}초 · 토큰 {tok}",
        "", ""])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.work.gemini_report")
    ap.add_argument("--project", required=True, help="마운트된 프로젝트 — 사용량이 그 트윈에 남는다")
    ap.add_argument("--brief-dir", required=True, help="BRIEF.md 와 자료 사본이 든 스크래치 폴더")
    ap.add_argument("--out", required=True, help="보고서 경로 — reports/research/ 아래 .md")
    ap.add_argument("--timeout", type=int, default=U.TIMEOUT)
    a = ap.parse_args(argv)

    from master.context_search import paths as P
    try:
        paths = P.resolve_mounted_only(a.project)
    except Exception as e:                                       # noqa: BLE001
        log(f"거절 — {e}")
        return 2
    brief_dir = Path(a.brief_dir).resolve()
    out = Path(a.out).resolve()
    if not (brief_dir / BRIEF).is_file():
        log(f"거절 — {brief_dir / BRIEF} 가 없다")
        return 2
    if out.suffix != ".md" or out.parent.name != "research" or out.parent.parent.name != "reports":
        log(f"거절 — 보고서는 reports/research/<이름>.md 여야 한다: {out}")
        return 2
    if out.exists():
        log(f"거절 — 이미 있다(덮어쓰지 않는다): {out}")
        return 2
    exe = shutil.which("agy")
    mats = materials(brief_dir)
    run_dir = out.with_suffix(".run")

    if not exe:
        log("실패 — agy 가 없다")
        U.record(paths.usage_log, {"cost_unknown": True, "note": "agy 없음"}, lane="agy",
                 rc=127, source=SOURCE)
        return 1

    version = agy_version(exe)
    log(f"시작 — agy {version} · 자료 {len(mats)}개 · 지시서 {brief_dir / BRIEF}")
    rc, stdout, stderr, secs = run_agy(exe, brief_dir, timeout=a.timeout)

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "out.json").write_text(stdout, encoding="utf-8")
    (run_dir / "err.log").write_text(stderr, encoding="utf-8")
    shutil.copy2(brief_dir / BRIEF, run_dir / BRIEF)

    parsed = U.parse_agy_json(stdout) if stdout else None
    text, u, status, model = parsed if parsed else ("", None, "", "")
    why = ("" if rc == 0 and parsed and text.strip() else
           f"rc={rc}" if rc != 0 else "봉투 아님" if not parsed else "response 비었음")
    meta = U.meta_from_usage(u) if u is not None else {"cost_unknown": True}
    if why:
        meta["note"] = why if not meta.get("note") else f"{why} · {meta['note']}"
    rec = U.record(paths.usage_log, meta, lane="agy", rc=rc if rc else (0 if not why else 1),
                   seconds=secs, source=SOURCE, model=model)
    if rec.get("error"):
        log(f"[주의] 사용량 기록 실패 — {rec['error']}")
    summary = {"ok": not why, "why": why, "rc": rc, "seconds": round(secs, 1),
               "status": status, "model": model, "tokens": (u.as_dict() if u else None),
               "usage_log": str(paths.usage_log), "run_dir": str(run_dir),
               "report": "" if why else str(out)}
    (run_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    if why:
        log(f"실패 — {why} · {secs:.0f}초 · stderr 끝: {stderr.strip()[-300:] or '(없음)'}")
        print(json.dumps(summary, ensure_ascii=False))
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header(version=version, model=model, mats=mats, seconds=secs, u=u,
                          project=a.project) + text.strip() + "\n", encoding="utf-8")
    log(f"완료 — {secs:.0f}초 · {u.summary() if u else '토큰 미상'} · 보고서 {out}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
