"""수정 항목 검토·적용 흐름 — `.33` 쪽 결정론 부분 (`#630`, 사용자 요청 2026-09-16).

    py .ax/lib/axmaster/clientside/fix_flow.py list
    py .ax/lib/axmaster/clientside/fix_flow.py fetch R12       ① 내려받기 → .ax/fixes/R12/doc.md·doc.json
    py .ax/lib/axmaster/clientside/fix_flow.py check R12       ② 지금 origin/main 과 대조 → check.md·check.json
    py .ax/lib/axmaster/clientside/fix_flow.py worktree R12    ④ 적용 자리 — 옆 디렉토리 worktree · fix/R12
    py .ax/lib/axmaster/clientside/fix_flow.py diff R12        ⑤ 고친 것 확인 → diff.patch · 요지는 flow.log
    py .ax/lib/axmaster/clientside/fix_flow.py commit R12 --items R12-1,R12-3 --message "…"   ⑤ fix/R12 에만
    py .ax/lib/axmaster/clientside/fix_flow.py status R12-3 applied --branch fix/R12 --commit <sha> --note "…"

[중요] **판단은 여기서 하지 않는다** — 「합당한가」·「고칠까」는 세션과 사람이 한다(`ax-fix` 스킬).
이 파일은 사실만 모은다: 리뷰한 커밋이 main 에 들어갔나, 지적한 파일이 그 뒤 바뀌었나, 지적한 줄이
아직 있나. `hint` 는 읽을 순서를 정하는 단서일 뿐 판정이 아니다.

[중요] 단일 파일 · stdlib 만 — `client_mcp.py` 와 같은 제약(스크립트 모드 · 클라에 pip 없음).
큐 호출은 옆 파일 `client_mcp.py` 를 **경로로 로드**해 그 `queue_api` 를 쓴다 — 프로젝트 태그와
오류 문장이 한 벌이다.
[중요] **사람의 체크아웃은 건드리지 않는다** — 브랜치를 바꾸지 않고 옆 디렉토리에 worktree 만
만든다. 있는 worktree 는 재사용하고 리셋하지 않는다(사람이 거기서 고쳤을 수 있다).
[주의] 내용은 파일로 남기고 콘솔엔 요지만 찍는다 — 이 PC 콘솔은 CP949 다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FIXES_REL = Path(".ax/fixes")
BASE = "origin/main"
STATES = ("open", "accepted", "dismissed", "stale", "applied", "failed")
_SERIAL = re.compile(r"^\s*([RrPp])(\d+)(?:-(\d+))?\s*$")
_INT = re.compile(r"\d+")

HINT_LABEL = {
    "gone": "파일이 main 에 없다 — 해당 없음일 가능성이 크다",
    "unchanged": "리뷰 뒤 파일이 안 바뀌었다 — 지적이 그대로일 가능성이 크다",
    "line_present": "파일은 바뀌었지만 지적한 줄이 남아 있다",
    "line_missing": "지적한 줄이 사라졌다 — 이미 고쳐졌을 수 있다",
    "changed": "파일이 바뀌었다 — 읽어서 판단",
    "unknown": "대조하지 못했다 — 읽어서 판단",
}


class FlowError(RuntimeError):
    """사람에게 보고하고 멈출 사유. [중요] 실패를 우회하지 않는다 — 스킬은 이것을 보고 멈춘다."""


def _mcp():
    import importlib.util
    src = Path(__file__).with_name("client_mcp.py")
    spec = importlib.util.spec_from_file_location("ax_client_mcp_for_fix", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_serial(text: str) -> tuple:
    m = _SERIAL.match(text or "")
    if not m:
        raise FlowError(f"번호 형식이 아니다: {text!r} (예: R12 · P3 · R12-3)")
    return m.group(1).upper(), int(m.group(2)), (int(m.group(3)) if m.group(3) else None)


def doc_serial(text: str) -> str:
    kind, num, _ = parse_serial(text)
    return f"{kind}{num}"


def work_dir(root: Path, serial: str) -> Path:
    d = root / FIXES_REL / serial
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(root: Path, serial: str, msg: str) -> None:
    line = f"[fix] {serial} {msg}"
    print(line, flush=True)
    try:
        with open(work_dir(root, serial) / "flow.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except OSError:
        pass


def git(root: Path, *args: str, check: bool = False) -> tuple:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    except OSError as e:
        raise FlowError(f"git 을 실행하지 못했다: {e}") from e
    out = (p.stdout or b"").decode("utf-8", "replace")
    if check and p.returncode != 0:
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        raise FlowError(f"git {' '.join(args)} 실패 (rc={p.returncode}): {err[:300]}")
    return p.returncode, out


def _api(root: Path, api=None):
    return api or _mcp().queue_api(root)


def _call(fn, *a):
    """`client_mcp.ClientError` 를 FlowError 로 — 모듈을 경로로 로드해 클래스 비교가 안 된다."""
    try:
        return fn(*a)
    except FlowError:
        raise
    except Exception as e:                                   # noqa: BLE001
        if type(e).__name__ == "ClientError":
            raise FlowError(str(e)) from e
        raise


# ── ① 내려받기 ──────────────────────────────────────────────────────────────

def cmd_list(root: Path, *, api=None) -> dict:
    got = _call(_mcp().tool_list_fixes, _api(root, api))
    if not isinstance(got, dict) or not got.get("ok"):
        raise FlowError(f"목록을 받지 못했다: {(got or {}).get('reason') if isinstance(got, dict) else got}")
    for d in got.get("docs") or []:
        when = d.get("created") or d.get("week") or ""
        print(f"{d['serial']:>5} {d.get('kind', ''):<6} {when:<16} {d.get('author', ''):<12} "
              f"항목 {d.get('items', 0):>3} {d.get('severity')} {d.get('states')}")
    return got


def cmd_fetch(root: Path, serial: str, *, api=None) -> dict:
    s = doc_serial(serial)
    got = _call(_mcp().tool_get_fix, _api(root, api), s)
    if not isinstance(got, dict) or not got.get("ok"):
        reason = got.get("reason") if isinstance(got, dict) else str(got)
        log(root, s, f"내려받기 거절 — {reason}")
        raise FlowError(f"{s} 를 받지 못했다: {reason}")
    d = work_dir(root, s)
    (d / "doc.json").write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "doc.md").write_text(got.get("body") or "", encoding="utf-8")
    log(root, s, f"내려받기 — {got.get('kind')} · 항목 {got.get('items')}건 → "
                 f"{(d / 'doc.md').relative_to(root).as_posix()}")
    return got


# ── ② 지금 main 과 대조 ─────────────────────────────────────────────────────

def _first_int(text) -> int | None:
    m = _INT.search(str(text or ""))
    return int(m.group()) if m else None


def _clean_path(p) -> str:
    return str(p or "").strip().strip("`").strip().replace("\\", "/")


def _file_lines(root: Path, rev: str, path: str):
    rc, out = git(root, "show", f"{rev}:{path}")
    return out.splitlines() if rc == 0 else None


def check_review_item(root: Path, commit: str, item: dict, *, base: str = BASE,
                      have_commit: bool = True) -> dict:
    path = _clean_path(item.get("file"))
    line = _first_int(item.get("line"))
    r = {"id": item.get("id"), "file": path, "line": line}
    now_lines = _file_lines(root, base, path) if path else None
    r["exists_now"] = now_lines is not None
    if now_lines is None:
        r["hint"] = "gone"
        return r
    then_lines = _file_lines(root, commit, path) if have_commit else None
    if then_lines is None:
        r["hint"] = "unknown"
        r["why"] = "리뷰 커밋의 파일을 읽지 못했다"
        return r
    rc, _ = git(root, "diff", "--quiet", commit, base, "--", path)
    r["changed_since"] = rc != 0
    if line and 1 <= line <= len(then_lines):
        lo, hi = max(0, line - 3), min(len(then_lines), line + 2)
        r["then"] = "\n".join(f"{i + 1}: {then_lines[i]}" for i in range(lo, hi))
        target = then_lines[line - 1].strip()
        if target:
            r["now_lines"] = [i + 1 for i, text in enumerate(now_lines) if text.strip() == target][:5]
    if not r["changed_since"]:
        r["hint"] = "unchanged"
    elif "now_lines" not in r:
        r["hint"] = "changed"
    else:
        r["hint"] = "line_present" if r["now_lines"] else "line_missing"
    return r


def _cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _check_md(result: dict, doc: dict) -> str:
    by_id = {it.get("id"): it for it in doc.get("items_detail") or []}
    lines = [f"# {result['serial']} 대조 — {result['base']} @ {result['base_commit'][:12]}", ""]
    if result.get("kind") == "review":
        lines += [f"- 리뷰 커밋: `{result.get('review_commit', '')[:12]}` · "
                  f"이 PC 에 있음 {result.get('commit_known')} · main 에 들어감 {result.get('commit_in_main')}"]
    lines += [f"- 대조 시각: {result['checked_at']}",
              "- [주의] 단서는 판정이 아니다 — 합당한지는 코드를 읽고 사람과 정한다", "",
              "| 항목 | 파일:라인 | 단서 | 지금 줄 | 심각도 | 지적 | 권장 수정 |",
              "|---|---|---|---|---|---|---|"]
    for r in result["items"]:
        src = by_id.get(r.get("id")) or {}
        where = f"{r.get('file')}:{r.get('line') or '-'}"
        now = ",".join(str(n) for n in r.get("now_lines") or []) or "-"
        lines.append(f"| {_cell(r.get('id'))} | {_cell(where)} | {_cell(HINT_LABEL.get(r.get('hint'), r.get('hint')))} "
                     f"| {now} | {_cell(src.get('severity'))} | {_cell(src.get('description'))} "
                     f"| {_cell(src.get('recommendation'))} |")
    if result.get("kind") == "plan":
        lines += ["", "플랜 본문은 `doc.md` 에 있다 — 대상 파일의 지금 코드를 읽고 개선안이 여전히 맞는지 본다."]
    return "\n".join(lines) + "\n"


def cmd_check(root: Path, serial: str, *, fetch: bool = True, base: str = BASE, api=None) -> dict:
    s = doc_serial(serial)
    d = work_dir(root, s)
    p = d / "doc.json"
    if not p.is_file():
        cmd_fetch(root, s, api=api)
    doc = json.loads(p.read_text(encoding="utf-8"))
    if fetch:
        rc, _ = git(root, "fetch", "--quiet", "origin", "main")
        log(root, s, f"git fetch origin main rc={rc}")
        if rc != 0:
            # [중요] 낡은 main 으로 대조하면 「이미 고쳐진 것」을 「아직 문제」로 읽는다
            raise FlowError("git fetch origin main 실패 — 네트워크·원격을 확인한다 (낡은 main 으로 대조하지 않는다)")
    _, head = git(root, "rev-parse", base, check=True)
    result = {"serial": s, "kind": doc.get("kind"), "base": base, "base_commit": head.strip(),
              "checked_at": datetime.now().isoformat(timespec="seconds"), "items": []}
    if doc.get("kind") == "review":
        commit = doc.get("commit_full") or ""
        have = bool(commit) and git(root, "cat-file", "-e", f"{commit}^{{commit}}")[0] == 0
        result.update(review_commit=commit, commit_known=have,
                      commit_in_main=have and git(root, "merge-base", "--is-ancestor",
                                                  commit, base)[0] == 0)
        for it in doc.get("items_detail") or []:
            result["items"].append(check_review_item(root, commit, it, base=base, have_commit=have))
    else:
        for t in [_clean_path(x) for x in str(doc.get("target_file") or "").split(",") if x.strip()]:
            exists = git(root, "cat-file", "-e", f"{base}:{t}")[0] == 0
            _, last = git(root, "log", "-1", "--format=%cs %h", base, "--", t)
            result["items"].append({"id": s, "file": t, "exists_now": exists,
                                    "last_change": last.strip(),
                                    "hint": "changed" if exists else "gone"})
    (d / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "check.md").write_text(_check_md(result, doc), encoding="utf-8")
    counts: dict = {}
    for r in result["items"]:
        counts[r["hint"]] = counts.get(r["hint"], 0) + 1
    log(root, s, f"대조 — {base}@{result['base_commit'][:8]} · {counts} → "
                 f"{(d / 'check.md').relative_to(root).as_posix()}")
    return result


# ── ④ 적용 자리 ─────────────────────────────────────────────────────────────

def _worktree_path(root: Path, s: str) -> Path:
    return (root.parent / f"ax-fix-{s}").resolve()


def _is_worktree(root: Path, path: Path) -> bool:
    _, listing = git(root, "worktree", "list", "--porcelain")
    known = {Path(l[len("worktree "):].strip()).resolve().as_posix().lower()
             for l in listing.splitlines() if l.startswith("worktree ")}
    return path.as_posix().lower() in known


def cmd_worktree(root: Path, serial: str, *, base: str = BASE) -> dict:
    s = doc_serial(serial)
    branch = f"fix/{s}"
    path = _worktree_path(root, s)
    if _is_worktree(root, path):
        log(root, s, f"worktree 재사용 — {path.as_posix()} (리셋하지 않는다)")
        return {"path": str(path), "branch": branch, "reused": True}
    if path.exists():
        raise FlowError(f"{path} 가 이미 있는데 이 저장소의 worktree 가 아니다 — 덮지 않는다")
    has_branch = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
    if has_branch:
        git(root, "worktree", "add", str(path), branch, check=True)
    else:
        git(root, "worktree", "add", "-b", branch, str(path), base, check=True)
    log(root, s, f"worktree {'기존 브랜치' if has_branch else base + ' 에서 새 브랜치'} {branch} → {path.as_posix()}")
    return {"path": str(path), "branch": branch, "reused": False}


# ── ⑤ 확인·커밋 ─────────────────────────────────────────────────────────────
#    [중요] 서브 에이전트의 「끝났다」를 믿지 않는다 — `diff` 가 실제 변경을 파일과 로그로 남기고,
#    `commit` 이 해시·항목을 로그에 남긴다. 둘 다 없던 때는 「고쳤는데 기록 전에 멈춘」 자리가
#    어디에도 안 보였다(2026-09-16 로그 점검).

def _existing_worktree(root: Path, s: str) -> Path:
    path = _worktree_path(root, s)
    if not _is_worktree(root, path):
        raise FlowError(f"{s} 의 worktree 가 없다 — 먼저 `worktree {s}`")
    return path


def cmd_diff(root: Path, serial: str) -> dict:
    s = doc_serial(serial)
    wt = _existing_worktree(root, s)
    git(wt, "add", "-N", ".")                 # 새 파일도 diff 에 보이게 — 내용은 스테이징하지 않는다
    _, names = git(wt, "diff", "--name-only")
    files = [n for n in names.splitlines() if n.strip()]
    _, short = git(wt, "diff", "--shortstat")
    _, patch = git(wt, "diff")
    out = work_dir(root, s) / "diff.patch"
    out.write_text(patch, encoding="utf-8")
    log(root, s, f"diff — 파일 {len(files)}개 · {short.strip() or '변경 없음'} → "
                 f"{out.relative_to(root).as_posix()}"
                 + (f" ({', '.join(files[:5])})" if files else ""))
    return {"files": files, "shortstat": short.strip(), "patch": str(out)}


def cmd_commit(root: Path, serial: str, items: list, message: str = "") -> dict:
    """`fix/<번호>` 에만 커밋한다 — 스킬이 사용자에게 물은 뒤에만 부른다. push 하지 않는다."""
    s = doc_serial(serial)
    ids = []
    for it in items:
        kind, num, row = parse_serial(it)
        if f"{kind}{num}" != s:
            raise FlowError(f"{it} 는 {s} 의 항목이 아니다 — 한 번에 한 번호만 커밋한다")
        if kind == "R" and row is None:
            raise FlowError(f"리뷰 항목은 행 번호까지 준다 (예: {s}-1)")
        iid = f"{kind}{num}" + (f"-{row}" if row else "")
        if iid not in ids:
            ids.append(iid)
    if not ids:
        raise FlowError(f"커밋할 항목이 없다 — --items {s}-1,{s}-3")
    wt = _existing_worktree(root, s)
    _, head = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    if head.strip() != f"fix/{s}":
        raise FlowError(f"worktree 가 fix/{s} 가 아니다 ({head.strip()}) — 커밋하지 않는다")
    _, porcelain = git(wt, "status", "--porcelain")
    if not porcelain.strip():
        log(root, s, "커밋 거절 — 변경이 없다")
        raise FlowError("커밋할 변경이 없다")
    git(wt, "add", "-A", check=True)
    text = (message or "").strip()
    subject = text.splitlines()[0] if text else "리뷰 지적 수정"
    git(wt, "commit", "-q", "-m", f"fix({','.join(ids)}): {subject}",
        "-m", f"자동 리뷰·플랜 {s} — ax-fix", check=True)
    _, sha = git(wt, "rev-parse", "HEAD")
    _, stat = git(wt, "show", "--shortstat", "--format=", "HEAD")
    sha = sha.strip()
    log(root, s, f"커밋 {sha[:12]} on fix/{s} · 항목 {','.join(ids)} · {stat.strip()}")
    return {"commit": sha, "branch": f"fix/{s}", "items": ids}


# ── ⑥ 기록 ──────────────────────────────────────────────────────────────────

def cmd_status(root: Path, item: str, state: str, *, note: str = "", branch: str = "",
               commit: str = "", by: str = "ax-fix", api=None) -> dict:
    parse_serial(item)
    if state not in STATES:
        raise FlowError(f"상태는 {' · '.join(STATES)} 중 하나다 (받은 값 {state!r})")
    got = _call(_mcp().tool_update_fix_status, _api(root, api),
                {"item": item, "state": state, "note": note, "branch": branch,
                 "commit": commit, "by": by})
    ok = isinstance(got, dict) and got.get("ok")
    log(root, doc_serial(item), f"상태 {item} → {state} · "
                                f"{'기록됨' if ok else (got or {}).get('reason')}")
    if not ok:
        raise FlowError(f"상태를 기록하지 못했다: {(got or {}).get('reason')}")
    return got


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                    # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="fix_flow", description="수정 항목 검토·적용 (#630)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("fetch", "check", "worktree", "diff"):
        sp = sub.add_parser(name)
        sp.add_argument("serial")
        if name == "check":
            sp.add_argument("--no-fetch", action="store_true")
    sp = sub.add_parser("commit")
    sp.add_argument("serial")
    sp.add_argument("--items", required=True, help="R12-1,R12-3")
    sp.add_argument("--message", default="")
    sp = sub.add_parser("status")
    sp.add_argument("item")
    sp.add_argument("state", choices=STATES)
    for opt in ("--note", "--branch", "--commit", "--by"):
        sp.add_argument(opt, default="")
    args = ap.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        if args.cmd == "list":
            cmd_list(root)
        elif args.cmd == "fetch":
            cmd_fetch(root, args.serial)
        elif args.cmd == "check":
            cmd_check(root, args.serial, fetch=not args.no_fetch)
        elif args.cmd == "worktree":
            got = cmd_worktree(root, args.serial)
            print(json.dumps(got, ensure_ascii=False))
        elif args.cmd == "diff":
            cmd_diff(root, args.serial)
        elif args.cmd == "commit":
            got = cmd_commit(root, args.serial,
                             [x for x in args.items.split(",") if x.strip()], args.message)
            print(json.dumps(got, ensure_ascii=False))
        else:
            cmd_status(root, args.item, args.state, note=args.note, branch=args.branch,
                       commit=args.commit, by=args.by or "ax-fix")
    except FlowError as e:
        print(f"[fix] [실패] {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
