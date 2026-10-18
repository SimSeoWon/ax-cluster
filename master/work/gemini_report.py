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
[중요] **요청자(`.33`) 는 `--remote` 로 돈다** (`#763`, 사용자 승인 2026-10-17). 트윈 `usage_log` 는
마스터에 있으므로 기록 한 줄을 큐(`POST /api/v1/usage`)로 보내 마스터가 대행한다 — 프로젝트 태그·
`worker`(= `.ax/config.json` `this_host.host`)는 체크아웃 설정에서 온다. 배달 위치는
`.ax/lib/axmaster/work/` 이고 큐 호출은 옆 패키지의 `clientside/client_mcp.py` 를 경로로 로드한다.
[주의] 전송이 실패해도 실행은 실패가 아니다 — stderr 와 결과 JSON `usage_error` 에 사유를 남긴다.

    "<backends.python>" -c "import sys; sys.path.insert(0, '.ax/lib'); from axmaster.work import gemini_report as G; sys.exit(G.main())" \\
        --remote --brief-dir <scratch>/ax-gemini-<주제> --out reports/research/2026-10-17-<주제>.md

🔴 [중요] **모델은 정본 id 로 명시한다** (`#830`, 사용자 승인 2026-10-18). 설정의 별칭이 조용히
「Gemini 4 Argon」으로 풀려 한도를 태웠다. 그래서 매 실행 `agy --model <id>` 를 싣는다 — 출처는
`--remote` 면 체크아웃 `.ax/config.json` 의 `backends.agy_model`, 마스터면 `agy_models.DEFAULT_MODEL`,
`--model` 을 주면 그 값이다. 값이 없거나 정본 모양(`[a-z0-9][a-z0-9.-]*` · `gemini-` 로 시작 — 사용자 결정
2026-10-18)이 아니거나 `argon` 이 들면
**agy 를 부르지 않고 거절(종료 2)** 한다 — Argon 은 `--model` 과 `--allow-argon` 을 **함께** 준 때만.
폴백·쿨다운·자동 Argon 은 없다. 실행 뒤 `--log-file` 로그(`usage.parse_agy_log`)로 **실제 모델**을
읽어 요청과 다르거나 읽지 못하면 **출력을 버린다**(종료 1 · 보고서 없음 · 원본은 `.run/` 에 남는다).
[주의] `agy_models` 는 `fcntl`(리눅스 전용)을 쓴다 — `--remote`(`.33` Windows) 경로에서는 임포트하지 않는다.
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

from . import usage as U          # [중요] 상대 임포트 — 요청자 배달본(`axmaster.work`)에서도 산다

BRIEF = "BRIEF.md"
PROMPT = ("Read BRIEF.md in the added directory and follow it exactly. "
          "Return the full report as your response. Do not create or modify files.")
HEARTBEAT = 30
SOURCE = "ax-gemini"
# 보고서 인용 `src/경로:줄` 또는 `src/경로:시작-끝`. 경로에는 공백·백틱·괄호·쉼표가 없다
_CITE = re.compile(r"(src/[^\s`:()\[\],]+):(\d+)(?:-(\d+))?")
CITE_SHOW = 12          # 인용 하나당 citations.txt 에 싣는 최대 줄 수 (긴 범위는 앞부분만)
SUMMARY_CHARS = 600     # 결과 JSON 에 싣는 요약 길이 — 세션이 본문을 안 열고 보고할 만큼만
# agy 정본 모델 id 모양 (`agy models` 의 첫 칸 · `agy_models.parse_catalog` 와 같은 식) — `#830`
_MODEL_ID = re.compile(r"[a-z0-9][a-z0-9.-]*")


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


