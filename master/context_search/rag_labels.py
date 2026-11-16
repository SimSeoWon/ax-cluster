"""RAG 실사용 평가 라벨 (`#855` T2) — 검색 로그와 **분리된** 사람(검증자) 판정 기록.

검색 로그(`search_log`)는 「무엇을 검색했고 무엇을 반환했나」다. 이 모듈은 그 위에 **판정**을 얹는다 —
요청·검색 하나가 요구에 필요한 근거를 줬는지(근거 제공), 그 근거가 플랜·코드에 실제로 쓰였는지(채택).
원본 로그는 건드리지 않는다. 판정은 `<트윈>/rag_labels/labels.jsonl` 에 덧붙이고 **같은 대상의 최신 판정이 유효**하다
(이력은 남는다).

    근거 제공  있음 · 일부 · 없음 · 확인불가
    채택      직접 · 간접 · 확인불가
    상태      후보(검증 전 제안) · 확정(검증자가 근거와 함께 확인)

🔴 [중요] **「직접 채택」은 산출물 근거가 있어야 한다** — 커밋 해시 · 플랜 태스크(`#N T#`) · `파일:줄` 중 하나.
같은 모듈이 반환되고 나중에 수정됐다는 사실, 에이전트의 자기 보고는 직접 증거가 아니다(2026-10-31 Gemini 분석이
그렇게 과대 판정했다 — #855 본문). 근거 없이 「직접」을 적으면 기록이 거절된다.
[주의] 「결과 있음」 비율을 적중률·반영률로 쓰지 않는다 — `summary` 는 판정된 것과 판정 안 된 것을 나눠 센다.

    .venv/bin/python -m master.context_search.rag_labels add --search <id> --evidence 있음 --adoption 직접 \\
        --status 확정 --reviewer claude --basis "커밋 853dbd3" --basis "master/x.py:12"
    .venv/bin/python -m master.context_search.rag_labels list [--issue N] [--request ID]
    .venv/bin/python -m master.context_search.rag_labels summary [--issue N]
    .venv/bin/python -m master.context_search.rag_labels check [--issue N]      # 불일치면 rc 1
"""
from __future__ import annotations

import fcntl
import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from . import search_log

EVIDENCE = ("있음", "일부", "없음", "확인불가")
ADOPTION = ("직접", "간접", "확인불가")
STATUS = ("후보", "확정")
TARGETS = ("search", "request")
SCHEMA = 1

# 「직접」 채택의 산출물 근거 — 커밋 해시 · 플랜 태스크 · 파일:줄
_ADOPTION_BASIS = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])"          # 커밋 해시
    r"|#\d+\s*T\d+"                                    # 플랜 태스크
    r"|[\w./-]+\.\w+:\d+")                             # 파일:줄
_lock = threading.Lock()


class LabelError(ValueError):
    """기록 거절 — 사유가 메시지다."""


def labels_path(paths) -> Path:
    return Path(paths.root) / "rag_labels" / "labels.jsonl"


def has_adoption_basis(basis) -> bool:
    return any(_ADOPTION_BASIS.search(str(b or "")) for b in basis or ())


def _entries_by(paths):
    searches, requests = {}, {}
    for rec in search_log._all_entries(paths):
        sid, rid = rec.get("search_id"), rec.get("request_id")
        if sid:
            searches[sid] = rec
        if rid:
            requests.setdefault(rid, []).append(rec)
    return searches, requests


def _doc_hashes(records) -> dict:
    out = {}
    for rec in records:
        for row in rec.get("result_snapshot") or []:
            fid = row.get("file_id")
            h = (row.get("meta") or {}).get("content_hash") if isinstance(row.get("meta"), dict) else None
            if fid:
                out[str(fid)] = h or ""
    return out


