"""수정 항목 검토·적용 흐름 — `.33` 쪽 결정론 부분 (`#630`, 사용자 요청 2026-09-16).

    py .ax/lib/axmaster/clientside/fix_flow.py list
    py .ax/lib/axmaster/clientside/fix_flow.py fetch R12       ① 내려받기 → .ax/fixes/R12/doc.md·doc.json
    py .ax/lib/axmaster/clientside/fix_flow.py check R12       ② 지금 origin/main 과 대조 → check.md·check.json
    py .ax/lib/axmaster/clientside/fix_flow.py prepare R12      ④ 적용 자리 — 기본은 **이 체크아웃**에 fix/R12
    py .ax/lib/axmaster/clientside/fix_flow.py prepare R12 --mode worktree   사람이 고치던 중일 때만 옆으로
    py .ax/lib/axmaster/clientside/fix_flow.py diff R12        ⑤ 고친 것 확인 → diff.patch · 요지는 flow.log
    py .ax/lib/axmaster/clientside/fix_flow.py commit R12 --items R12-1,R12-3 --message "…"   ⑤ fix/R12 에만
    py .ax/lib/axmaster/clientside/fix_flow.py release R12     ⑥ 브랜치 점유를 푼다 (worktree 모드)
    py .ax/lib/axmaster/clientside/fix_flow.py status R12-3 applied --branch fix/R12 --commit <sha> --note "…"

[중요] **판단은 여기서 하지 않는다** — 「합당한가」·「고칠까」는 세션과 사람이 한다(`ax-fix` 스킬).
이 파일은 사실만 모은다: 리뷰한 커밋이 main 에 들어갔나, 지적한 파일이 그 뒤 바뀌었나, 지적한 줄이
아직 있나. `hint` 는 읽을 순서를 정하는 단서일 뿐 판정이 아니다.

[중요] 단일 파일 · stdlib 만 — `client_mcp.py` 와 같은 제약(스크립트 모드 · 클라에 pip 없음).
큐 호출은 옆 파일 `client_mcp.py` 를 **경로로 로드**해 그 `queue_api` 를 쓴다 — 프로젝트 태그와
오류 문장이 한 벌이다.
🔴 [중요] **적용 자리의 기본은 사람의 체크아웃이다** (`#660`, 사용자 결정 2026-09-22).
옆 worktree 를 기본으로 뒀더니 ⑴ 수정이 소스트리에 안 보였고 ⑵ git 이 같은 브랜치를 두 worktree 에
못 붙여 사람이 그 브랜치를 자기 폴더에서 열 수도 없었고 ⑶ worktree 엔 `Intermediate`/`Binaries` 가
없어 첫 빌드가 풀빌드라 확인이 실질적으로 불가능했다. 그래서 **worktree 는 피난처지 기본이 아니다.**
[중요] **더러운 체크아웃에는 절대 붙이지 않는다** — 깨끗하지 않으면 거절하고 갈래를 말한다
(미커밋 `.uasset` 작업을 날리는 것이 이 격리가 원래 막으려던 사고다).
있는 worktree 는 재사용하고 리셋하지 않는다(사람이 거기서 고쳤을 수 있다).
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
# 🔴 [중요] **스테이징에서 `.ax/` 를 뺀다** — 이 도구 자신의 산출물이다(`doc`·`check`·`diff`·로그).
# worktree 모드에선 `.ax/` 가 사람 체크아웃에만 있어 안 보였지만, inplace 모드에서는 같은 트리라
# `add -A` 가 **사람 저장소에 도구 산출물을 커밋**한다 (실측 2026-09-22, 테스트가 잡았다).
AX_PATHSPEC = (".", ":(exclude).ax", ":(exclude).ax/*")
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


def _current_branch(root: Path) -> str:
    _, head = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return head.strip()


def _dirty(root: Path) -> str:
    """빈 문자열이면 깨끗하다 — 추적 안 되는 파일도 더러운 것으로 센다(사람의 작업일 수 있다).

    [중요] **`.ax/` 는 빼고 센다** — 이 도구 자신의 산출물이다(`fetch`·`check` 가 거기에 쓴다).
    실측(2026-09-22): 요청자 체크아웃은 `.git/info/exclude` 로 이미 빼고 있어 안 보이지만,
    그 배선이 어긋난 체크아웃에서는 **`prepare` 가 영원히 거절**된다 — 사람 작업이 하나도
    없는데도. 판정을 배선에 기대지 않고 여기서 집행한다.
    """
    _, porcelain = git(root, "status", "--porcelain")
    kept = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        path = path.split(" -> ")[-1].strip().strip('"')     # rename 은 도착지로 본다
        if path == FIXES_REL.parts[0] or path.startswith(FIXES_REL.parts[0] + "/"):
            continue
        kept.append(line)
    return "\n".join(kept)


def cmd_prepare(root: Path, serial: str, *, mode: str = "auto", base: str = BASE) -> dict:
    """④ 적용 자리를 만든다. `mode` 는 auto(기본) · inplace · worktree.

    auto 는 **깨끗하면 inplace, 더러우면 거절**이다 — 자동으로 worktree 로 도망가지 않는다.
    도망가면 사람은 자기 폴더에서 아무것도 못 보는데 왜 그런지도 모른다(`#660` 이 그 사고다).
    """
    if mode not in ("auto", "inplace", "worktree"):
        raise FlowError(f"모르는 mode: {mode!r} (auto · inplace · worktree)")
    s = doc_serial(serial)
    if mode in ("auto", "inplace"):
        # [중요] 재사용 판정이 먼저다 — 이미 그 브랜치면 **갈아탈 것이 없으니** 더러움은 무관하다.
        if _current_branch(root) == f"fix/{s}":
            return _prepare_inplace(root, s, base=base)
        dirty = _dirty(root)
        if not dirty:
            return _prepare_inplace(root, s, base=base)
        head = dirty.splitlines()
        raise FlowError(
            f"체크아웃에 커밋하지 않은 변경 {len(head)}건이 있다 — 여기에 브랜치를 붙이지 않는다. "
            f"커밋하거나 stash 한 뒤 다시 부르고, 작업을 유지해야 하면 "
            f"`prepare {s} --mode worktree` 로 옆에서 고친다. "
            f"({' · '.join(x.strip() for x in head[:3])}"
            + (" …" if len(head) > 3 else "") + ")")
    return _prepare_worktree(root, s, base=base)


def _prepare_inplace(root: Path, s: str, *, base: str = BASE) -> dict:
    """[중요] 사람의 체크아웃에 `fix/<번호>` 를 붙인다 — **깨끗할 때만 불린다.**"""
    branch = f"fix/{s}"
    cur = _current_branch(root)
    if cur == branch:
        log(root, s, f"이 체크아웃이 이미 {branch} 다 — 그대로 쓴다 ({root.as_posix()})")
        return {"path": str(root), "branch": branch, "mode": "inplace",
                "previous_branch": cur, "reused": True}
    wt = _worktree_path(root, s)
    if _is_worktree(root, wt):
        raise FlowError(
            f"{branch} 를 옆 worktree({wt.as_posix()})가 점유하고 있다 — git 은 같은 브랜치를 "
            f"두 작업 폴더에 못 붙인다. 거기 것을 커밋한 뒤 `release {s}` 로 점유를 풀면 "
            f"이 폴더에서 열 수 있다.")
    has_branch = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
    if has_branch:
        git(root, "checkout", "-q", branch, check=True)
    else:
        git(root, "checkout", "-q", "-b", branch, base, check=True)
    log(root, s, f"[중요] 이 체크아웃의 브랜치를 {cur} → {branch} 로 바꿨다 "
                 f"({'기존 브랜치' if has_branch else base + ' 에서 새로'} · {root.as_posix()}) "
                 f"— 돌아갈 곳: `release {s} --to {cur}`")
    return {"path": str(root), "branch": branch, "mode": "inplace",
            "previous_branch": cur, "reused": False}


def _prepare_worktree(root: Path, s: str, *, base: str = BASE) -> dict:
    branch = f"fix/{s}"
    path = _worktree_path(root, s)
    if _is_worktree(root, path):
        log(root, s, f"worktree 재사용 — {path.as_posix()} (리셋하지 않는다)")
        return {"path": str(path), "branch": branch, "mode": "worktree", "reused": True}
    if path.exists():
        raise FlowError(f"{path} 가 이미 있는데 이 저장소의 worktree 가 아니다 — 덮지 않는다")
    has_branch = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
    if has_branch:
        git(root, "worktree", "add", str(path), branch, check=True)
    else:
        git(root, "worktree", "add", "-b", branch, str(path), base, check=True)
    log(root, s, f"worktree {'기존 브랜치' if has_branch else base + ' 에서 새 브랜치'} {branch} → {path.as_posix()}")
    return {"path": str(path), "branch": branch, "mode": "worktree", "reused": False}


# ── ⑤ 확인·커밋 ─────────────────────────────────────────────────────────────
#    [중요] 서브 에이전트의 「끝났다」를 믿지 않는다 — `diff` 가 실제 변경을 파일과 로그로 남기고,
#    `commit` 이 해시·항목을 로그에 남긴다. 둘 다 없던 때는 「고쳤는데 기록 전에 멈춘」 자리가
#    어디에도 안 보였다(2026-09-16 로그 점검).

def _fix_tree(root: Path, s: str) -> Path:
    """고친 자리 — 옆 worktree 가 있으면 거기, 없으면 이 체크아웃(inplace)."""
    path = _worktree_path(root, s)
    if _is_worktree(root, path):
        return path
    cur = _current_branch(root)
    if cur == f"fix/{s}":
        return root
    raise FlowError(f"{s} 의 적용 자리가 없다 — 먼저 `prepare {s}` "
                    f"(이 체크아웃은 {cur} 에 있고 옆 worktree 도 없다)")


def cmd_diff(root: Path, serial: str) -> dict:
    s = doc_serial(serial)
    wt = _fix_tree(root, s)
    # 새 파일도 diff 에 보이게 — 내용은 스테이징하지 않는다.
    # [주의] inplace 모드면 이것이 **사람 트리의 인덱스**를 건드린다(intent-to-add). `prepare` 가
    #        깨끗한 트리에서만 붙었으므로 여기 잡히는 새 파일은 이 수정의 산물이다.
    git(wt, "add", "-N", "--", *AX_PATHSPEC)
    _, names = git(wt, "diff", "--name-only")
    files = [n for n in names.splitlines() if n.strip()]
    _, short = git(wt, "diff", "--shortstat")
    _, patch = git(wt, "diff")
    out = work_dir(root, s) / "diff.patch"
    # [중요] **바이트로 쓴다** — 텍스트 모드는 윈도우에서 줄바꿈을 CRLF 로 번역하는데
    # 저장소 blob 은 LF 라 그 패치를 `git apply` 가 거절한다 (`#660`, 실측 2026-09-22).
    # [주의] 리눅스 유닛 테스트로는 안 잡힌다 — 번역은 이 파일이 도는 윈도우에서만 일어난다.
    out.write_bytes(patch.encode("utf-8"))
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
    wt = _fix_tree(root, s)
    _, head = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    if head.strip() != f"fix/{s}":
        raise FlowError(f"적용 자리가 fix/{s} 가 아니다 ({head.strip()}) — 커밋하지 않는다")
    porcelain = _dirty(wt)
    if not porcelain.strip():
        log(root, s, "커밋 거절 — 변경이 없다")
        raise FlowError("커밋할 변경이 없다")
    git(wt, "add", "-A", "--", *AX_PATHSPEC, check=True)
    text = (message or "").strip()
    subject = text.splitlines()[0] if text else "리뷰 지적 수정"
    git(wt, "commit", "-q", "-m", f"fix({','.join(ids)}): {subject}",
        "-m", f"자동 리뷰·플랜 {s} — ax-fix", check=True)
    _, sha = git(wt, "rev-parse", "HEAD")
    _, stat = git(wt, "show", "--shortstat", "--format=", "HEAD")
    sha = sha.strip()
    log(root, s, f"커밋 {sha[:12]} on fix/{s} · 항목 {','.join(ids)} · {stat.strip()}")
    return {"commit": sha, "branch": f"fix/{s}", "items": ids}


def cmd_release(root: Path, serial: str, *, to: str = "") -> dict:
    """⑥ 적용 자리를 푼다 — 사람이 자기 폴더에서 그 브랜치를 열 수 있게.

    [중요] git 은 같은 브랜치를 두 작업 폴더에 못 붙인다. worktree 가 살아 있는 한 사람은
    소스트리에서 `fix/<번호>` 를 체크아웃할 수 없고, 그 거절이 `#660` 사고의 한 축이었다.
    그래서 worktree 모드의 마지막 걸음은 **점유를 푸는 것**이다.

    [주의] **커밋하지 않은 변경이 있으면 거절한다** — worktree 를 지우면 그 변경이 사라진다.
    """
    s = doc_serial(serial)
    path = _worktree_path(root, s)
    branch = f"fix/{s}"
    if _is_worktree(root, path):
        dirty = _dirty(path)
        if dirty:
            raise FlowError(
                f"worktree 에 커밋하지 않은 변경 {len(dirty.splitlines())}건이 있다 — 지우면 "
                f"사라진다. 먼저 `commit {s} --items …` 하고 다시 부른다.")
        git(root, "worktree", "remove", str(path), check=True)
        log(root, s, f"worktree 제거 — {path.as_posix()} · {branch} 점유가 풀렸다 "
                     f"(이제 이 체크아웃에서 열 수 있다)")
        return {"mode": "worktree", "branch": branch, "removed": str(path)}

    cur = _current_branch(root)
    if not to:
        log(root, s, f"풀 worktree 가 없다 — 이 체크아웃이 적용 자리다 (지금 {cur})")
        return {"mode": "inplace", "branch": cur, "removed": None}
    dirty = _dirty(root)
    if dirty:
        raise FlowError(f"체크아웃에 커밋하지 않은 변경 {len(dirty.splitlines())}건이 있다 — "
                        f"{to} 로 옮기지 않는다")
    git(root, "checkout", "-q", to, check=True)
    log(root, s, f"이 체크아웃을 {cur} → {to} 로 되돌렸다")
    return {"mode": "inplace", "branch": to, "previous_branch": cur, "removed": None}


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
    for name in ("fetch", "check", "diff"):
        sp = sub.add_parser(name)
        sp.add_argument("serial")
        if name == "check":
            sp.add_argument("--no-fetch", action="store_true")
    # [중요] 옛 이름 `worktree` 는 **격리를 뜻한 채로** 남긴다 — 이름이 동작을 말해야 한다.
    #        새 기본(`prepare`)은 사람 체크아웃이다 (`#660`).
    sp = sub.add_parser("prepare", aliases=["worktree"])
    sp.add_argument("serial")
    sp.add_argument("--mode", choices=("auto", "inplace", "worktree"), default="")
    sp = sub.add_parser("release")
    sp.add_argument("serial")
    sp.add_argument("--to", default="", help="inplace 였을 때 돌아갈 브랜치 (예: main)")
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
        elif args.cmd in ("prepare", "worktree"):
            mode = args.mode or ("worktree" if args.cmd == "worktree" else "auto")
            got = cmd_prepare(root, args.serial, mode=mode)
            print(json.dumps(got, ensure_ascii=False))
        elif args.cmd == "release":
            got = cmd_release(root, args.serial, to=args.to)
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
