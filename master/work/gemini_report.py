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
[중요] **세션이 보고서 본문을 읽지 않게 한다** (사용자 요청 2026-10-09, `#762` 후속 — 인바운드 토큰).
본문은 이 프로세스 안에서 파일로 가고, 세션에는 로그 몇 줄과 결과 JSON 한 줄만 간다. 인용 대조
재료도 여기서 만든다 — 보고서의 `src/경로:줄` 인용을 뽑아 **범위를 결정적으로 검사**하고 인용된
원문 줄을 `<보고서>.run/citations.txt` 에 모은다. 세션은 그 파일에서 몇 개만 골라 내용을 대조한다.
[중요] **종료 코드** — 0 성공 · 1 실패(보고서 없음) · 2 실행 전 거절 · **3 경고**: 보고서는 썼지만
agy 봉투 `status` 가 `SUCCESS` 가 아니다(사용자 결정 2026-10-09 (나) — 본문을 버리지 않되 `ok:false`
로 내서 세션이 사용자에게 보고하고 대조를 더 하게 한다).
[중요] **단, agy 가 스스로 재시도해 회복했으면 성공이다** (사용자 결정 2026-10-09 A). 실행마다
`--log-file <보고서>.run/agy.log` 를 받아 `usage.parse_agy_log` 로 판정한다 — 「attempt N 실패 →
재시도 → 이후 생성 요청」이 로그에 있으면 종료 0 · 비고에 재시도 횟수. 로그가 없거나 회복 근거가
모자라면 종전대로 경고 3이다(모르면 회복으로 보지 않는다). 모델 이름도 그 로그에서 읽는다.
[주의] 마스터 전용이다 — 트윈 `usage_log` 는 마스터에 있다. `.33` 기록 경로는 별도 일감(사용자 결정 (가)).
"""
from __future__ import annotations

import argparse
import json
import re
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
# 보고서 인용 `src/경로:줄` 또는 `src/경로:시작-끝`. 경로에는 공백·백틱·괄호·쉼표가 없다
_CITE = re.compile(r"(src/[^\s`:()\[\],]+):(\d+)(?:-(\d+))?")
CITE_SHOW = 12          # 인용 하나당 citations.txt 에 싣는 최대 줄 수 (긴 범위는 앞부분만)
SUMMARY_CHARS = 600     # 결과 JSON 에 싣는 요약 길이 — 세션이 본문을 안 열고 보고할 만큼만


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


def run_agy(exe: str, brief_dir: Path, *, timeout: int, log_file: Path | None = None) -> tuple:
    """agy 를 돌린다 → `(rc, stdout, stderr, seconds)`. 도는 동안 하트비트를 찍는다.

    [중요] **`-p` 는 프롬프트 바로 앞이다** (실측 2026-08-08). 프롬프트는 ASCII 한 문장 —
    내용은 `BRIEF.md` 파일이 나른다(백틱·CP949 회피).
    """
    cmd = [exe, "--dangerously-skip-permissions", "--output-format", "json",
           "--add-dir", str(brief_dir)]
    if log_file is not None:
        cmd += ["--log-file", str(log_file)]
    cmd += ["-p", PROMPT]
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


def check_citations(text: str, brief_dir: Path) -> tuple:
    """보고서 인용 → `(통계 dict, citations.txt 본문)`. [중요] **범위만 판정한다** — 줄이 그 주장을
    하는지는 사람(세션)의 판단이다. 같은 인용은 한 번만 센다."""
    seen, rows = [], []
    for m in _CITE.finditer(text):
        key = (m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)))
        if key not in seen:
            seen.append(key)
    bad_file = bad_range = 0
    lines_cache: dict = {}
    for rel, a, b in seen:
        f = brief_dir / rel
        if rel not in lines_cache:
            lines_cache[rel] = (f.read_text(encoding="utf-8", errors="replace").splitlines()
                                if f.is_file() else None)
        lines = lines_cache[rel]
        tag = f"{rel}:{a}" + (f"-{b}" if b != a else "")
        if lines is None:
            bad_file += 1
            rows.append(f"### {tag}  [파일 없음]")
            continue
        if a < 1 or b < a or b > len(lines):
            bad_range += 1
            rows.append(f"### {tag}  [범위 밖 — 파일은 {len(lines)}줄]")
            continue
        shown = lines[a - 1:min(b, a - 1 + CITE_SHOW)]
        more = f"  (… {b - a + 1 - len(shown)}줄 생략)" if b - a + 1 > len(shown) else ""
        rows.append(f"### {tag}{more}\n" + "\n".join(f"{a + i:>5}  {t}" for i, t in enumerate(shown)))
    stats = {"total": len(seen), "missing_file": bad_file, "out_of_range": bad_range,
             "in_range": len(seen) - bad_file - bad_range}
    return stats, "\n\n".join(rows) + ("\n" if rows else "")


def summary_of(text: str) -> str:
    """`## 요약` 절(없으면 첫 문단) — 앞 `SUMMARY_CHARS` 자."""
    m = re.search(r"^##\s*요약\s*$\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    body = (m.group(1) if m else text.strip().split("\n\n", 1)[0]).strip()
    return body if len(body) <= SUMMARY_CHARS else body[:SUMMARY_CHARS].rstrip() + " …"


def header(*, version: str, model: str, mats: list, seconds: float, u, project: str,
           cites: dict | None = None, warn: str = "", info: str = "") -> str:
    tok = ("미상" if u is None or not u.known else
           f"입력 {u.input_tokens if u.input_tokens is not None else '미상'} / "
           f"출력 {u.output_tokens if u.output_tokens is not None else '미상'}"
           + (f" / 캐시읽기 {u.cache_read}" if u.cache_read else ""))
    return "\n".join([
        f"> 작성: Gemini (agy {version}{' · ' + model if model else ''}) · 실행: `master.work.gemini_report` · "
        f"{datetime.now():%Y-%m-%d %H:%M} · 프로젝트 {project}",
        f"> 자료: {', '.join(mats) if mats else '(없음)'}",
        "> 검증: 미검증 — 위임한 세션이 인용 내용을 원본과 대조한 뒤 이 줄을 갱신한다"
        + (f" · 범위 검사(자동): 인용 {cites['total']}개 — 범위 안 {cites['in_range']} · "
           f"범위 밖 {cites['out_of_range']} · 파일 없음 {cites['missing_file']}" if cites else ""),
        f"> 소요 {seconds:.0f}초 · 토큰 {tok}",
        *([f"> [주의] {warn} — 본문이 불완전할 수 있다"] if warn else []),
        *([f"> 참고: {info}"] if info else []),
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
        U.record(paths.usage_log, {"cost_unknown": True}, lane="agy",
                 rc=127, source=SOURCE, note="agy 없음")
        return 1

    version = agy_version(exe)
    run_dir.mkdir(parents=True, exist_ok=True)
    agy_log = run_dir / "agy.log"
    log(f"시작 — agy {version} · 자료 {len(mats)}개 · 지시서 {brief_dir / BRIEF} · agy 로그 {agy_log}")
    rc, stdout, stderr, secs = run_agy(exe, brief_dir, timeout=a.timeout, log_file=agy_log)

    (run_dir / "out.json").write_text(stdout, encoding="utf-8")
    (run_dir / "err.log").write_text(stderr, encoding="utf-8")
    shutil.copy2(brief_dir / BRIEF, run_dir / BRIEF)

    parsed = U.parse_agy_json(stdout) if stdout else None
    text, u, status, model = parsed if parsed else ("", None, "", "")
    why = ("" if rc == 0 and parsed and text.strip() else
           f"rc={rc}" if rc != 0 else "봉투 아님" if not parsed else "response 비었음")
    err_text = U.agy_envelope_error(stdout) if parsed else ""
    lg = U.parse_agy_log(agy_log.read_text(encoding="utf-8", errors="replace")
                         if agy_log.is_file() else "")
    model = model or lg["model"]
    bad_status = not why and status and status != "SUCCESS"
    recovered = bool(bad_status and lg["recovered"])
    info = (f"agy 재시도 {lg['retries']}회 후 완료 (마지막 실패: {lg['last_error']}) — "
            f"봉투 status={status} 는 첫 시도의 기록" if recovered else "")
    warn = ("" if not bad_status or recovered else
            f"agy status={status}" + (f": {err_text}" if err_text else "")
            + ("" if agy_log.is_file() else " · agy 로그 없음(회복 판정 불가)"))
    meta = U.meta_from_usage(u) if u is not None else {"cost_unknown": True}
    for msg in (why, warn, info):
        if msg:
            meta["note"] = msg if not meta.get("note") else f"{msg} · {meta['note']}"
    rec = U.record(paths.usage_log, meta, lane="agy", rc=rc if rc else (0 if not why else 1),
                   seconds=secs, source=SOURCE, model=model, note=meta.get("note", ""))
    if rec.get("error"):
        log(f"[주의] 사용량 기록 실패 — {rec['error']}")
    summary = {"ok": not why and not warn, "why": why or warn, "rc": rc, "seconds": round(secs, 1),
               "status": status, "error": err_text, "model": model,
               "retries": lg["retries"], "recovered": recovered,
               "tokens": (u.as_dict() if u else None),
               "usage_log": str(paths.usage_log), "run_dir": str(run_dir),
               "report": "" if why else str(out)}
    (run_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    if why:
        log(f"실패 — {why} · {secs:.0f}초 · stderr 끝: {stderr.strip()[-300:] or '(없음)'}")
        print(json.dumps(summary, ensure_ascii=False))
        return 1

    cites, cite_text = check_citations(text, brief_dir)
    (run_dir / "citations.txt").write_text(cite_text, encoding="utf-8")
    summary.update({"citations": cites, "citations_file": str(run_dir / "citations.txt"),
                    "summary": summary_of(text)})
    (run_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header(version=version, model=model, mats=mats, seconds=secs, u=u,
                          project=a.project, cites=cites, warn=warn, info=info) + text.strip() + "\n",
                   encoding="utf-8")
    log(f"완료 — {secs:.0f}초 · {u.summary() if u else '토큰 미상'} · 인용 {cites['total']}개 "
        f"(범위 밖 {cites['out_of_range']} · 파일 없음 {cites['missing_file']}) · 보고서 {out}")
    if info:
        log(f"참고 — {info}")
    if warn:
        log(f"[주의] 경고 — {warn} · 보고서는 썼다, 사용자에게 보고하고 대조를 더 할 것")
    print(json.dumps(summary, ensure_ascii=False))
    return 3 if warn else 0


if __name__ == "__main__":
    raise SystemExit(main())
