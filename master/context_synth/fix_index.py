"""수정 항목 색인 — 자동 리뷰·주간 플랜에 일련번호(`R12` · `P3`)를 붙이고 항목별 결정을 기록한다.

원전에 없던 층이다 (사용자 요청 2026-09-16). 원전의 원칙은 *"리뷰/플랜은 제안이지 지시가
아님 — 수용 여부는 개발자가 결정"* 이었고, 개발자가 직접 고친 뒤 `code-validator` 가 플랜을
`acted`, `review-consultant` 가 `dismissed` 로 적었다. 여기서는 그 결정을 **번호로 부를 수
있게** 한다 — `.33` 이 *"R12 검토해볼까"* 로 문서를 받아 가고, 결정은 이 색인에 쌓인다.

    번호     리뷰 = `R<n>` (커밋 하나 = 리뷰 하나) · 플랜 = `P<n>` (플랜 MD 하나)
    항목     리뷰의 표 한 행 = `R12-3` · 플랜은 문서 전체가 한 항목 = `P3`
    상태     open(기록 없음) · accepted · dismissed · stale · applied · failed

[중요] **번호는 경로가 아니라 커밋에 묶는다.** `plan_archive` 가 플랜에 반영된 리뷰를
`reviews/<작성자>/_archive/<주차>/` 로 **옮긴다** — 경로로 번호를 매기면 옮기는 순간 번호가
바뀐다. 레드마인 `#N` 과 헷갈리지 않게 접두를 붙였다(원전의 *"리뷰 #4"* 는 레드마인 번호였다).
[중요] **깨진 색인을 빈 것으로 덮지 않는다** — 덮으면 번호가 처음부터 다시 매겨져 사람이 부른
`R12` 가 다른 문서를 가리킨다. 못 읽으면 `FixIndexError` 로 멈춘다.
[주의] 쓰는 쪽이 여럿이다(색인기·배치·8101·8103) — 쓰기는 전부 `fixes/.lock` 을 잡는다.

실행: .venv/bin/python -m master.context_synth.fix_index sweep|list|show <번호>|set <항목> <상태> [메모]
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .review_collector import parse_review_reports

FIXES_DIRNAME = "fixes"
INDEX_NAME = "index.json"
REVIEWS_DIRNAME = "reviews"
PLANS_DIRNAME = "plans"
SCHEMA = 1

STATES = ("open", "accepted", "dismissed", "stale", "applied", "failed")
# 플랜 MD frontmatter 의 `status` — 원전 값(pending/acted/dismissed)을 그대로 쓴다.
# accepted·stale·failed 는 아직 결론이 아니라 frontmatter 를 건드리지 않는다.
PLAN_STATUS_FOR = {"applied": "acted", "dismissed": "dismissed", "open": "pending"}
NOTE_MAX = 2000

_ID = re.compile(r"^\s*([RrPp])(\d+)(?:-(\d+))?\s*$")
_COMMIT = re.compile(r"커밋:\s*`([0-9a-f]{7,40})`")
_AUTHOR = re.compile(r"^- 작성자:\s*(.+)$", re.M)
_CREATED = re.compile(r"^- 생성:\s*(.+)$", re.M)
_FILES = re.compile(r"^- 파일:\s*(\d+)", re.M)
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})_([0-9a-f]{7,40})$")


class FixIndexError(Exception):
    """색인을 읽거나 쓸 수 없다. [주의] 메시지에 절대 경로를 싣지 않는다 — 8103 이 무인증이다."""


def index_path(root) -> Path:
    return Path(root) / FIXES_DIRNAME / INDEX_NAME


def parse_id(text: str) -> tuple:
    """`R12-3` → `("R", 12, 3)` · `P3` → `("P", 3, None)`. 형식이 아니면 `None`."""
    m = _ID.match(text or "")
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), (int(m.group(3)) if m.group(3) else None)


def serial_for_commit(root, commit: str) -> str:
    """이 커밋의 리뷰 번호. 없으면 빈 문자열 — 색인기 저널이 「리뷰 1 (R35)」로 찍는 재료다."""
    if not commit:
        return ""
    for serial, d in load(root)["docs"].items():
        c = d.get("commit") or ""
        if d.get("kind") == "review" and c and (c.startswith(commit) or commit.startswith(c)):
            return serial
    return ""


def _empty() -> dict:
    return {"schema": SCHEMA, "next": {"R": 1, "P": 1}, "docs": {}, "status": {}}


def load(root) -> dict:
    p = index_path(root)
    if not p.is_file():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise FixIndexError(f"수정 항목 색인을 읽지 못했다 ({p.name}: {type(e).__name__})") from e
    if not isinstance(data, dict) or not isinstance(data.get("docs"), dict):
        raise FixIndexError(f"수정 항목 색인 형식이 아니다 ({p.name})")
    out = _empty()
    out.update(data)
    out["next"] = {**_empty()["next"], **(data.get("next") or {})}
    if not isinstance(out.get("status"), dict):
        out["status"] = {}
    return out


def _save(root, data: dict) -> None:
    p = index_path(root)
    tmp = p.with_name(INDEX_NAME + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, p)


@contextmanager
def _locked(root):
    d = Path(root) / FIXES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ── 원천 훑기 ────────────────────────────────────────────────────────────────

def _review_files(root: Path) -> list:
    """작성자 디렉토리의 리뷰 + `_archive/<주차>/` 로 옮겨진 리뷰. `_` 접두 파일은 리뷰가 아니다."""
    base = root / REVIEWS_DIRNAME
    if not base.is_dir():
        return []
    out = []
    for author in base.iterdir():
        if not author.is_dir() or author.name.startswith("_"):
            continue
        out.extend(f for f in author.glob("*.md") if not f.name.startswith("_"))
        out.extend(f for f in author.glob("_archive/*/*.md") if not f.name.startswith("_"))
    # 파일명이 생성 시각으로 시작하므로 이름순 = 시간순 (작성자 무관)
    return sorted(out, key=lambda f: (f.name, f.as_posix()))


def _review_head(f: Path) -> dict:
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    stamp = _STAMP.match(f.stem)
    m = _COMMIT.search(text)
    commit = m.group(1) if m else (stamp.group(4) if stamp else "")
    c = _CREATED.search(text)
    created = (c.group(1).strip() if c else
               f"{stamp.group(1)} {stamp.group(2)}:{stamp.group(3)}" if stamp else "")
    n = _FILES.search(text)
    return {"commit": commit, "created": created, "files": int(n.group(1)) if n else 0}


def _plan_files(root: Path) -> list:
    """`plans/<작성자>/<주차>/*.md` — `_summary.md`·`_index.md` 는 플랜이 아니다."""
    base = root / PLANS_DIRNAME
    if not base.is_dir():
        return []
    out = [f for f in base.glob("*/*/*.md")
           if not f.name.startswith("_") and not f.parent.parent.name.startswith("_")]
    return sorted(out, key=lambda f: (f.parent.name, f.parent.parent.name, f.name))


def _plan_front(f: Path) -> tuple:
    from .plan_register import _parse_plan_frontmatter
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    return _parse_plan_frontmatter(text)


def _find_commit(by_commit: dict, commit: str) -> str:
    """헤더가 없어 파일명의 8자만 아는 리뷰도 같은 커밋으로 묶는다."""
    if commit in by_commit:
        return by_commit[commit]
    for full, serial in by_commit.items():
        if full.startswith(commit) or commit.startswith(full):
            return serial
    return ""


def sweep(root, *, logf=None, now: datetime | None = None) -> dict:
    """번호가 없는 리뷰·플랜에 번호를 준다. 여러 번 불러도 같은 결과다(멱등).

    옮겨진 리뷰는 경로만 고치고, 사라진 문서(아카이브 4주 보관 뒤 삭제)는 `missing` 으로
    남긴다 — 번호를 지우면 그 번호에 쌓인 결정이 고아가 된다.
    """
    log = logf or (lambda m: None)
    root = Path(root)
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    with _locked(root):
        data = load(root)
        docs = data["docs"]
        by_commit = {d["commit"]: s for s, d in docs.items()
                     if d.get("kind") == "review" and d.get("commit")}
        by_plan = {d["file"]: s for s, d in docs.items()
                   if d.get("kind") == "plan" and d.get("file")}
        assigned, moved, seen, no_commit = [], 0, set(), 0

        for f in _review_files(root):
            head = _review_head(f)
            if not head["commit"]:
                no_commit += 1
                continue
            rel = f.relative_to(root).as_posix()
            serial = _find_commit(by_commit, head["commit"])
            if not serial:
                serial = f"R{data['next']['R']}"
                data["next"]["R"] += 1
                docs[serial] = {"kind": "review", "commit": head["commit"],
                                "author": rel.split("/")[1], "created": head["created"],
                                "files": head["files"], "file": rel, "assigned_at": stamp}
                by_commit[head["commit"]] = serial
                assigned.append(serial)
            elif serial not in seen and docs[serial].get("file") != rel:
                docs[serial]["file"] = rel
                moved += 1
            seen.add(serial)

        for f in _plan_files(root):
            rel = f.relative_to(root).as_posix()
            serial = by_plan.get(rel)
            if not serial:
                fm, _ = _plan_front(f)
                if fm.get("type") != "improvement_plan":
                    continue
                serial = f"P{data['next']['P']}"
                data["next"]["P"] += 1
                docs[serial] = {"kind": "plan", "author": f.parent.parent.name,
                                "week": f.parent.name, "file": rel, "assigned_at": stamp}
                by_plan[rel] = serial
                assigned.append(serial)
            seen.add(serial)

        missing = 0
        changed = bool(assigned or moved)
        for serial, d in docs.items():
            gone = serial not in seen
            if gone != bool(d.get("missing")):
                changed = True
                if gone:
                    d["missing"] = True
                else:
                    d.pop("missing", None)
            missing += gone
        if changed:
            _save(root, data)

    if assigned:
        log(f"[fix] 번호 부여 {len(assigned)}건: {', '.join(assigned[:20])}"
            + (" …" if len(assigned) > 20 else ""))
    if moved:
        log(f"[fix] 옮겨진 리뷰 경로 갱신 {moved}건")
    if no_commit:
        log(f"[fix] [주의] 커밋을 알 수 없는 리뷰 {no_commit}건 — 번호를 주지 않았다")
    return {"assigned": assigned, "moved": moved, "missing": missing,
            "no_commit": no_commit, "total": len(docs)}


# ── 읽기 ─────────────────────────────────────────────────────────────────────

def _review_items(root: Path, doc: dict, serial: str, cache: dict) -> list:
    f = root / doc.get("file", "")
    if not f.is_file():
        return []
    key = f.parent.as_posix()
    if key not in cache:
        by_file: dict = {}
        for i in parse_review_reports(f.parent, "0000-00-00"):
            by_file.setdefault(i.source_review, []).append(i)
        cache[key] = by_file
    out = []
    for n, i in enumerate(cache[key].get(f.name, []), 1):
        out.append({"id": f"{serial}-{n}", "no": n, "category": i.category,
                    "severity": i.severity, "file": i.file, "line": i.line,
                    "description": i.description, "recommendation": i.recommendation,
                    "module": i.module})
    return out


def _summary(root: Path, data: dict, serial: str, cache: dict) -> tuple:
    """(요약, 항목 목록). 요약에는 **본문·소스 경로를 싣지 않는다** — 8103 에 그대로 나간다."""
    d = data["docs"][serial]
    status = data.get("status") or {}
    s = {"serial": serial, "kind": d.get("kind"), "author": d.get("author", ""),
         "missing": bool(d.get("missing"))}
    if d.get("kind") == "review":
        items = _review_items(root, d, serial, cache)
        s.update(created=d.get("created", ""), commit=(d.get("commit") or "")[:12],
                 files=d.get("files", 0))
        keys = [it["id"] for it in items]
    else:
        fm, _ = _plan_front(root / d.get("file", "")) if not d.get("missing") else ({}, "")
        items = []
        s.update(week=d.get("week", ""), category=fm.get("category", ""),
                 plan_status=fm.get("status", ""),
                 redmine_issue_id=fm.get("redmine_issue_id", ""))
        sev = fm.get("severity", "")
        s["severity_label"] = sev
        keys = [serial]
    sev_count = {"high": 0, "mid": 0, "low": 0}
    for it in items:
        sev_count[it["severity"]] = sev_count.get(it["severity"], 0) + 1
    states = {}
    for k in keys:
        st = (status.get(k) or {}).get("state", "open")
        states[st] = states.get(st, 0) + 1
    s.update(items=len(keys), severity=sev_count, states=states)
    return s, items


def list_docs(root, *, do_sweep: bool = True, logf=None) -> dict:
    """번호 붙은 문서 전체의 요약 — 최신 번호가 먼저."""
    root = Path(root)
    swept = sweep(root, logf=logf) if do_sweep else None
    data = load(root)
    cache: dict = {}

    def order(serial):
        k, n, _ = parse_id(serial)
        return (k, -n)
    docs = [_summary(root, data, s, cache)[0] for s in sorted(data["docs"], key=order)]
    return {"docs": docs, "swept": swept}


def get_doc(root, serial: str) -> dict:
    """문서 하나 — 항목·본문 포함. [중요] **토큰이 필요한 8101 로만 내보낸다.**"""
    root = Path(root)
    pid = parse_id(serial)
    if not pid:
        return {"ok": False, "reason": f"번호 형식이 아니다: {serial!r} (예: R12 · P3 · R12-3)"}
    key = f"{pid[0]}{pid[1]}"
    sweep(root)
    data = load(root)
    if key not in data["docs"]:
        return {"ok": False, "reason": f"{key} 는 없는 번호다"}
    d = data["docs"][key]
    s, items = _summary(root, data, key, {})
    status = data.get("status") or {}
    for it in items:
        it["status"] = status.get(it["id"]) or {"state": "open"}
    body = ""
    f = root / d.get("file", "")
    if f.is_file():
        body = f.read_text(encoding="utf-8", errors="replace")
    out = {"ok": True, **s, "file": d.get("file", ""), "items_detail": items, "body": body}
    if d.get("kind") == "review":
        out["commit_full"] = d.get("commit", "")
    else:
        fm, _ = _plan_front(f) if f.is_file() else ({}, "")
        out.update(target_file=fm.get("target_file", ""),
                   source_reviews=fm.get("source_reviews") or [],
                   status=status.get(key) or {"state": "open"})
    return out


# ── 쓰기 ─────────────────────────────────────────────────────────────────────

def set_status(root, item_id: str, state: str, *, note: str = "", by: str = "",
               branch: str = "", commit: str = "", now: datetime | None = None,
               logf=None) -> dict:
    """항목 하나의 결정을 기록한다. 거절은 예외가 아니라 `ok:false` + 사유다.

    리뷰는 행 번호까지(`R12-3`), 플랜은 문서 번호(`P3`)로 부른다.
    플랜이 applied/dismissed/open 이 되면 그 MD 의 `status` 도 acted/dismissed/pending 으로 맞춘다.
    """
    log = logf or (lambda m: None)
    root = Path(root)
    pid = parse_id(item_id)
    if not pid:
        return {"ok": False, "reason": f"항목 형식이 아니다: {item_id!r} (예: R12-3 · P3)"}
    if state not in STATES:
        return {"ok": False, "reason": f"모르는 상태: {state!r} (가능: {', '.join(STATES)})"}
    kind, num, row = pid
    serial = f"{kind}{num}"
    sweep(root, logf=log)
    with _locked(root):
        data = load(root)
        d = data["docs"].get(serial)
        if not d:
            return {"ok": False, "reason": f"{serial} 는 없는 번호다"}
        if kind == "R":
            if row is None:
                return {"ok": False, "reason": f"리뷰는 행 번호까지 준다 (예: {serial}-1)"}
            n = len(_review_items(root, d, serial, {}))
            if not 1 <= row <= n:
                return {"ok": False, "reason": f"{serial} 의 항목은 1~{n} 이다 (받은 값 {row})"}
            key = f"{serial}-{row}"
        else:
            key = serial
        if state == "open":
            data["status"].pop(key, None)
        else:
            data["status"][key] = {
                "state": state,
                "at": (now or datetime.now()).isoformat(timespec="seconds"),
                "by": (by or "")[:80], "note": (note or "")[:NOTE_MAX],
                "branch": (branch or "")[:200], "commit": (commit or "")[:40]}
        _save(root, data)

    out = {"ok": True, "id": key, "state": state}
    if kind == "P" and state in PLAN_STATUS_FOR:
        out["plan_status"] = _write_plan_status(root / d.get("file", ""),
                                                PLAN_STATUS_FOR[state])
    log(f"[fix] {key} → {state}" + (f" · {branch}" if branch else "")
        + (f" · {commit[:12]}" if commit else "")
        + (f" · 플랜 status={out.get('plan_status')}" if "plan_status" in out else ""))
    return out


def _write_plan_status(f: Path, value: str) -> str:
    """플랜 MD frontmatter `status` 를 고친다. 반환은 쓴 값 또는 `[실패] 사유`."""
    from .plan_register import _parse_plan_frontmatter, _serialize_plan_frontmatter
    try:
        fm, body = _parse_plan_frontmatter(f.read_text(encoding="utf-8"))
        if not fm:
            return "[실패] frontmatter 없음"
        fm["status"] = value
        f.write_text(_serialize_plan_frontmatter(fm, body), encoding="utf-8")
    except OSError as e:
        return f"[실패] {type(e).__name__}"
    return value


def main(argv=None) -> int:
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    from ..context_search.paths import resolve
    paths = resolve("")
    cmd = args[0] if args else "list"
    if cmd == "sweep":
        print(json.dumps(sweep(paths.root, logf=print), ensure_ascii=False))
        return 0
    if cmd == "list":
        for s in list_docs(paths.root, logf=print)["docs"]:
            when = s.get("created") or s.get("week", "")
            print(f"{s['serial']:>5} {s['kind']:<6} {when:<16} {s['author']:<12} "
                  f"항목 {s['items']:>3} {s['severity']} {s['states']}"
                  + (" [missing]" if s["missing"] else ""))
        return 0
    if cmd == "show" and len(args) > 1:
        print(json.dumps(get_doc(paths.root, args[1]), ensure_ascii=False, indent=1))
        return 0
    if cmd == "set" and len(args) > 2:
        got = set_status(paths.root, args[1], args[2],
                         note=" ".join(args[3:]), by="cli", logf=print)
        print(json.dumps(got, ensure_ascii=False))
        return 0 if got.get("ok") else 1
    print(__doc__.strip().splitlines()[-1])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