def validate(rec: dict) -> list:
    """한 판정의 형식·근거 규칙 위반 목록(비면 통과)."""
    bad = []
    if rec.get("target") not in TARGETS:
        bad.append(f"target 은 {TARGETS} 중 하나")
    if rec.get("evidence") not in EVIDENCE:
        bad.append(f"근거 제공은 {EVIDENCE} 중 하나")
    if rec.get("adoption") not in ADOPTION:
        bad.append(f"채택은 {ADOPTION} 중 하나")
    if rec.get("status") not in STATUS:
        bad.append(f"상태는 {STATUS} 중 하나")
    basis = rec.get("basis") or []
    if rec.get("adoption") == "직접":
        if not has_adoption_basis(basis):
            bad.append("「직접」 채택은 산출물 근거(커밋 해시 · #N T# · 파일:줄)가 있어야 한다")
        if rec.get("evidence") in ("없음", "확인불가"):
            bad.append(f"근거 제공이 「{rec.get('evidence')}」인데 「직접」 채택일 수 없다")
    if rec.get("status") == "확정":
        if not str(rec.get("reviewer") or "").strip():
            bad.append("「확정」은 검증자가 있어야 한다")
        if not basis:
            bad.append("「확정」은 근거 인용이 있어야 한다")
    return bad


def add(paths, *, target: str, target_id: str, evidence: str, adoption: str, status: str = "후보",
        basis=(), reviewer: str = "", note: str = "") -> dict:
    """판정 하나를 덧붙인다. 대상이 검색 로그에 없거나 규칙을 어기면 `LabelError`."""
    searches, requests = _entries_by(paths)
    if target == "search":
        src = searches.get(target_id)
        if not src:
            raise LabelError(f"검색 로그에 없는 search_id: {target_id}")
        records, request_id, search_id = [src], src.get("request_id", ""), target_id
    elif target == "request":
        records = requests.get(target_id) or []
        if not records:
            raise LabelError(f"검색 로그에 없는 request_id: {target_id}")
        request_id, search_id = target_id, ""
    else:
        raise LabelError(f"target 은 {TARGETS} 중 하나")
    issue_ids = sorted({r["issue_id"] for r in records if isinstance(r.get("issue_id"), int)})
    rec = {
        "schema": SCHEMA, "label_id": uuid.uuid4().hex, "ts": datetime.now().astimezone().isoformat(),
        "project": getattr(paths, "name", ""), "target": target,
        "request_id": request_id, "search_id": search_id, "issue_ids": issue_ids,
        "evidence": evidence, "adoption": adoption, "status": status,
        "basis": [str(b).strip() for b in basis or () if str(b).strip()],
        "reviewer": reviewer.strip(), "note": note.strip()[:500],
        # 판정 당시 반환 문서의 해시 — 문서가 바뀐 뒤에도 무엇을 보고 판정했는지 남긴다
        "doc_hashes": _doc_hashes(records),
    }
    bad = validate(rec)
    if bad:
        raise LabelError(" · ".join(bad))
    p = labels_path(paths)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_all(paths) -> list:
    p = labels_path(paths)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def latest(paths) -> dict:
    """대상별 최신 판정 `{(target, id): 판정}` — 뒤에 적은 것이 이긴다."""
    out = {}
    for rec in read_all(paths):
        key = (rec.get("target"), rec.get("search_id") if rec.get("target") == "search" else rec.get("request_id"))
        out[key] = rec
    return out


def summary(paths, *, issue_id: int = 0, task_type: str = "user_command") -> dict:
    """분모(요청·검색·문서)와 행별 판정, 요약 집계. `issue_id` 면 그 일감에 관측 연결된 검색만."""
    entries = [r for r in search_log._all_entries(paths)
               if (not task_type or r.get("task_type") == task_type)
               and (not issue_id or r.get("issue_id") == int(issue_id))]
    search_ids = {r.get("search_id") for r in entries if r.get("search_id")}
    request_ids = {r.get("request_id") for r in entries if r.get("request_id")}
    docs = sum(len(r.get("result_snapshot") or []) for r in entries)
    labels = latest(paths)
    rows = []
    for (target, tid), rec in sorted(labels.items(), key=lambda kv: str(kv[0])):
        pool = search_ids if target == "search" else request_ids
        if tid in pool:
            rows.append({k: rec.get(k) for k in ("target", "request_id", "search_id", "issue_ids", "evidence",
                                                 "adoption", "status", "basis", "reviewer", "label_id")})
    totals = {"searches": len(search_ids), "requests": len(request_ids), "docs": docs}
    counts = {}
    for target, denom in (("search", len(search_ids)), ("request", len(request_ids))):
        mine = [r for r in rows if r["target"] == target]
        counts[target] = {
            "labeled": len(mine), "unlabeled": denom - len(mine),
            "evidence": {k: sum(r["evidence"] == k for r in mine) for k in EVIDENCE},
            "adoption": {k: sum(r["adoption"] == k for r in mine) for k in ADOPTION},
            "status": {k: sum(r["status"] == k for r in mine) for k in STATUS},
        }
    return {"project": getattr(paths, "name", ""), "issue_id": int(issue_id or 0), "task_type": task_type,
            "totals": totals, "counts": counts, "rows": rows}