def model_refusal(model: str, *, explicit: bool = False, allow_argon: bool = False) -> str:
    """요청 모델이 쓸 수 있으면 `""`, 아니면 거절 사유 (`#830`). [중요] **폴백하지 않는다** —
    빈 값·별칭·Argon 은 agy 를 부르기 **전에** 막는다. Argon 은 `--model` 로 직접 고르고
    `--allow-argon` 을 함께 준 때만(사용자 정책: 사용자가 명시적으로 요청할 때만)."""
    if not model:
        return "agy 모델이 설정되지 않았다(backends.agy_model 없음) — agy 를 부르지 않는다"
    if not _MODEL_ID.fullmatch(model) or not model.startswith("gemini-"):
        return (f"agy 모델 {model!r} 이 정본 id 모양이 아니다(gemini- 로 시작하는 id 만 · 별칭 금지)"
                " — agy 를 부르지 않는다")
    if "argon" in model.casefold() and not (explicit and allow_argon):
        return (f"agy 모델 {model} 은 Argon 이다 — --model 과 --allow-argon 을 함께 줄 때만 쓴다"
                " (자동 경로 금지)")
    return ""


def configured_model(root: Path) -> str:
    """요청자 체크아웃 `.ax/config.json` 의 `backends.agy_model` — 없으면 `""` (마스터가 배달한 값)."""
    cfg = _client_mcp().load_config(root)
    v = (cfg.get("backends") or {}).get("agy_model") if isinstance(cfg, dict) else ""
    return v.strip() if isinstance(v, str) else ""


def master_model() -> str:
    """마스터 정본 `agy_models.DEFAULT_MODEL`. [주의] 마스터 경로 전용 지연 임포트 — `--remote` 에서
    부르지 않는다(`fcntl` 이 없는 Windows 에서 죽는다)."""
    from master import agy_models
    return str(agy_models.DEFAULT_MODEL or "").strip()


def run_agy(exe: str, brief_dir: Path, *, timeout: int, log_file: Path | None = None,
            model: str = "") -> tuple:
    """agy 를 돌린다 → `(rc, stdout, stderr, seconds)`. 도는 동안 하트비트를 찍는다.

    [중요] **`-p` 는 프롬프트 바로 앞이다** (실측 2026-08-08). 프롬프트는 ASCII 한 문장 —
    내용은 `BRIEF.md` 파일이 나른다(백틱·CP949 회피).
    🔴 `model` 은 **정본 id 로만** — 부르는 쪽이 `model_refusal` 로 거른 값이다(`#830`).
    """
    cmd = [exe, "--dangerously-skip-permissions", "--output-format", "json",
           "--add-dir", str(brief_dir)]
    if model:
        cmd += ["--model", model]
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
    bad_file = bad_range = unreadable = 0
    lines_cache: dict = {}
    read_errors: dict = {}
    for rel, a, b in seen:
        f = brief_dir / rel
        if rel not in lines_cache:
            try:
                lines_cache[rel] = (f.read_text(encoding="utf-8", errors="replace").splitlines()
                                    if f.is_file() else None)
            except OSError as e:
                lines_cache[rel] = None
                read_errors[rel] = f"{type(e).__name__}: {e}"
        lines = lines_cache[rel]
        tag = f"{rel}:{a}" + (f"-{b}" if b != a else "")
        if rel in read_errors:
            unreadable += 1
            rows.append(f"### {tag}  [읽기 실패] {read_errors[rel]}")
            continue
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
             "unreadable_file": unreadable, "in_range": len(seen) - bad_file - bad_range - unreadable}
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
           f"범위 밖 {cites['out_of_range']} · 파일 없음 {cites['missing_file']} · "
           f"읽기 실패 {cites.get('unreadable_file', 0)}" if cites else ""),
        f"> 소요 {seconds:.0f}초 · 토큰 {tok}",
        *([f"> [주의] {warn} — 본문이 불완전할 수 있다"] if warn else []),
        *([f"> 참고: {info}"] if info else []),
        "", ""])


def _client_mcp():
    """큐 호출자 — 배달본은 옆 패키지(`axmaster/clientside/`), 저장소는 `client/runtime/` 이다.

    [주의] 패키지 이름으로 임포트하지 않는다 — 저장소엔 `master.clientside` 가 없다(`#263`).
    `fix_flow.py` 와 같은 방식(경로 로드)이라 두 집 문제가 없다.
    """
    import importlib.util
    here = Path(__file__).resolve()
    for src in (here.parents[1] / "clientside" / "client_mcp.py",
                here.parents[2] / "client" / "runtime" / "client_mcp.py"):
        if src.is_file():
            spec = importlib.util.spec_from_file_location("ax_client_mcp_for_gemini", src)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("client_mcp.py 를 찾지 못했다 — 마스터에서 재배달: python -m master.client update")


