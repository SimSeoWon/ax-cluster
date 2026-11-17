"""검색 유용성 유추 — 일감 · 작업 리포트 · 커밋 파일과 검색 결과 대조 (`#980`).

사용자 관찰(2026-11-17): 「사용자가 요청한 일감과 이 일감을 작업한 보고서, 그리고 해당 일감을 진행하면서 커밋한
파일등을 이용해 유용한 검색이었는지 유추할 수 있었어」. #211 에서 손으로 한 그 대조를 요청 단위로 자동화한다.

    요청(검색 로그 request_id) ──연결──▶ 일감 N
        연결   observed  검색 로그의 issue_id(#855 직접·잠금 · #979 스냅샷)
               candidate #979 이전 로그 — 원문에 번호가 **하나**일 때만 「원문 번호 후보」(#855: 확정 연결 아님)
    일감 N ──▶ 커밋이 고친 파일   issue_track 회차 해시(#884 이후) · 없으면 커밋 메시지 `#N`
           ──▶ 리포트가 언급한 파일 그 일감 리포트(파일명에 N) 전체 + 다른 리포트의 `#N` 언급 줄
    소스 `master/x.py` ↔ 컨텍스트 문서 `master/x.md` (현재 색인에 있는 것만)

판정(자동 「후보」)과 `--apply` 는 아래 절. [중요] 사람 확정 없이 판정을 확정하지 않는다(#855).
[중요] 읽기 전용 — 원본 검색 로그는 바이트 그대로다. 쓰는 것은 `--apply` 의 `rag_labels` 덧붙이기뿐이다.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORTS = REPO / "reports"

OBSERVED = "observed"
CANDIDATE = "candidate"

_NUM = re.compile(r"(?<![\d.])(\d{3,5})(?![\d.])")      # rag_logs 의 원문 번호 후보와 같은 규칙
_PY = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w-]+\.py)\b")


@dataclass
class Link:
    issue_id: int | None
    kind: str = ""            # observed · candidate · ""(연결 없음)
    source: str = ""          # issue_id_source 또는 「원문 번호 후보」
    why: str = ""             # 연결하지 않은 사유


@dataclass
class IssueEvidence:
    issue_id: int
    commits: list = field(default_factory=list)          # [(sha, 경로)] — 비테스트 .py 를 고친 커밋
    commit_docs: dict = field(default_factory=dict)      # 문서 → [근거 문자열]
    report_docs: dict = field(default_factory=dict)      # 문서 → [근거 문자열]
    commit_source: str = ""                              # issue_track · message · ""
    reports: list = field(default_factory=list)          # 대조한 리포트 경로

    @property
    def empty(self) -> bool:
        return not self.commit_docs and not self.report_docs


def group_requests(entries, *, task_type: str = "user_command") -> dict:
    """request_id → 그 요청의 검색들(로그 순). `task_type` 이 비면 전부."""
    out: dict = {}
    for e in entries:
        if task_type and e.get("task_type") != task_type:
            continue
        rid = str(e.get("request_id") or e.get("search_id") or "")
        if rid:
            out.setdefault(rid, []).append(e)
    return out


def link_of(entries) -> Link:
    """요청 → 일감. 관측 연결이 먼저, 없으면 원문 번호가 하나일 때만 후보."""
    seen = {e["issue_id"]: e.get("issue_id_source") or "" for e in entries if isinstance(e.get("issue_id"), int)}
    if len(seen) == 1:
        n, src = next(iter(seen.items()))
        return Link(n, OBSERVED, src)
    if len(seen) > 1:
        return Link(None, why=f"한 요청에 관측 일감이 여럿 {sorted(seen)}")
    nums = sorted({int(m) for e in entries for m in _NUM.findall(str(e.get("user_request") or ""))})
    if len(nums) == 1:
        return Link(nums[0], CANDIDATE, "원문 번호 후보")
    if nums:
        return Link(None, why=f"원문 번호가 여럿 {nums} — 연결하지 않는다")
    return Link(None, why="연결 없음(관측·원문 번호 모두 없음)")


def _is_test(path: str) -> bool:
    return Path(path).name.startswith("test_")


def doc_of(path: str, context_root: Path) -> str:
    """소스 경로 → 현재 색인의 문서 경로(없으면 빈 문자열). 테스트 파일은 대상이 아니다."""
    if not path.endswith(".py") or _is_test(path):
        return ""
    doc = str(Path(path).with_suffix(".md"))
    return doc if (Path(context_root) / doc).is_file() else ""


def _git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else ""


def commit_hashes(issue_id: int, *, twin_root, repo: Path = REPO, git=_git) -> tuple[list, str]:
    """(해시 목록, 출처). 마감 추적 회차가 먼저 — 없으면 커밋 메시지 `#N`."""
    try:
        from master.context_synth import issue_track
        hashes = [h["sha"] for r in issue_track.rounds(twin_root, issue_id) for h in r.get("hashes") or []
                  if h.get("sha")]
    except Exception:                                       # noqa: BLE001 — 추적이 없으면 메시지로
        hashes = []
    if hashes:
        return hashes, "issue_track"
    out = git(repo, "log", "--all", "--format=%H", "-E", f"--grep=#{int(issue_id)}([^0-9]|$)")
    hashes = [h for h in out.split() if h]
    return hashes, ("message" if hashes else "")


def commit_docs(issue_id: int, *, twin_root, context_root: Path, repo: Path = REPO, git=_git) -> tuple:
    """(문서 → 근거, [(sha, 경로)], 출처)."""
    hashes, source = commit_hashes(issue_id, twin_root=twin_root, repo=repo, git=git)
    docs: dict = {}
    pairs = []
    for sha in hashes:
        for path in git(repo, "show", "--name-only", "--format=", sha).split():
            d = doc_of(path, context_root)
            if d:
                pairs.append((sha, path))
                docs.setdefault(d, []).append(f"커밋 {sha[:7]}: {path}")
    return docs, pairs, source


def _own_report(path: Path, issue_id: int) -> bool:
    return re.search(rf"(?<!\d){int(issue_id)}(?!\d)", path.name) is not None


def report_docs(issue_id: int, *, context_root: Path, reports_root: Path = REPORTS) -> tuple[dict, list]:
    """(문서 → 근거, 대조한 리포트). 그 일감 리포트(파일명에 N)는 전체, 다른 리포트는 `#N` 언급 줄만 본다."""
    pat = re.compile(rf"#{int(issue_id)}(?!\d)")
    docs: dict = {}
    seen = []
    stems = _stem_index(context_root)
    for p in sorted(Path(reports_root).rglob("*.md")) if Path(reports_root).is_dir() else []:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        own = _own_report(p, issue_id)
        picked = [(i, ln) for i, ln in enumerate(lines, 1) if own or pat.search(ln)]
        if not picked:
            continue
        rel = str(p.relative_to(reports_root.parent)) if p.is_relative_to(reports_root.parent) else str(p)
        seen.append(rel)
        for i, ln in picked:
            for name in _PY.findall(ln):
                for d in _docs_for_name(name, context_root, stems):
                    docs.setdefault(d, []).append(f"{rel}:{i}")
    return docs, seen


def _stem_index(context_root: Path) -> dict:
    idx: dict = {}
    root = Path(context_root)
    for f in root.rglob("*.md") if root.is_dir() else []:
        idx.setdefault(f.stem, []).append(str(f.relative_to(root)))
    return idx


def _docs_for_name(name: str, context_root: Path, stems: dict) -> list:
    """리포트 속 `.py` 이름 → 문서. 경로가 있으면 그 경로, 이름만 있으면 같은 이름 문서가 하나일 때만."""
    if _is_test(name):
        return []
    if "/" in name:
        d = doc_of(name, context_root)
        return [d] if d else []
    cands = stems.get(Path(name).stem, [])
    return cands if len(cands) == 1 else []


def evidence(issue_id: int, *, twin_root, context_root: Path, repo: Path = REPO,
             reports_root: Path = REPORTS, git=_git) -> IssueEvidence:
    cdocs, pairs, source = commit_docs(issue_id, twin_root=twin_root, context_root=context_root,
                                       repo=repo, git=git)
    rdocs, reports = report_docs(issue_id, context_root=context_root, reports_root=reports_root)
    return IssueEvidence(issue_id, commits=pairs, commit_docs=cdocs, report_docs=rdocs,
                         commit_source=source, reports=reports)


# ── 판정 (자동 「후보」) ──────────────────────────────────────────────────────────
#
#   근거 있음      상위 5 안에 그 일감 커밋이 고친 파일의 문서
#   근거 일부      고친 파일의 문서가 6~15위뿐이거나, 리포트 언급 문서만 반환
#   근거 없음      반환 문서가 어느 쪽에도 없다
#   확인불가       연결 없음 · 그 일감에 커밋도 리포트 언급도 없음
#   채택           겹치면 「간접」, 아니면 「확인불가」 — [중요] 자동으로 「직접」을 주지 않는다:
#                  검색에 나온 문서를 고쳤다는 것은 그 결과를 작업자가 **썼다**는 증거가 아니다(#855).

TOP = 5
LIMIT = 15
AUTO = "auto"


def returned_docs(entries) -> dict:
    """요청의 검색들이 돌려준 문서 → (최고 순위, search_id). 15위까지."""
    best: dict = {}
    for e in entries:
        for rank, f in enumerate(e.get("results") or [], 1):
            if rank > LIMIT or not f:
                break
            if f not in best or rank < best[f][0]:
                best[f] = (rank, str(e.get("search_id") or ""))
    return best


def judge(entries, link: Link, ev: IssueEvidence | None) -> dict:
    docs = returned_docs(entries)
    marks = []
    for f, (rank, sid) in sorted(docs.items(), key=lambda kv: kv[1][0]):
        kinds = [k for k, src in (("커밋", ev.commit_docs if ev else {}), ("리포트", ev.report_docs if ev else {}))
                 if f in src]
        marks.append({"doc": f, "rank": rank, "search_id": sid, "marks": kinds,
                      "why": [*(ev.commit_docs.get(f, []) if ev else []),
                              *(ev.report_docs.get(f, []) if ev else [])][:3]})
    if link.issue_id is None:
        evidence, reason = "확인불가", link.why
    elif ev is None or ev.empty:
        evidence, reason = "확인불가", f"#{link.issue_id} 에 커밋·리포트 근거가 없다"
    elif any("커밋" in m["marks"] and m["rank"] <= TOP for m in marks):
        evidence, reason = "있음", f"상위 {TOP} 안에 #{link.issue_id} 커밋이 고친 파일의 문서"
    elif any(m["marks"] for m in marks):
        evidence, reason = "일부", "고친 파일 문서가 6~15위뿐이거나 리포트 언급 문서만"
    else:
        evidence, reason = "없음", "반환 문서가 커밋·리포트 어느 쪽에도 없다"
    adoption = "간접" if evidence in ("있음", "일부") else "확인불가"
    basis = [f"{m['search_id'][:8]} {m['rank']}위 {m['doc']} ← {w}" for m in marks if m["marks"] for w in m["why"]][:8]
    return {"issue_id": link.issue_id, "link": link.kind, "link_source": link.source,
            "evidence": evidence, "adoption": adoption, "reason": reason,
            "commit_source": ev.commit_source if ev else "", "docs": marks, "basis": basis,
            "searches": [str(e.get("search_id") or "") for e in entries]}


def note_of(row: dict) -> str:
    """판정 note — 자동 대조임과 연결의 성격(관측/원문 번호 후보)을 밝힌다."""
    if row["link"] == CANDIDATE:
        link = f"원문 번호 후보 #{row['issue_id']} — 확정 연결 아님"
    elif row["link"] == OBSERVED:
        link = f"관측 연결 #{row['issue_id']} ({row['link_source'] or '출처 미상'})"
    else:
        link = "연결 없음"
    return f"자동 대조(#980) · {link} · {row['reason']}"


def analyze(paths, *, issue_id: int = 0, task_type: str = "user_command", repo: Path = REPO,
            reports_root: Path = REPORTS, git=_git) -> list:
    """요청별 판정 목록. `issue_id` 면 그 일감으로 연결된(관측·후보) 요청만."""
    from master.context_search import search_log
    groups = group_requests(search_log._all_entries(paths), task_type=task_type)
    cache: dict = {}
    rows = []
    for rid, entries in groups.items():
        link = link_of(entries)
        if issue_id and link.issue_id != int(issue_id):
            continue
        ev = None
        if link.issue_id is not None:
            if link.issue_id not in cache:
                cache[link.issue_id] = evidence(link.issue_id, twin_root=paths.root, context_root=paths.context,
                                                repo=repo, reports_root=reports_root, git=git)
            ev = cache[link.issue_id]
        row = judge(entries, link, ev)
        row["request_id"] = rid
        # 판정 대상 — request_id 가 있으면 요청, 옛 로그처럼 없으면 그 검색 하나(`rag_labels` 대상 규칙)
        row["target"] = "request" if any(e.get("request_id") for e in entries) else "search"
        row["user_request"] = next((e.get("user_request") for e in entries if e.get("user_request")), None)
        rows.append(row)
    return rows


def apply(paths, rows, *, add=None, latest=None) -> dict:
    """판정을 `rag_labels` 에 검증자 auto·「후보」로 덧붙인다(`#855` 저장소 · 스키마 무변경).

    건너뜀: 연결 없는 요청(근거가 없어 판정할 것이 없다) · **사람이 판정한 대상**(검증자가 auto 가 아니다) ·
    같은 자동 판정이 이미 최신인 대상(재실행해도 같은 결과). 원본 검색 로그는 건드리지 않는다.
    """
    from master.context_search import rag_labels
    add = add or rag_labels.add
    current = (latest or rag_labels.latest)(paths)
    out = {"added": 0, "unchanged": 0, "human": 0, "unlinked": 0, "errors": []}
    for r in rows:
        if r["issue_id"] is None:
            out["unlinked"] += 1
            continue
        target, tid = r.get("target", "request"), r["request_id"]
        note = note_of(r)
        cur = current.get((target, tid))
        if cur and str(cur.get("reviewer") or "") != AUTO:
            out["human"] += 1
            continue
        if cur and (cur.get("evidence"), cur.get("adoption"), cur.get("basis") or [], cur.get("note")) == \
                (r["evidence"], r["adoption"], r["basis"], note):
            out["unchanged"] += 1
            continue
        try:
            add(paths, target=target, target_id=tid, evidence=r["evidence"], adoption=r["adoption"],
                status="후보", basis=r["basis"], reviewer=AUTO, note=note)
        except Exception as e:                              # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            out["errors"].append(f"{target}:{tid[:8]} {type(e).__name__}: {e}")
            continue
        out["added"] += 1
    return out


def distribution(rows) -> dict:
    out = {k: 0 for k in ("있음", "일부", "없음", "확인불가")}
    for r in rows:
        out[r["evidence"]] += 1
    return {"requests": len(rows), "evidence": out,
            "link": {k: sum(r["link"] == k for r in rows) for k in (OBSERVED, CANDIDATE, "")}}


def report_text(rows) -> str:
    d = distribution(rows)
    out = [f"요청 {d['requests']}건 · 근거 {d['evidence']} · 연결 관측 {d['link'][OBSERVED]} · "
           f"원문 번호 후보 {d['link'][CANDIDATE]} · 연결 없음 {d['link']['']}"]
    for r in rows:
        tag = {OBSERVED: "관측", CANDIDATE: "후보"}.get(r["link"], "없음")
        n = f"#{r['issue_id']}" if r["issue_id"] else "-"
        out.append(f"\n[{r['evidence']}·채택 {r['adoption']}] {n}({tag}) 요청 {r['request_id'][:8]} "
                   f"「{(r.get('user_request') or '')[:40]}」 — {r['reason']}")
        for m in r["docs"][:LIMIT]:
            mark = "+".join(m["marks"]) or "-"
            out.append(f"   {m['rank']:>2}위 {m['doc']}  [{mark}]" + (f"  ← {m['why'][0]}" if m["why"] else ""))
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python -m master.search_usefulness")
    ap.add_argument("--issue", type=int, default=0, help="그 일감으로 연결된 요청만")
    ap.add_argument("--task-type", default="user_command")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="판정을 rag_labels 에 auto·「후보」로 덧붙인다(사람 판정은 건드리지 않는다)")
    args = ap.parse_args(argv)
    from master.context_search.paths import resolve
    paths = resolve("")
    rows = analyze(paths, issue_id=args.issue, task_type=args.task_type)
    applied = apply(paths, rows) if args.apply else None
    if args.json:
        print(json.dumps({"distribution": distribution(rows), "applied": applied, "rows": rows},
                         ensure_ascii=False, indent=1))
    else:
        print(report_text(rows))
        if applied is not None:
            print(f"\n[apply] 추가 {applied['added']} · 그대로 {applied['unchanged']} · 사람 판정 보존 "
                  f"{applied['human']} · 연결 없음 건너뜀 {applied['unlinked']} · 실패 {len(applied['errors'])}")
            for e in applied["errors"]:
                print(f"  [실패] {e}")
    return 1 if applied and applied["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
