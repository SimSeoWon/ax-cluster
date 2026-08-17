"""태깅 권장 지점 리포트 — 게임팀 핸드오프용, **제안형** (#169, 원전 η.12.3).

원전 `watcher/log_tagging_candidates.py`(240줄) 이식. active 도메인의 invariant
evidence 를 파싱해 *"여기 태깅하면 실증 테스트에 좋다"* + 권장 로그 태그·CVar 이름을
제안하는 MD 를 만든다. **사이드카를 직접 건드리지 않는다** — 게임팀이 실제 코드에
CVar+태깅 로그를 구현한 뒤에야 사람이 `log-tags set` 으로 확정 기입한다 (저작 방향 (b),
자동 편입 없음 — `_unassigned` 와 같은 패턴).

원전과 다른 곳 둘 (둘 다 우리 환경이 근거):

- [주의] **확정 등록분 표기**: 원전은 dedup 을 못 했다 — watcher 의 단순 스칼라 파서로는
  중첩 리스트(사이드카)를 안전하게 못 읽어서 *"사람이 대조해 걸러낸다"* 로 남겼다. 우리는
  전체 YAML 리더(yaml_io)가 있으므로 이미 등록된 invariant 를 **버리지 않고 [확정 등록됨]
  으로 표기**한다 — 사람이 대조하는 원전의 자리를 지우지 않고 그 대조를 대신해 준다.
- [주의] **일일 게이트 없음**: 원전은 watch.exe 유휴 루프에 1회/일 게이트로 걸었지만
  우리에게는 그 루프가 없다(ax-indexer 는 push 구동). LLM 0·부작용은 파일 1개라
  CLI(`python -m master.ontology log-candidates`)로 사람이 부른다.

출력: `<트윈>/ontology/_log_tagging_candidates.md` (`_thesaurus.tsv` 와 같은 자리).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import domain_md, log_tags, yaml_io

OUTPUT_FILENAME = "_log_tagging_candidates.md"
_LAYER_DIRS = ("L1", "L2", "L3")

# 원전 ontology_layers.py:45 그대로 — evidence 의 `<PascalCase>.(cpp|h)` 에서 클래스명.
# "Tick() 의 lock_guard 패턴" 처럼 확장자 없는 서술형 evidence 는 자연히 빈 집합이 된다.
_CLASS_IN_EVIDENCE_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\.(?:cpp|h)\b")


def parse_evidence_classes(evidence: str) -> set:
    if not evidence:
        return set()
    return set(_CLASS_IN_EVIDENCE_RE.findall(evidence))


def suggest_names(domain: str, invariant_name: str) -> tuple:
    """권장 로그 태그·CVar — `<도메인>.Log<기능>.Enable` 컨벤션 (원전 2026-07-12 확정).

    게임팀이 다른 이름을 쓰면 `log-tags set` 에서 얼마든지 다르게 확정 기입한다 —
    어디까지나 제안 기본값이다.
    """
    feature = re.sub(r"[^A-Za-z0-9]", "", invariant_name)[:40] or "Event"
    return f"Log{domain}{feature}", f"{domain.lower()}.Log{feature}.Enable"


def compute(paths) -> dict:
    """active 도메인의 invariant evidence → 태깅 후보.

    반환: {"by_domain": {도메인: [cand,...]}, "counts": {"total","domains","registered"}}
    cand = {invariant, evidence, classes, layer, suggested_tag, suggested_cvar, registered}
    """
    domains_root = paths.ontology / "domains"
    by_domain: dict = {}
    total = registered_n = 0
    for doc in domain_md.read_all(paths):
        pkg = domains_root / doc.domain
        if not pkg.is_dir():
            continue
        already = set()
        for e in log_tags.entries_at(pkg):
            already.update(e.get("related_invariants") or [])
        cands = []
        for L in _LAYER_DIRS:
            inv_dir = pkg / L / "invariants"
            if not inv_dir.is_dir():
                continue
            for yp in sorted(inv_dir.glob("*.yaml")):
                data = yaml_io.read(yp)
                if not isinstance(data, dict):
                    continue
                evidence = str(data.get("evidence") or "").strip()
                if not evidence:
                    continue
                classes = sorted(parse_evidence_classes(evidence))
                if not classes:
                    continue
                name = str(data.get("name") or yp.stem)
                tag, cvar = suggest_names(doc.domain, name)
                is_reg = name in already
                registered_n += 1 if is_reg else 0
                cands.append({"invariant": name, "evidence": evidence,
                              "classes": classes, "layer": data.get("layer", L),
                              "suggested_tag": tag, "suggested_cvar": cvar,
                              "registered": is_reg})
        if cands:
            by_domain[doc.domain] = cands
            total += len(cands)
    return {"by_domain": by_domain,
            "counts": {"total": total, "domains": len(by_domain),
                       "registered": registered_n}}


def render_md(result: dict, *, generated: str) -> str:
    c = result["counts"]
    lines = [
        "---",
        f"generated: {generated}",
        "kind: log_tagging_candidates_report",
        "---",
        "",
        "# 태깅 권장 지점 (제안 — 게임팀 전달용, 자동 등록 안 함)",
        "",
        f"> invariant evidence 기반 후보 **{c['total']}건** ({c['domains']}개 도메인, "
        f"확정 등록됨 {c['registered']}건 포함). 실증 테스트(η.12.3)를 위해 이 지점에 "
        "CVar+태깅 로그를 추가하면 좋다는 제안이며, 실제 이름·구현은 게임팀 재량.",
        "> 게임팀이 실제로 구현한 뒤에는 `python -m master.ontology log-tags <도메인> set "
        "<tag> <cvar> [invariant...]` 로 확정 기입 — 여기 목록은 참고용 기본 제안일 뿐, "
        "자동 등록되지 않는다.",
        "",
    ]
    by_domain = result["by_domain"]
    if not by_domain:
        lines += ["_evidence 기반 태깅 후보 없음._", ""]
        return "\n".join(lines).rstrip() + "\n"
    for domain in sorted(by_domain):
        lines.append(f"## {domain}")
        for x in by_domain[domain]:
            classes = ", ".join(f"`{k}`" for k in x["classes"])
            mark = " **[확정 등록됨]**" if x["registered"] else ""
            lines.append(
                f"- `{x['invariant']}` ({x['layer']}){mark} — {classes}\n"
                f"  - evidence: {x['evidence']}\n"
                f"  - 권장 tag: `{x['suggested_tag']}` / 권장 cvar: `{x['suggested_cvar']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate(paths, *, now: datetime | None = None) -> dict:
    """후보를 계산해 `<트윈>/ontology/_log_tagging_candidates.md` 작성. 반환: counts."""
    now = now or datetime.now()
    result = compute(paths)
    out = Path(paths.ontology) / OUTPUT_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_md(result, generated=now.isoformat(timespec="seconds")),
                   encoding="utf-8")
    return {**result["counts"], "path": str(out)}