def _winsession():
    """세션 0 판정 모듈 (`#832`) — `_client_mcp` 와 같은 경로 로드. 배달본은 `axmaster/clientside/`,
    저장소는 `client/runtime/` 이다. 못 찾으면 `None`."""
    import importlib.util
    here = Path(__file__).resolve()
    for src in (here.parents[1] / "clientside" / "winsession.py",
                here.parents[2] / "client" / "runtime" / "winsession.py"):
        if src.is_file():
            spec = importlib.util.spec_from_file_location("ax_winsession_for_gemini", src)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def session0_refusal() -> str:
    """🔴 `#832` — Windows 세션 0(SSH)이면 고정 사유, 아니면 `""`. agy 로그인은 대화형 세션 자격이라
    세션 0 에서는 *"not logged into Antigravity"* 로 늦게 죽고 「실제 모델 미상」으로 오보된다(실측 2026-10-18).
    [주의] Windows 에서 판정 모듈을 못 불러오면 **거절**한다(fail-closed) — 리눅스는 판정할 것이 없다."""
    try:
        ws = _winsession()
    except Exception as e:                                       # noqa: BLE001
        ws, err = None, f"{type(e).__name__}: {e}"
    else:
        err = "winsession.py 가 배달되지 않았다"
    if ws is None:
        return (f"세션 판정 모듈을 못 불러왔다({err}) — 마스터에서 재배달: python -m master.client update"
                if sys.platform == "win32" else "")
    return ws.refuse_reason()


def usage_payload(meta: dict, *, lane: str, rc: int, seconds: float = 0.0, source: str,
                  model: str = "", note: str = "", worker: str = "") -> dict:
    """`U.record` 인자 → `POST /api/v1/usage` 본문. [중요] 모양 지식은 `meta_from_usage` 의 키 그대로다 —
    서버가 같은 meta 를 다시 만들어 `U.record` 에 넘기므로 레코드가 마스터 로컬 기록과 같아진다."""
    meta = meta or {}
    out = {"source": source, "lane": lane, "rc": int(rc), "seconds": round(float(seconds or 0.0), 1),
           "model": model, "note": note, "worker": worker,
           "usage": dict(meta.get("usage") or {}), "session_id": str(meta.get("session_id") or "")}
    if not meta.get("cost_unknown") and meta.get("total_cost_usd") is not None:
        out["total_cost_usd"] = float(meta["total_cost_usd"])
    return out


def remote_recorder(root: Path, *, api=None):
    """요청자 기록기 → `(record(meta, **kw) -> dict, 설명, 프로젝트, worker)`. **예외를 올리지 않는다** —
    실패는 `{"error": …}` 로 돌려준다(`U.record` 와 같은 비차단 계약).

    [중요] `api` 를 주입할 수 있다 — 테스트·드라이런은 가짜 큐를 꽂는다. 없으면 체크아웃의
    `.ax/config.json`·`.ax/token` 으로 `queue_api` 를 만든다(프로젝트 태그는 거기서 붙는다).
    """
    cm = _client_mcp()
    cfg = cm.load_config(root)
    project = str(cfg.get("project") or "").strip()
    worker = str((cfg.get("this_host") or {}).get("host") or "").strip()
    q = api or cm.queue_api(root)

    def record(meta: dict, **kw) -> dict:
        body = usage_payload(meta, worker=worker, **kw)
        try:
            got = cm.tool_log_usage(q, body)
        except Exception as e:                                   # noqa: BLE001
            return {**body, "error": f"{type(e).__name__}: {e}"}
        if not isinstance(got, dict):
            return {**body, "error": f"큐 응답이 객체가 아니다: {str(got)[:200]}"}
        if not got.get("ok"):
            why = got.get("reason") or got.get("error") or str(got)[:200]
            return {**body, "error": f"큐 거절({got.get('status') or 'ok:false'}): {why}"}
        return got.get("record") or body

    return record, f"마스터 트윈({project or '?'}) via POST /api/v1/usage", project, worker