def check(report: dict) -> list:
    """요약 집계가 행별 판정·분모와 맞는지, 행이 규칙을 지키는지. 문제 목록(비면 통과)."""
    problems = []
    rows = report.get("rows") or []
    for target, denom_key in (("search", "searches"), ("request", "requests")):
        c = (report.get("counts") or {}).get(target) or {}
        mine = [r for r in rows if r.get("target") == target]
        denom = (report.get("totals") or {}).get(denom_key, 0)
        if c.get("labeled") != len(mine):
            problems.append(f"{target}: 판정 수 {c.get('labeled')} ≠ 행 {len(mine)}")
        if (c.get("labeled") or 0) + (c.get("unlabeled") or 0) != denom:
            problems.append(f"{target}: 판정 {c.get('labeled')} + 미판정 {c.get('unlabeled')} ≠ 분모 {denom}")
        if (c.get("unlabeled") or 0) < 0:
            problems.append(f"{target}: 미판정이 음수 — 분모 밖 판정이 섞였다")
        for field, keys in (("evidence", EVIDENCE), ("adoption", ADOPTION), ("status", STATUS)):
            got = (c.get(field) or {})
            want = {k: sum(r.get(field) == k for r in mine) for k in keys}
            if got != want:
                problems.append(f"{target}.{field}: 집계 {got} ≠ 행별 {want}")
            if sum(got.values()) != len(mine):
                problems.append(f"{target}.{field}: 합 {sum(got.values())} ≠ 판정 {len(mine)}")
    for r in rows:
        if r.get("adoption") == "직접" and not has_adoption_basis(r.get("basis")):
            problems.append(f"{r.get('label_id')}: 산출물 근거 없이 「직접」 채택으로 집계됐다")
    return problems


def _main(argv=None) -> int:
    import argparse
    from .paths import resolve
    ap = argparse.ArgumentParser(prog="python -m master.context_search.rag_labels")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--search")
    g.add_argument("--request")
    a.add_argument("--evidence", required=True, choices=EVIDENCE)
    a.add_argument("--adoption", required=True, choices=ADOPTION)
    a.add_argument("--status", default="후보", choices=STATUS)
    a.add_argument("--basis", action="append", default=[])
    a.add_argument("--reviewer", default="")
    a.add_argument("--note", default="")
    for name in ("list", "summary", "check"):
        s = sub.add_parser(name)
        s.add_argument("--issue", type=int, default=0)
        s.add_argument("--request", default="")
        s.add_argument("--task-type", default="user_command")
    for s in (a,):
        s.add_argument("--project", default="")
    for name in ("list", "summary", "check"):
        sub.choices[name].add_argument("--project", default="")
    args = ap.parse_args(argv)
    paths = resolve(args.project)
    if args.cmd == "add":
        try:
            rec = add(paths, target="search" if args.search else "request", target_id=args.search or args.request,
                      evidence=args.evidence, adoption=args.adoption, status=args.status, basis=args.basis,
                      reviewer=args.reviewer, note=args.note)
        except LabelError as e:
            print(f"[rag_labels] 거절 — {e}")
            return 2
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "list":
        rows = [r for r in read_all(paths) if (not args.request or r.get("request_id") == args.request)
                and (not args.issue or args.issue in (r.get("issue_ids") or []))]
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        print(f"[rag_labels] {len(rows)}건 (이력 포함 — 대상별 최신만 유효)")
        return 0
    rep = summary(paths, issue_id=args.issue, task_type=args.task_type)
    if args.cmd == "summary":
        print(json.dumps({k: rep[k] for k in ("project", "issue_id", "task_type", "totals", "counts")},
                         ensure_ascii=False, indent=2))
        return 0
    problems = check(rep)
    for p in problems:
        print(f"[rag_labels] 불일치 — {p}")
    print(f"[rag_labels] check {'통과' if not problems else '실패'} — 행 {len(rep['rows'])} · 문제 {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(_main())
