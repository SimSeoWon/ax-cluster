"""도메인 사이드카 `log_categories.yaml` — 실증 테스트용 로그 태그/CVar 매핑 (#169).

원전 `mcp/context_search/ontology_log_tags.py`(132줄, Phase η.12.3) 이식. 계약을 글자대로
유지한다:

- **저작 방향 (b) 개발자 선작성 확정** (원전 history/2026-07-12_1730 + 사용자 재확인) —
  게임팀이 실제 코드에 CVar+태깅 로그를 먼저 넣은 뒤 사람이 사후 기입한다.
  **자동 생성·자동 편입 없음** (제안 리포트는 `log_candidates.py` 가 별도 생성).
- 태그 문자열은 이 사이드카가 유일한 SSOT — 로그 분석 전 임의 추측을 막는다.
- 읽기 측(뷰어의 invariant 목록)이 `log_tags` 필드로 자동 첨부한다. [중요] 매치가 없으면
  **필드 자체를 생략** — "확인했는데 없음"(로그로 실증 불가)과 "확인 안 함"을 null 이
  아니라 부재로 구분한다 (원전 find_log_tags_for_invariant 의 주석 그대로).

경로: `<트윈>/ontology/domains/<D>/log_categories.yaml` (원전은 `.claude/ontology/...`).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import yaml_io

FILENAME = "log_categories.yaml"


def sidecar_path(domain_dir: Path) -> Path:
    """도메인 패키지 디렉토리 → 사이드카 경로. 뷰어(loaders)도 이 저수준을 쓴다."""
    return Path(domain_dir) / FILENAME


def _domain_dir(paths, domain: str) -> Path:
    return paths.ontology / "domains" / domain


def entries_at(domain_dir: Path) -> list:
    """도메인 패키지 안의 entries 목록 (부재 시 빈 리스트)."""
    p = sidecar_path(domain_dir)
    data = yaml_io.read(p) if p.is_file() else None
    if not isinstance(data, dict):
        return []
    return list(data.get("entries") or [])


def load_entries(paths, domain: str) -> list:
    return entries_at(_domain_dir(paths, domain))


def tags_for_invariant(entries: list, invariant_name: str) -> list:
    """invariant 1건에 매핑된 항목들. `[{"tag","cvar"}, ...]` — 없으면 빈 리스트.

    [주의] 호출자가 entries 를 한 번만 읽어 여러 invariant 에 재사용한다 — 뷰어가
    invariant 마다 파일을 다시 읽으면 도메인 하나에 수십 번 I/O 다.
    """
    out = []
    for e in entries:
        if invariant_name in (e.get("related_invariants") or []):
            out.append({"tag": e.get("tag", ""), "cvar": e.get("cvar", "")})
    return out


def list_impl(paths, domain: str) -> dict:
    """entries 전체 조회 (read-only)."""
    pkg = _domain_dir(paths, domain)
    if not pkg.is_dir():
        return {"status": "not_found", "domain": domain, "reason": "도메인 패키지 부재"}
    entries = load_entries(paths, domain)
    return {"status": "ok", "domain": domain, "count": len(entries), "entries": entries}


def set_impl(paths, domain: str, tag: str, cvar: str,
             related_invariants: list | None = None) -> dict:
    """tag 기준 upsert — 있으면 cvar/related_invariants 갱신, 없으면 추가.

    `registered_at` 은 저장할 때마다 무조건 갱신 (원전 η.12.14 `synthesized_at` 과 같은
    단순 스탬프 — 해시 비교·변경 감지 없음).
    """
    tag = (tag or "").strip()
    cvar = (cvar or "").strip()
    if not tag:
        return {"status": "error", "reason": "tag 가 비어있음"}
    pkg = _domain_dir(paths, domain)
    if not pkg.is_dir():
        return {"status": "not_found", "domain": domain, "reason": "도메인 패키지 부재"}

    entries = load_entries(paths, domain)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = False
    for e in entries:
        if e.get("tag") == tag:
            e["cvar"] = cvar
            e["related_invariants"] = (list(related_invariants)
                                       if related_invariants is not None
                                       else list(e.get("related_invariants") or []))
            e["registered_at"] = now
            updated = True
            break
    if not updated:
        entries.append({"tag": tag, "cvar": cvar,
                        "related_invariants": list(related_invariants or []),
                        "registered_at": now})
    yaml_io.write(sidecar_path(pkg), {"entries": entries})
    return {"status": "updated" if updated else "created",
            "domain": domain, "tag": tag, "entry_count": len(entries)}


def remove_impl(paths, domain: str, tag: str) -> dict:
    """tag 1건 삭제. 되돌릴 수 없음 — 호출 측이 확정 전 사람에게 보여 준다.

    마지막 항목이 지워지면 **파일째 지운다** (원전 그대로) — 빈 사이드카는
    "확인했는데 없음"이 아니라 "없음"이다.
    """
    pkg = _domain_dir(paths, domain)
    p = sidecar_path(pkg)
    entries = load_entries(paths, domain)
    remaining = [e for e in entries if e.get("tag") != tag]
    if len(remaining) == len(entries):
        return {"status": "not_found", "domain": domain, "tag": tag}
    if remaining:
        yaml_io.write(p, {"entries": remaining})
    else:
        p.unlink(missing_ok=True)
    return {"status": "deleted", "domain": domain, "tag": tag,
            "entry_count": len(remaining)}