def main(argv=None, *, queue=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.work.gemini_report")
    ap.add_argument("--project", default="",
                    help="마운트된 프로젝트 — 사용량이 그 트윈에 남는다 (마스터 필수 · --remote 는 설정값)")
    ap.add_argument("--brief-dir", required=True, help="BRIEF.md 와 자료 사본이 든 스크래치 폴더")
    ap.add_argument("--out", required=True, help="보고서 경로 — reports/research/ 아래 .md")
    ap.add_argument("--timeout", type=int, default=U.TIMEOUT)
    ap.add_argument("--remote", action="store_true",
                    help="요청자(.33) — 사용량을 큐로 보내 마스터 트윈에 남긴다 (#763)")
    ap.add_argument("--checkout", default="",
                    help="--remote 의 체크아웃 루트 (.ax/config.json 이 있는 곳, 기본 cwd)")
    ap.add_argument("--model", default="",
                    help="agy 정본 모델 id 를 직접 고른다 (기본: --remote 는 backends.agy_model, 마스터는 정본)")
    ap.add_argument("--allow-argon", action="store_true",
                    help="--model 로 Argon 을 고를 때만 — 사용자가 명시적으로 요청한 경우 (#830)")
    a = ap.parse_args(argv)
    # 🔴 `#832` — agy·모델 해석·요청자 설정보다 **먼저**. 실행 전 거절(종료 2)이라 사용량 행은 남기지 않는다
    #    (다른 종료 2 거절과 같은 계약 — agy 를 부르지 않았다).
    s0 = session0_refusal()
    if s0:
        log(f"거절 — {s0}")
        return 2
    if a.allow_argon and not a.model:
        log("거절 — --allow-argon 은 --model 과 함께만 쓴다")
        return 2

    if a.remote:
        try:
            record, usage_where, project, worker = remote_recorder(
                Path(a.checkout or ".").resolve(), api=queue)
        except Exception as e:                                   # noqa: BLE001
            log(f"거절 — 요청자 설정을 읽지 못했다: {e}")
            return 2
        if a.project and project and a.project != project:
            log(f"거절 — --project {a.project} 가 체크아웃 설정 project({project}) 와 다르다")
            return 2
        a.project = project or a.project
        log(f"요청자 모드 — 기록은 {usage_where} · worker={worker or '(미상)'}")
        if a.model:
            want, want_from = a.model, "--model"
        else:
            try:
                want = configured_model(Path(a.checkout or ".").resolve())
            except Exception as e:                               # noqa: BLE001
                log(f"거절 — 요청자 설정에서 agy 모델을 읽지 못했다: {e}")
                return 2
            want_from = ".ax/config.json backends.agy_model"
    else:
        if not a.project:
            log("거절 — --project 가 필요하다 (요청자는 --remote)")
            return 2
        from master.context_search import paths as P
        try:
            paths = P.resolve_mounted_only(a.project)
        except Exception as e:                                   # noqa: BLE001
            log(f"거절 — {e}")
            return 2
        usage_where = str(paths.usage_log)

        def record(meta: dict, **kw) -> dict:
            return U.record(paths.usage_log, meta, **kw)
        if a.model:
            want, want_from = a.model, "--model"
        else:
            try:
                want = master_model()
            except Exception as e:                               # noqa: BLE001
                log(f"거절 — 마스터 정본 agy 모델을 읽지 못했다: {type(e).__name__}: {e}")
                return 2
            want_from = "agy_models.DEFAULT_MODEL"
    bad_model = model_refusal(want, explicit=bool(a.model), allow_argon=a.allow_argon)
    if bad_model:
        log(f"거절 — {bad_model} (출처 {want_from})")
        return 2
    log(f"요청 모델 {want} (출처 {want_from})")
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
        rec = record({"cost_unknown": True, "requested_model": want}, lane="agy", rc=127,
                     source=SOURCE, model=want, note="agy 없음")
        if rec.get("error"):
            log(f"[주의] 사용량 기록 실패 — {rec['error']}")
        return 1

    version = agy_version(exe)
    run_dir.mkdir(parents=True, exist_ok=True)
    agy_log = run_dir / "agy.log"
    log(f"시작 — agy {version} · 모델 {want} · 자료 {len(mats)}개 · 지시서 {brief_dir / BRIEF} · "
        f"agy 로그 {agy_log}")
    rc, stdout, stderr, secs = run_agy(exe, brief_dir, timeout=a.timeout, log_file=agy_log,
                                       model=want)

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
    # 🔴 실제 모델 — 로그 label/별칭 해석이 우선, 없으면 봉투 키. 요청과 다르거나 모르면 출력을 버린다
    actual = lg["model"] or (U.agy_model_id(model) if model else "")
    actual_from = lg.get("model_source") or ("envelope" if model else "")
    model = actual
    model_why = ("" if actual == want else
                 f"실제 모델 미상 — agy 로그에서 모델을 읽지 못했다(요청 {want}), 출력을 버린다" if not actual else
                 f"모델 불일치 — 요청 {want} · 실제 {actual}, 출력을 버린다")
    log(f"실제 모델 {actual or '(미상)'} (출처 {actual_from or '없음'}) · 판정 "
        + ("일치" if not model_why else "[주의] " + model_why))
    if model_why:
        why = f"{why} · {model_why}" if why else model_why
    bad_status = not why and status and status != "SUCCESS"
    recovered = bool(bad_status and lg["recovered"])
    info = (f"agy 재시도 {lg['retries']}회 후 완료 (마지막 실패: {lg['last_error']}) — "
            f"봉투 status={status} 는 첫 시도의 기록" if recovered else "")
    warn = ("" if not bad_status or recovered else
            f"agy status={status}" + (f": {err_text}" if err_text else "")
            + ("" if agy_log.is_file() else " · agy 로그 없음(회복 판정 불가)"))
    meta = U.meta_from_usage(u) if u is not None else {"cost_unknown": True}
    meta.update({"requested_model": want, "actual_model": actual, "model_source": actual_from})
    if a.remote:      # 큐 모델(`UsageReq`)엔 요청/실제 칸이 없다 — 비고로 남긴다
        meta["note"] = (f"요청 모델 {want}" + ("" if actual == want else f" · 실제 {actual or '미상'}")
                        + (f" · {meta['note']}" if meta.get("note") else ""))
    for msg in (why, warn, info):
        if msg:
            meta["note"] = msg if not meta.get("note") else f"{msg} · {meta['note']}"
    rec = record(meta, lane="agy", rc=rc if rc else (0 if not why else 1),
                 seconds=secs, source=SOURCE, model=actual or want, note=meta.get("note", ""))
    if rec.get("error"):
        log(f"[주의] 사용량 기록 실패 — {rec['error']}")
    summary = {"ok": not why and not warn, "why": why or warn, "rc": rc, "seconds": round(secs, 1),
               "status": status, "error": err_text, "model": model,
               "requested_model": want, "requested_from": want_from,
               "actual_model": actual, "actual_from": actual_from, "model_ok": not model_why,
               "retries": lg["retries"], "recovered": recovered,
               "tokens": (u.as_dict() if u else None),
               "usage_log": usage_where, "run_dir": str(run_dir),
               "report": "" if why else str(out)}
    if rec.get("error"):
        summary["usage_error"] = rec["error"]       # [중요] 조용히 넘기지 않는다 — 세션이 보고한다
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
        f"(범위 밖 {cites['out_of_range']} · 파일 없음 {cites['missing_file']} · "
        f"읽기 실패 {cites['unreadable_file']}) · 보고서 {out}")
    if info:
        log(f"참고 — {info}")
    if warn:
        log(f"[주의] 경고 — {warn} · 보고서는 썼다, 사용자에게 보고하고 대조를 더 할 것")
    print(json.dumps(summary, ensure_ascii=False))
    return 3 if warn else 0


if __name__ == "__main__":
    raise SystemExit(main())
