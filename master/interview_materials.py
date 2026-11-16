"""착수 전 인터뷰 **재료 수집** — `#960` T4.

사용자 결정(2026-11-15): 「파이썬이 직접 모아서 건네줘」 — 세션이 조회하고 「조회했다」고 적는 길을 두지 않는다.
재료는 일감(제목·본문·코멘트·마일스톤) · RAG · 온톨로지 · 작업 보고서 · 최근 완료 일감이다.

[중요] **출처 하나가 실패해도 나머지는 돌려준다** — 대신 실패는 `errors` 에 이름과 사유로 실린다(조용히
빠지지 않는다). 재료는 판정에 쓰지 않는다 — LLM 이 가설·질문을 만드는 데 쓴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORTS = REPO / "reports"
RAG_LIMIT = 6
RECENT_LIMIT = 10
REPORT_LINES = 3


def _query(issue: dict) -> str:
    """검색 질의 — 제목에서 `[AX]`·「버그 —」 같은 머리표를 걷는다."""
    s = re.sub(r"^\s*\[[^\]]*\]\s*", "", issue.get("subject") or "")
    return re.sub(r"^\s*(버그|개선|신규)\s*[—-]\s*", "", s).strip() or (issue.get("subject") or "")


def default_rag(query: str, issue_id: int = 0) -> dict:
    from master.context_search import search_log
    from master.projects import mcp_server
    # `#855` — 재료 검색은 어느 일감의 착수 전 인터뷰인지 안다. 그 번호를 관측값으로 남긴다
    links = mcp_server._search_links(issue_id, "착수 전 인터뷰 재료", source="interview") if issue_id else {}
    with search_log.search_context(caller="interview", task_type="interview_materials",
                                   user_request=None, user_request_source="missing", llm_query=query,
                                   **links):
        return json.loads(mcp_server._search_context(query, RAG_LIMIT))


def default_ontology(query: str) -> dict:
    from master.projects import mcp_server
    return json.loads(mcp_server.infer_domain_tool(query))


def default_recent(project: str) -> dict:
    from master import redmine
    return redmine.list_issues(project=project or redmine.PROJECT_ID, status="closed",
                               limit=RECENT_LIMIT, sort="updated_on:desc")


def reports_mentioning(issue_id, root: Path = REPORTS) -> list[dict]:
    """`#N` 을 언급한 작업 보고서 — 파일 이름과 처음 몇 줄."""
    pat = re.compile(rf"#{int(issue_id)}(?!\d)")
    out = []
    for p in sorted(root.rglob("*.md")) if root.is_dir() else []:
        try:
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if pat.search(ln)]
        except (OSError, UnicodeDecodeError):
            continue
        if lines:
            out.append({"path": str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p),
                        "hits": len(lines), "lines": lines[:REPORT_LINES]})
    return out


def collect(issue: dict, *, project: str = "", rag=None, ontology=None, recent=None,
            reports_root: Path = REPORTS) -> dict:
    """재료 한 묶음. `issue` 는 `redmine.get_issue` 응답(본문·노트 포함)."""
    rag = rag or (lambda q: default_rag(q, int(issue.get("id") or 0)))   # `#855` 일감 번호를 검색 로그에
    ontology, recent = ontology or default_ontology, recent or default_recent
    q = _query(issue)
    errors: dict[str, str] = {}
    log: list[str] = []
    out = {
        "issue": {"id": issue.get("id"), "subject": issue.get("subject", ""),
                  "fixed_version": issue.get("fixed_version", ""), "status": issue.get("status", ""),
                  "description": issue.get("description") or "",
                  "journals": [{"at": j.get("created_on", ""), "user": j.get("user", ""), "notes": j.get("notes", "")}
                               for j in issue.get("journals") or []]},
        "query": q,
    }

    def _take(name, fn, *args):
        try:
            got = fn(*args)
        except Exception as e:                           # noqa: BLE001
            errors[name] = f"{type(e).__name__}: {e}"
            log.append(f"[interview] 재료 {name} 실패 — {errors[name]}")
            return None
        if isinstance(got, dict) and got.get("error"):      # ok:false 만으로는 실패가 아니다(모르면 빈 결과)
            errors[name] = str(got["error"])
            log.append(f"[interview] 재료 {name} 실패 — {errors[name]}")
            return None
        return got

    r = _take("rag", rag, q)
    out["rag"] = None if r is None else {"query_used": r.get("query_used", q), "request_id": r.get("request_id"),
                                         "hits": r.get("hits", [])}
    o = _take("ontology", ontology, q)
    out["ontology"] = None if o is None else {k: o.get(k) for k in ("domains", "summary", "evidence", "notes")}
    out["reports"] = _take("reports", reports_mentioning, issue.get("id"), reports_root)
    rc = _take("recent_closed", recent, project)
    out["recent_closed"] = None if rc is None else [
        {k: x.get(k) for k in ("id", "subject", "fixed_version", "updated_on")} for x in rc.get("issues", [])]
    out["errors"] = errors
    log.append(f"[interview] 재료 수집 #{issue.get('id')} — rag {len((out['rag'] or {}).get('hits') or [])} · "
               f"보고서 {len(out['reports'] or [])} · 최근 완료 {len(out['recent_closed'] or [])} · 실패 {sorted(errors)}")
    out["log"] = log
    return out
