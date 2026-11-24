"""운영 스냅샷 — 열린 Redmine 일감과 서비스·워커 배달 상태를 손으로 돌려 Markdown 두 장에 남긴다 (`#839`).

    python -m master.ops_snapshot [--root PATH] [--project NAME] [--only redmine|ops]

        docs/snapshots/redmine-open.md   열린 일감 메타데이터(버전별) · 받은 수와 total_count
        docs/snapshots/ops-state.md      상주 서비스 · 마스터 HEAD·dirty · 마운트 프로젝트 워커 배달 리비전

[중요] **라이브가 아니다.** 사람이 돌린 그 시점의 사본이고, 파일마다 한 벌만 덮어쓴다. `doc_sync` 는
       파일만 읽는다 — 네트워크·프로세스에 닿는 것은 이 모듈뿐이다(인수인계서 근거 자료).
[중요] **못 닿은 것을 「없음」으로 접지 않는다.** 조회 실패는 빈 표가 아니라 `닿지 않았다: <사유>` 줄로
       남기고 rc 1 로 끝낸다(파일은 그래도 쓴다). 받은 수와 `total_count` 가 다르면 둘 다 보인다.
[중요] **메타데이터만 싣는다.** 일감 본문·노트·메일 주소·절대 경로·토큰은 출력에 들어가지 않는다 —
       Redmine 은 키 없는 공개 읽기 API(`issue_snapshot._fetch_public` 과 같은 길)만 쓴다.

검사 대역 자리: `fetch_page`(Redmine 한 쪽) · `runner`(systemctl·git) · `workers`(워커 배달 판정) ·
`mounted`(마운트 프로젝트) · `now`(생성 시각) — 같은 입력이면 같은 바이트가 나온다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

KST = timezone(timedelta(hours=9), "KST")
REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = Path("docs") / "snapshots"
REDMINE_FILE = SNAPSHOT_DIR / "redmine-open.md"
OPS_FILE = SNAPSHOT_DIR / "ops-state.md"

DEFAULT_REDMINE_PROJECT = "ax-cluster"
PAGE_LIMIT = 100
MAX_PAGES = 50                      # 끝없는 페이지 루프 방지 — 넘으면 받은 수가 total_count 와 갈려 보인다
FETCH_TIMEOUT = 10.0
CMD_TIMEOUT = 15
IDEA_MARK = "아이디어"
NO_VERSION = "(버전 없음)"
UNREACHED = "닿지 않았다"
HAND_RUN = ("손으로 돌린 스냅샷이다(`python -m master.ops_snapshot`) — 라이브가 아니다. "
            "지금 값은 원천을 다시 조회한다.")

# [중요] 출력에 절대 경로·메일·비밀이 새지 않게 한다 — 사유 문자열은 예외 메시지에서 오므로 경로를 품기 쉽다.
_WIN_PATH = re.compile(r"[A-Za-z]:[\\/][^\s'\"`|)]*")
_POSIX_PATH = re.compile(r"(?<![\w.~:/])/(?:home|root|tmp|etc|usr|var|opt|mnt|srv|run|media|proc|Users)/[^\s'\"`|)]*"
                         r"|(?<![\w.~:/])~/[^\s'\"`|)]*")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SECRET = re.compile(r"(?i)\b(token|api[_-]?key|secret|password)\s*[:=]\s*\S+|\b(bearer)\s+[\w.~+/=-]{12,}")


def scrub(text) -> str:
    """경로·메일·비밀 꼴을 가린다. 표 칸에 넣을 수 있게 줄바꿈·`|` 도 고른다."""
    s = " ".join(str(text or "").split())
    s = _WIN_PATH.sub("<경로>", s)
    s = _POSIX_PATH.sub("<경로>", s)
    s = _EMAIL.sub("<메일>", s)
    s = _SECRET.sub(lambda m: f"{m.group(1) or m.group(2)} <가림>", s)
    return s.replace("|", "\\|")


def _reason(e) -> str:
    """예외 → 짧은 사유(가림 적용)."""
    if isinstance(e, BaseException):
        e = f"{type(e).__name__}: {e}"
    return scrub(str(e))[:160]


def kst_now(now=None) -> str:
    t = now or datetime.now(KST)
    if t.tzinfo is None:
        t = t.replace(tzinfo=KST)
    return t.astimezone(KST).isoformat(timespec="seconds")


# ── 기본 대역(실물) ─────────────────────────────────────────────────────────────

def _redmine_base() -> str:
    from master.redmine import base_url
    return base_url()


def _query(project: str) -> str:
    return (f"/issues.json?project_id={quote(project)}&status_id=open"
            f"&limit={PAGE_LIMIT}&sort=id:desc")


def _fetch_page_public(project: str, offset: int) -> dict:
    """공개 읽기 API 한 쪽. 실패는 예외로 올린다(`collect_redmine` 이 사유로 바꾼다)."""
    url = f"{_redmine_base()}{_query(project)}&offset={int(offset)}"
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
        return json.load(resp)


def _run(argv) -> tuple:
    """명령 한 번 — `(rc, stdout)`. 예외를 던지지 않는다."""
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=CMD_TIMEOUT)
        out = (p.stdout or "").strip() if p.returncode == 0 else (p.stderr or p.stdout or "").strip()
        return p.returncode, out
    except (OSError, subprocess.SubprocessError) as e:
        return 255, f"{type(e).__name__}: {e}"


def _mounted() -> dict:
    """마운트된 프로젝트와 그 `redmine.project`. 못 읽으면 `error`."""
    try:
        from master.projects.config import Registry
        reg = Registry.load()
        name = (reg.active or "").strip()
        if not name:
            return {"project": "", "redmine": "", "error": "마운트된 프로젝트가 없다"}
        return {"project": name, "redmine": reg.config_of(name).redmine_project or ""}
    except Exception as e:                                  # noqa: BLE001 — 사유로 남긴다
        return {"project": "", "redmine": "", "error": _reason(e)}


def _workers(project: str, head: str) -> list:
    """마운트 프로젝트 작업장마다 배달 리비전 판정 — `bundle.compare_version` 을 그대로 쓴다.

    [중요] 정의를 새로 만들지 않는다. `delivered_stamp`·`compare_version` 이 필요로 하는 것은
    host·user·path·`windows`(경로 구분자)뿐이라 전체 `probe`(claude·codex·UE5·ollama 측정)를 돌리지 않고
    `HostFacts` 를 직접 만든다. OS 는 등록 경로 꼴로 가른다(`setup_host.is_windows_path`).
    배달 도장을 먼저 읽어 「못 닿음」과 「판정 unknown」을 가른다(그래서 같은 파일을 두 번 읽는다).
    """
    from master.client import bundle
    from master.client.setup_host import is_windows_path

    rows = []
    for host, user, path, driven, role, dispatch in bundle.workshops(project):
        row = {"host": host, "role": role, "commit": "", "verdict": "", "behind": None,
               "note": "", "error": ""}
        if not user or not path:
            row["error"] = "user/path 미등록"
            rows.append(row)
            continue
        f = bundle.HostFacts(host=host, user=user, path=path, driven=driven, role=role,
                             dispatch=dispatch, os="windows" if is_windows_path(path) else "linux")
        try:
            stamp = bundle.delivered_stamp(f)
            if stamp.get("error"):
                row["error"] = _reason(stamp["error"])
            else:
                row["commit"] = str(stamp.get("commit") or "")[:12]
                got = bundle.compare_version(f, head=head)
                row.update(verdict=got.get("verdict") or "unknown", behind=got.get("behind"),
                           note=_reason(got.get("reason") or ""))
        except Exception as e:                              # noqa: BLE001 — 한 대 실패가 나머지를 막지 않는다
            row["error"] = _reason(e)
        rows.append(row)
    return rows


# ── 수집 ────────────────────────────────────────────────────────────────────

def collect_redmine(project: str, fetch_page) -> dict:
    """열린 일감 전부(쪽을 넘기며). 메타데이터만 남긴다 — 본문·노트·사람 정보는 버린다."""
    seen: dict = {}
    total = None
    pages = 0
    try:
        offset = 0
        while pages < MAX_PAGES:
            data = fetch_page(project, offset) or {}
            pages += 1
            if total is None and data.get("total_count") is not None:
                total = int(data["total_count"])
            batch = data.get("issues") or []
            for iss in batch:
                iid = int(iss.get("id"))
                seen.setdefault(iid, _meta(iss))
            offset += len(batch)
            if not batch or len(batch) < PAGE_LIMIT or (total is not None and offset >= total):
                break
    except Exception as e:                                  # noqa: BLE001
        return {"ok": False, "error": _reason(e), "issues": [], "total": total, "pages": pages}
    return {"ok": True, "error": "", "issues": list(seen.values()), "total": total, "pages": pages}


def _name(v) -> str:
    return str((v or {}).get("name") or "") if isinstance(v, dict) else ""


def _date_kst(raw) -> str:
    s = str(raw or "")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST).date().isoformat()
    except ValueError:
        return s[:10]


def _meta(iss: dict) -> dict:
    return {"id": int(iss.get("id")), "subject": str(iss.get("subject") or ""),
            "status": _name(iss.get("status")), "done_ratio": int(iss.get("done_ratio") or 0),
            "priority": _name(iss.get("priority")), "updated": _date_kst(iss.get("updated_on")),
            "version": _name(iss.get("fixed_version"))}


def collect_services(runner) -> list:
    from master.service_freshness import RESIDENT
    rows = []
    for unit in sorted(RESIDENT):
        rc, out = runner(["systemctl", "show", unit, "-p", "LoadState", "-p", "ActiveState",
                          "-p", "SubState", "-p", "ExecMainStartTimestamp"])
        kv = dict(line.split("=", 1) for line in (out or "").splitlines() if "=" in line)
        row = {"unit": unit, "active": kv.get("ActiveState", ""), "sub": kv.get("SubState", ""),
               "started": kv.get("ExecMainStartTimestamp", ""), "error": ""}
        if rc != 0:
            row["error"] = f"systemctl rc={rc} {_reason(out)}".strip()
        elif not row["active"]:
            row["error"] = "ActiveState 가 없다"
        elif kv.get("LoadState") == "not-found":
            row["error"] = "유닛이 없다(LoadState=not-found)"
        rows.append(row)
    return rows


def collect_master(root: Path, runner) -> dict:
    """마스터 HEAD 와 작업트리 dirty — 스냅샷을 쓰기 **전에** 잰다."""
    rc, head = runner(["git", "-C", str(root), "rev-parse", "HEAD"])
    if rc != 0 or not re.fullmatch(r"[0-9a-f]{40}", (head or "").strip()):
        return {"head": "", "dirty": None, "error": f"git rev-parse rc={rc} {_reason(head)}".strip()}
    rc2, st = runner(["git", "-C", str(root), "status", "--porcelain"])
    return {"head": head.strip(), "dirty": (bool(st.strip()) if rc2 == 0 else None), "error": ""}


# ── 그리기 ──────────────────────────────────────────────────────────────────

def _header(title: str, sources: list, meta: dict) -> list:
    head = meta.get("head") or ""
    lines = [f"# {title}", "", f"> {HAND_RUN}", ""]
    lines += [f"- 출처: {s}" for s in sources]
    lines.append(f"- 생성: {meta['generated']}")
    lines.append(f"- 마스터 HEAD: {head[:12] if head else UNREACHED + ': ' + (meta.get('head_error') or '?')}")
    lines.append("")
    return lines


def render_redmine(red: dict, project: str, meta: dict) -> str:
    src = [f"`GET {meta.get('redmine_base', '')}{_query(project)}&offset=N` (공개 읽기 API, 키 없음)"]
    lines = _header(f"Redmine 열린 일감 — {project}", src, meta)
    if not red["ok"]:
        lines += [f"{UNREACHED}: {red['error']}", ""]
        return "\n".join(lines).rstrip("\n") + "\n"

    issues = red["issues"]
    total = red["total"]
    groups: dict = {}
    for i in issues:
        groups.setdefault(i["version"] or NO_VERSION, []).append(i)
    idea = sorted(v for v in groups if IDEA_MARK in v)
    idea_n = sum(len(groups[v]) for v in idea)
    named = sorted(v for v in groups if v != NO_VERSION and v not in idea)
    order = named + ([NO_VERSION] if NO_VERSION in groups else [])

    lines += ["## 집계", "", f"- 받은 열린 일감: {len(issues)}건 · total_count {total if total is not None else '없음'}"]
    if total is None or total != len(issues):
        lines.append(f"- [주의] 받은 수와 total_count 가 다르다 — 받은 {len(issues)} ≠ total_count "
                     f"{total if total is not None else '없음'} (쪽 {red['pages']})")
    for v in idea:
        lines.append(f"- {scrub(v)}: {len(groups[v])}건 (행 생략 — 일감이 아니다)")
    lines.append("")
    for v in order:
        rows = sorted(groups[v], key=lambda i: -i["id"])
        lines += [f"## {scrub(v)} ({len(rows)}건)", "",
                  "| # | 제목 | 상태 | 진척 | 우선순위 | 갱신 |", "|---|---|---|---|---|---|"]
        for i in rows:
            lines.append(f"| {i['id']} | {scrub(i['subject'])} | {scrub(i['status'])} | {i['done_ratio']}% "
                         f"| {scrub(i['priority'])} | {i['updated']} |")
        lines.append("")
    meta["idea_count"] = idea_n
    return "\n".join(lines).rstrip("\n") + "\n"


def render_ops(master: dict, services: list, workers: dict, meta: dict) -> str:
    src = ["`systemctl show <unit> -p ActiveState -p SubState -p ExecMainStartTimestamp` (읽기 전용)",
           "`git rev-parse HEAD` · `git status --porcelain` (마스터 체크아웃)",
           "워커 `.ax/config.json` 의 `delivered_by` — `master.client.bundle.compare_version`"]
    lines = _header("운영 상태", src, meta)

    lines += ["## 마스터", "", "| 항목 | 값 |", "|---|---|"]
    if master["error"]:
        lines.append(f"| HEAD | {UNREACHED}: {master['error']} |")
    else:
        dirty = {True: "dirty", False: "clean", None: f"{UNREACHED}: git status"}[master["dirty"]]
        lines += [f"| HEAD | {master['head'][:12]} |", f"| 작업트리 | {dirty} |"]
    lines.append("")

    lines += ["## 상주 서비스", "", "| 유닛 | ActiveState | SubState | 기동 시각 |", "|---|---|---|---|"]
    for s in services:
        if s["error"]:
            lines.append(f"| {s['unit']} | {UNREACHED}: {s['error']} | — | — |")
        else:
            lines.append(f"| {s['unit']} | {scrub(s['active'])} | {scrub(s['sub']) or '—'} "
                         f"| {scrub(s['started']) or '—'} |")
    lines.append("")

    proj = workers.get("project") or "?"
    lines += [f"## 워커 배달 리비전 — 마운트 프로젝트 {scrub(proj)}", ""]
    if workers.get("error"):
        lines += [f"{UNREACHED}: {workers['error']}", ""]
    elif not workers.get("rows"):
        lines += ["(등록된 작업장 없음)", ""]
    else:
        lines += ["| 호스트 | 역할 | 배달 커밋 | 판정 | 뒤처짐 | 비고 |", "|---|---|---|---|---|---|"]
        for w in sorted(workers["rows"], key=lambda r: r["host"]):
            if w["error"]:
                lines.append(f"| {scrub(w['host'])} | {scrub(w['role'])} | {UNREACHED}: {w['error']} | — | — | — |")
            else:
                behind = "—" if w["behind"] is None else str(w["behind"])
                lines.append(f"| {scrub(w['host'])} | {scrub(w['role'])} | {w['commit'] or '—'} "
                             f"| {w['verdict']} | {behind} | {w['note'] or '—'} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


# ── 쓰기·실행 ─────────────────────────────────────────────────────────────────

def _write(root: Path, rel: Path, text: str) -> None:
    """원자적 쓰기 — 같은 디렉토리 임시 파일 → replace."""
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, dest)


def run(root, *, project: str = "", only: str = "", now=None, fetch_page=None, runner=None,
        workers=None, mounted=None, log=print, redmine_base=None) -> int:
    """스냅샷을 쓴다. rc 0 = 모든 원천에 닿았다 · 1 = 하나라도 못 닿았다(파일은 그래도 쓴다)."""
    root = Path(root)
    runner = runner or _run
    fetch_page = fetch_page or _fetch_page_public
    workers = workers or _workers
    mounted = mounted or _mounted
    missed = False

    m = collect_master(root, runner)
    if m["error"]:
        missed = True
    meta = {"generated": kst_now(now), "head": m["head"], "head_error": m["error"]}
    mount = mounted() or {}

    if only in ("", "redmine"):
        # [중요] 인수인계서 근거라 AX 인프라 일감(`ax-cluster`)에 고정한다 — 마운트를 게임으로 바꿔도
        #       따라가지 않는다(#839 스펙). 다른 프로젝트는 `--project` 로만.
        rproj = project or DEFAULT_REDMINE_PROJECT
        try:
            base = redmine_base if redmine_base is not None else _redmine_base()
        except Exception:                                   # noqa: BLE001
            base = ""
        meta["redmine_base"] = base
        red = collect_redmine(rproj, fetch_page)
        text = render_redmine(red, rproj, meta)
        if red["ok"]:
            log(f"[ops_snapshot] redmine: 열린 {len(red['issues'])}건 (total_count {red['total']}) "
                f"· 아이디어 {meta.get('idea_count', 0)}")
        else:
            missed = True
            log(f"[ops_snapshot] redmine: {UNREACHED}: {red['error']}")
        _write(root, REDMINE_FILE, text)
        log(f"[ops_snapshot] 썼다: {REDMINE_FILE.as_posix()}")

    if only in ("", "ops"):
        services = collect_services(runner)
        for s in services:
            if s["error"]:
                missed = True
                log(f"[ops_snapshot] service {s['unit']}: {UNREACHED}: {s['error']}")
            else:
                log(f"[ops_snapshot] service {s['unit']}: {s['active']}")
        wk = {"project": mount.get("project") or "", "rows": [], "error": ""}
        if mount.get("error") or not wk["project"]:
            wk["error"] = mount.get("error") or "마운트된 프로젝트가 없다"
        elif not m["head"]:
            wk["error"] = "마스터 HEAD 를 몰라 대조할 수 없다"
        else:
            try:
                wk["rows"] = workers(wk["project"], m["head"])
            except Exception as e:                          # noqa: BLE001
                wk["error"] = _reason(e)
        if wk["error"]:
            missed = True
            log(f"[ops_snapshot] workers: {UNREACHED}: {wk['error']}")
        for w in wk["rows"]:
            if w.get("error"):
                missed = True
                log(f"[ops_snapshot] worker {w['host']}: {UNREACHED}: {w['error']}")
            else:
                log(f"[ops_snapshot] worker {w['host']}: {w['verdict']}")
        _write(root, OPS_FILE, render_ops(m, services, wk, meta))
        log(f"[ops_snapshot] 썼다: {OPS_FILE.as_posix()}")

    return 1 if missed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.ops_snapshot",
                                 description="열린 Redmine 일감·운영 상태 스냅샷을 docs/snapshots/ 에 쓴다 (#839)")
    ap.add_argument("--root", default=str(REPO_ROOT), help="스냅샷을 쓸 저장소 루트 (기본: 이 모듈의 저장소)")
    ap.add_argument("--project", default="", help="Redmine 프로젝트 식별자 (기본: ax-cluster — 마운트를 따르지 않는다)")
    ap.add_argument("--only", choices=("redmine", "ops"), default="", help="한쪽만 쓴다")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        ap.error("--root 가 디렉토리가 아니다")
    return run(root, project=args.project.strip(), only=args.only)


if __name__ == "__main__":
    sys.exit(main())
