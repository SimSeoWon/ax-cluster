"""소비자 history_harvest (#158) — 원전 `watcher/history_harvest.py` 755줄의 이식.

`.claude/history`(8필드 frontmatter md) + `.gemini/history`(6섹션 task report txt) 통합
read-only 파서. 생산자③(`history_gen.py`)이 쓰는 기록과 사용자 프로젝트에서 받아온 기록을
HistoryRecord 로 정규화해, 온톨로지 측 LLM 프롬프트의 narrative 컨텍스트로 쓰인다.

설계 정신 (원전 머리말 그대로):
    - PyYAML 의존성 0 — 정규식 + stdlib 만
    - 자동 migration 금지 — read-only 소비
    - 사용자 영역 자동 수정 X — Gemini 6-섹션 그대로 보존, 파서가 적응
    - 본 모듈은 데이터 추출만 — 첨부·소비는 온톨로지 쪽 (원전 η.8.2)

우리 위상 (원전 배포 프로젝트의 `.claude/history`·`.gemini/history` 대응):
    claude 측   `{root}/history/`         — 생산자③ 출력 + .33 에서 받아온 세션 기록 (같은 규약)
    gemini 측   `{root}/history_gemini/`  — .33 의 `.gemini/history` 받아온 사본 (read-only)
    [주의] 두 디렉토리는 클론(`repo/`) 밖이다 — 원전 프로젝트에서 `.claude/` 는 gitignore 라
    클론으로는 안 넘어온다 (실측: check-ignore 확인).

원전과의 차이: audit 의 도메인 원천이 class_graph DB 가 아니라 **온톨로지 YAML** 이다 —
우리 class_graph.db 의 domains/class_ontology 테이블은 비어 있고(실측), 도메인 멤버십은
`ontology/domains/<D>/L*/objects/*.yaml` 이 정본이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_LOG = lambda msg: None    # noqa: E731 — set_log 로 주입 (원전 common.log 자리)


def set_log(fn) -> None:
    global _LOG
    _LOG = fn or (lambda msg: None)


# ─────────────────────────────────────────────────────────────────
# 데이터 모델
# ─────────────────────────────────────────────────────────────────

@dataclass
class HistoryRecord:
    """통합 dict 스키마 — Claude/Gemini 양측 파서가 같은 키를 채워 후속 소비자는 source 무관."""
    source: str       # "claude" | "gemini"
    path: str         # 원본 파일 경로
    date: str         # YYYY-MM-DD (시간은 잘림)
    decision_type: str
    affected_classes: list = field(default_factory=list)
    affected_domains: list = field(default_factory=list)
    summary: str = ""              # WHY / 의도 단락 (cap 500자)
    flow_narrative: str = ""       # 흐름·변경 narrative (cap 1500자)
    next_steps: list = field(default_factory=list)
    raw_excerpt: str = ""          # LLM 프롬프트 첨부용 통합 발췌 (cap 1500자)
    # ── 세션이 되읽는 데 필요한 필드 (`#306`) — **뒤에 덧붙였다.** 기존 소비자(온톨로지 시드,
    #    `#158`)는 읽는 것만 읽으므로 추가는 안전하고, 파서를 두 벌로 쓰지 않기 위해서다
    #    (`#303` 의 `_stamp_fields` 와 같은 판단: 같은 규칙은 한 자리에서만).
    title: str = ""                # 본문 첫 `# ` 제목 — `log_history` 의 필수 인자였던 것
    tags: list = field(default_factory=list)
    alternatives_considered: list = field(default_factory=list)   # next_steps 와 갈라 보관
    supersedes: str = ""           # 뒤집힌 결정을 따라가는 축 — 이것 없이는 drift 를 못 쫓는다
    work_id: str = ""
    session_id: str = ""


# ─────────────────────────────────────────────────────────────────
# filename prefix → decision_type 매핑
# ─────────────────────────────────────────────────────────────────

# 원전 실측 (ModularStage `.gemini/history` 37 파일, 2026-05-30) prefix 분포 기반.
# 매칭 안 되는 prefix 는 "feature" fallback + 카나리 로그.
_PREFIX_DECISION_MAP: dict = {
    "Feature": "feature",
    "Fix": "bugfix",
    "Architectural": "architecture",
    "ArchitecturalShift": "architecture",
    "Design": "architecture",
    "MCP": "infra",
    "Manager": "architecture",
    "Refactor": "refactor",
    "Analysis": "experiment",
    "History": "infra",       # consolidation logs
    "Task": "feature",
    "UI": "feature",
}


def _prefix_to_decision_type(filename: str) -> tuple:
    """파일명 첫 `_` 토큰 → decision_type. 매칭 X 면 ("feature", True, prefix) fallback."""
    stem = filename.split(".")[0]
    prefix = stem.split("_")[0]
    if prefix in _PREFIX_DECISION_MAP:
        return _PREFIX_DECISION_MAP[prefix], False, prefix
    return "feature", True, prefix


# 원전 σ.15 — unknown prefix 카나리 process-level dedupe (66라인 노이즈 실측 후).
_LOGGED_UNKNOWN_PREFIXES: set = set()


def reset_unknown_prefix_dedupe() -> None:
    """테스트용 dedupe set 리셋."""
    global _LOGGED_UNKNOWN_PREFIXES
    _LOGGED_UNKNOWN_PREFIXES = set()


# ─────────────────────────────────────────────────────────────────
# 경로 → 클래스 stem 추출
# ─────────────────────────────────────────────────────────────────

_PATH_CLASS_RE = re.compile(r"([A-Z][A-Za-z0-9_]+?)\.(?:h|cpp)\b")


def _extract_classes_from_paths(paths: list) -> list:
    """파일 경로 list → 클래스 stem list (입력 순서 보존, dup 제거)."""
    out: list = []
    seen: set = set()
    for p in paths:
        for m in _PATH_CLASS_RE.finditer(p):
            stem = m.group(1)
            if stem not in seen:
                seen.add(stem)
                out.append(stem)
    return out


def _infer_domains_from_paths(paths: list) -> list:
    """`Source/<Module>/<SubDir>/X.h` 패턴에서 SubDir 추출 (보수적 도메인 단서)."""
    domains: set = set()
    for p in paths:
        parts = p.replace("\\", "/").strip().split("/")
        if "Source" not in parts:
            continue
        idx = parts.index("Source")
        if idx + 2 < len(parts):
            subdir = parts[idx + 2]
            if not subdir.endswith((".h", ".cpp")):
                domains.add(subdir)
    return sorted(domains)


# ─────────────────────────────────────────────────────────────────
# Claude 측 — 8-필드 frontmatter (PyYAML 의존성 0 mini-parser)
# ─────────────────────────────────────────────────────────────────

_FM_BOUNDARY_RE = re.compile(r"^---\s*$", re.M)
_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _scalar_value(s: str):
    """인라인 스칼라 역파싱 — null / bool / quoted string / plain."""
    s = s.strip()
    if not s:
        return ""
    if s.lower() == "null":
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _parse_simple_frontmatter(fm_text: str) -> dict:
    """8필드 frontmatter mini-parser (원전 글자대로 — `history_gen` 의 emission 짝)."""
    result: dict = {}
    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.strip().startswith("#"):
            i += 1
            continue
        if ln.startswith(" "):
            i += 1
            continue
        m = _FM_KEY_RE.match(ln)
        if not m:
            i += 1
            continue
        key = m.group(1)
        val_raw = m.group(2).strip()

        if val_raw == "|" or val_raw == ">":
            i += 1
            block_lines: list = []
            while i < len(lines):
                nl = lines[i]
                if not nl.strip():
                    block_lines.append("")
                    i += 1
                    continue
                if not nl.startswith(" "):
                    break
                block_lines.append(nl.lstrip())
                i += 1
            result[key] = "\n".join(block_lines).strip()
            continue

        if val_raw:
            result[key] = _scalar_value(val_raw)
            i += 1
            continue

        i += 1
        list_items: list = []
        while i < len(lines):
            nl = lines[i]
            if not nl.strip():
                i += 1
                continue
            if not nl.startswith(" "):
                break
            stripped = nl.lstrip()
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if (item.startswith('"') and item.endswith('"')) or \
                   (item.startswith("'") and item.endswith("'")):
                    item = item[1:-1]
                list_items.append(item)
            i += 1
        result[key] = list_items
    return result


def _first_paragraph(text: str) -> str:
    """첫 비어있지 않은 단락 (헤더 라인 제외)."""
    for p in re.split(r"\n\s*\n", text.strip()):
        p = p.strip()
        if p and not p.startswith("#"):
            return p
    return ""


def _extract_md_section(body: str, section_names: list) -> str:
    """Markdown `## <name>` 섹션 본문 추출. 첫 매칭만, 다음 ## 까지."""
    for name in section_names:
        pattern = (
            rf"^#{{1,3}}\s*\d*\.?\s*{re.escape(name)}\s*\n"
            rf"(.+?)(?=^#{{1,3}}\s|\Z)"
        )
        m = re.search(pattern, body, re.M | re.S)
        if m:
            return m.group(1).strip()
    return ""


def parse_claude_history(path: Path) -> Optional[HistoryRecord]:
    """Claude 측 .md → HistoryRecord. frontmatter 부재 / boundary 못 찾으면 None."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        _LOG(f"[history harvest] read fail path={path}")
        return None

    fm_match = _FM_BOUNDARY_RE.search(text)
    if not fm_match or fm_match.start() > 100:
        return None
    end_match = _FM_BOUNDARY_RE.search(text, fm_match.end() + 1)
    if not end_match:
        return None
    fm_text = text[fm_match.end():end_match.start()]
    body = text[end_match.end():].strip()

    fm = _parse_simple_frontmatter(fm_text)

    date_raw = str(fm.get("date") or "")
    date = date_raw.split(" ")[0] if date_raw else ""

    affected_classes = fm.get("affected_classes") or []
    if not isinstance(affected_classes, list):
        affected_classes = []
    affected_domains = fm.get("affected_domains") or []
    if not isinstance(affected_domains, list):
        affected_domains = []

    decision_type = str(fm.get("decision_type") or "feature")

    user_quote = str(fm.get("user_quote") or "").strip()
    summary = user_quote if user_quote else _first_paragraph(body)

    flow_narrative = _extract_md_section(body, [
        "주요 설계 결정", "작업 개요", "흐름", "변경 내용", "Changes",
    ])
    if not flow_narrative:
        flow_narrative = body[:1500]

    next_steps: list = []
    alt = fm.get("alternatives_considered") or []
    if isinstance(alt, list):
        next_steps.extend(str(x) for x in alt if x)
    follow = _extract_md_section(body, [
        "후속 작업", "후속", "다음 단계", "Next Steps", "후속 작업 / 미해결 검토",
    ])
    if follow:
        for ln in follow.splitlines():
            ln = ln.strip()
            m = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", ln)
            if m:
                next_steps.append(m.group(1).strip())

    tags = fm.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    alternatives = [str(x) for x in alt if x] if isinstance(alt, list) else []
    supersedes = str(fm.get("supersedes") or "").strip()
    title = ""
    for ln in body.splitlines():
        if ln.startswith("# "):
            title = ln[2:].strip()
            break

    raw_excerpt_parts = [user_quote, flow_narrative]
    raw_excerpt = "\n\n".join(p for p in raw_excerpt_parts if p)[:1500].strip()

    return HistoryRecord(
        source="claude",
        path=str(path),
        date=date,
        decision_type=decision_type,
        affected_classes=[str(x) for x in affected_classes],
        affected_domains=[str(x) for x in affected_domains],
        summary=summary[:500],
        flow_narrative=flow_narrative[:1500],
        next_steps=next_steps,
        raw_excerpt=raw_excerpt,
        title=title,
        tags=[str(x) for x in tags],
        alternatives_considered=alternatives,
        supersedes=supersedes,
        work_id=str(fm.get("work_id") or "").strip(),
        session_id=str(fm.get("session_id") or "").strip(),
    )


# ─────────────────────────────────────────────────────────────────
# Gemini 측 — Format A (## headers) / B (plain) / C (analysis)
# ─────────────────────────────────────────────────────────────────

_GEMINI_SECTION_NAMES = (
    "Date", "Task", "Overview", "Changes",
    "Key Files Affected", "Architectural Impact",
    "Performance Notes", "Next Steps",
)

_GEMINI_SECTION_ALIAS_MAP = {
    "New Files": "Key Files Affected",
    "Modified Files": "Key Files Affected",
}
_GEMINI_EXTRA_SECTION_NAMES = tuple(_GEMINI_SECTION_ALIAS_MAP.keys())

_GEMINI_HEADER_RE = re.compile(
    r"^(?:#{1,3}\s*|=={1,3}\s*)?"
    r"(" + "|".join(re.escape(n) for n in _GEMINI_SECTION_NAMES + _GEMINI_EXTRA_SECTION_NAMES) + r")"
    r"(?:\s*\(\d+\))?"
    r"(?:\s*={1,3})?"
    r"\s*:?\s*(.*)$",
    re.M,
)

_GEMINI_DATE_VALUE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_BODY_PATH_RE = re.compile(
    r"\b((?:Source|Plugins|Content|Public|Private)[/\\][^\s`*()\[\]]+?\.(?:h|cpp|cs))\b"
)


def _parse_gemini_sections(text: str) -> dict:
    """Format A/B/D 통합 — 헤더 라인 위치로 본문 분할. Alias 자동 병합."""
    sections: dict = {}
    matches = list(_GEMINI_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1)
        name = _GEMINI_SECTION_ALIAS_MAP.get(name, name)
        first_line_val = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        chunk = first_line_val + "\n" + body if first_line_val and body else (
            first_line_val or body
        )
        if name in sections and chunk:
            sections[name] = sections[name] + "\n" + chunk
        else:
            sections[name] = chunk
    return sections


def parse_gemini_history(path: Path) -> Optional[HistoryRecord]:
    """Gemini 측 .txt → HistoryRecord. Format A/B 지원, C 는 best-effort."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        _LOG(f"[history harvest] read fail path={path}")
        return None

    decision_type, unknown, prefix_token = _prefix_to_decision_type(path.name)
    if unknown and prefix_token not in _LOGGED_UNKNOWN_PREFIXES:
        _LOGGED_UNKNOWN_PREFIXES.add(prefix_token)
        _LOG(
            f"[history harvest] unknown prefix={prefix_token!r} "
            f"(예: {path.name}) — feature 로 분류 (같은 prefix 후속은 silent)"
        )

    sections = _parse_gemini_sections(text)

    date = ""
    date_section = sections.get("Date", "")
    if date_section:
        m = _GEMINI_DATE_VALUE_RE.search(date_section)
        if m:
            date = m.group(1)
    if not date:
        head = text[:200]
        m = _GEMINI_DATE_VALUE_RE.search(head)
        if m:
            date = m.group(1)

    overview = sections.get("Overview", "")
    changes = sections.get("Changes", "")
    key_files = sections.get("Key Files Affected", "")
    impact = sections.get("Architectural Impact", "") or sections.get("Performance Notes", "")
    next_steps_text = sections.get("Next Steps", "")

    file_paths: list = []
    for ln in key_files.splitlines():
        ln = ln.strip()
        if ln.startswith("- "):
            ln = ln[2:].strip()
        ln = re.sub(r"\s*\([^)]*\)\s*$", "", ln).strip()
        ln = ln.strip("`").rstrip()
        if ln and ("/" in ln or "\\" in ln) and ln.endswith((".h", ".cpp", ".cs")):
            file_paths.append(ln)

    if not file_paths:
        body_paths = _BODY_PATH_RE.findall(text)
        seen: set = set()
        for p in body_paths:
            if p not in seen:
                seen.add(p)
                file_paths.append(p)

    affected_classes = _extract_classes_from_paths(file_paths)
    affected_domains = _infer_domains_from_paths(file_paths)

    next_steps: list = []
    for ln in next_steps_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", ln)
        if m:
            next_steps.append(m.group(1).strip())
        elif ln and not ln.endswith(":"):
            next_steps.append(ln)

    flow_parts: list = []
    if changes:
        flow_parts.append(f"[Changes]\n{changes}")
    if impact:
        flow_parts.append(f"[Architectural Impact]\n{impact}")
    flow_narrative = "\n\n".join(flow_parts)

    # Format C (Analysis_* 등) best-effort — sections 거의 비어있으면 본문 fallback
    if not sections or (not overview and not changes and not key_files):
        backtick_paths = re.findall(r"`([^`]+\.(?:h|cpp))`", text)
        if backtick_paths:
            file_paths.extend(backtick_paths)
            affected_classes = _extract_classes_from_paths(file_paths)
        first_header_end = text.find("\n")
        body_only = text[first_header_end:] if first_header_end > 0 else text
        first_para = _first_paragraph(body_only)
        if not overview:
            overview = first_para
        if not flow_narrative:
            flow_narrative = body_only.strip()[:1500]

    raw_excerpt_parts = [overview, flow_narrative]
    raw_excerpt = "\n\n".join(p for p in raw_excerpt_parts if p)[:1500].strip()

    return HistoryRecord(
        source="gemini",
        path=str(path),
        date=date,
        decision_type=decision_type,
        affected_classes=affected_classes,
        affected_domains=affected_domains,
        summary=overview[:500],
        flow_narrative=flow_narrative[:1500],
        next_steps=next_steps,
        raw_excerpt=raw_excerpt,
    )


# ─────────────────────────────────────────────────────────────────
# 통합 walk + 필터링
# ─────────────────────────────────────────────────────────────────

def walk_histories(claude_dir: Optional[Path] = None,
                   gemini_dir: Optional[Path] = None) -> list:
    """두 디렉토리 통합 walk. 경로 부재 / 파싱 실패 한 파일은 silent skip.

    Returns: date DESC 정렬된 HistoryRecord list (빈 date 는 최후순).
    """
    records: list = []
    if claude_dir and claude_dir.exists():
        for p in sorted(claude_dir.glob("*.md")):
            if p.name.startswith("_"):
                continue
            rec = parse_claude_history(p)
            if rec:
                records.append(rec)
    if gemini_dir and gemini_dir.exists():
        for p in sorted(gemini_dir.glob("*.txt")):
            rec = parse_gemini_history(p)
            if rec:
                records.append(rec)
    records.sort(
        key=lambda r: (r.date or "0000-00-00", r.path),
        reverse=True,
    )
    return records


# UE 식 prefix (UCLASS/AActor/USTRUCT F/IInterface/Enum E/Slate S/TArray T/Delegate D).
_UE_PREFIX_RE = re.compile(r"^[UAFIESBD]")


def _strip_ue_prefix(name: str) -> str:
    """UE 식 prefix 한 글자 제거. 'UManager_Mission' → 'Manager_Mission'. 단글자는 보존."""
    if len(name) < 2:
        return name
    return _UE_PREFIX_RE.sub("", name, count=1)


def filter_for_classes(records: list, class_names: set, *,
                       limit: int = 5, per_record_chars: int = 1500,
                       prefix_tolerant: bool = True) -> list:
    """class_names 와 교집합 있는 record 만, 최신순, 최대 limit 건.

    prefix_tolerant: history 의 affected_classes 는 path stem(`Manager_TableData`)이고
    온톨로지는 prefix 포함(`UManager_TableData`)이라 stem-tolerant 매칭이 기본이다 (원전 실측).
    """
    if not class_names or not records:
        return []
    if prefix_tolerant:
        target_stems = {_strip_ue_prefix(n) for n in class_names}
        matched = [
            r for r in records
            if {_strip_ue_prefix(c) for c in r.affected_classes} & target_stems
        ]
    else:
        matched = [r for r in records if set(r.affected_classes) & class_names]
    matched.sort(key=lambda r: r.date or "0000-00-00", reverse=True)
    out = matched[:limit]
    for r in out:
        if len(r.raw_excerpt) > per_record_chars:
            r.raw_excerpt = r.raw_excerpt[:per_record_chars] + "..."
    return out


def project_history_dirs(paths) -> tuple:
    """우리 트윈의 두 history 디렉토리 (원전 `.claude/history`·`.gemini/history` 자리)."""
    root = Path(paths.root)
    return (root / "history", root / "history_gemini")


# ─────────────────────────────────────────────────────────────────
# 세션이 되읽는 표면 (`#306`)
#
# [중요] **읽는 기계는 이미 있었다.** `walk_histories`·`parse_claude_history`·
#    `filter_for_classes` 는 온톨로지 시드(`#158`)를 위해 이식돼 있었고, 없던 것은
#    **세션이 부를 자리**다. 그래서 여기서 파서를 새로 쓰지 않는다 — 위의 것을 그대로 쓴다.
# [주의] `log_history` 는 **쓰기만** 있었다. 쓰기만 있는 기록은 다음 세션에게 없는 것과 같다
#    (실측 2026-08-24: `.33` 세션이 자기가 남긴 기록을 못 찾아 *"없다"* 고 판단했다).
# ─────────────────────────────────────────────────────────────────

def _row(rec, *, excerpt_chars: int) -> dict:
    """세션이 읽을 한 줄. [중요] **원본 json 을 그대로 흘리지 않는다** — 컨텍스트를 아끼고,
    필드 이름이 절차 문서(`log_history` 인자)와 같게 유지한다(`redmine._issue_row` 와 같은 규약)."""
    return {
        "path": Path(rec.path).name,          # [주의] 절대경로를 내보내지 않는다 — 마스터 디스크 구조다
        "date": rec.date,
        "title": rec.title,
        "decision_type": rec.decision_type,
        "affected_classes": rec.affected_classes,
        "affected_domains": rec.affected_domains,
        "tags": rec.tags,
        "alternatives_considered": rec.alternatives_considered,
        "supersedes": rec.supersedes,
        "work_id": rec.work_id,
        "summary": (rec.summary or "")[:excerpt_chars],
        "next_steps": rec.next_steps,
        "source": rec.source,
    }


def _hay(rec) -> str:
    """자유 질의가 훑을 텍스트. [주의] 본문 전체가 아니라 **발췌까지**다 — 파일을 다 읽어
    grep 하면 느려지고, 정작 필요한 것은 프론트매터와 요지다."""
    return " ".join([rec.title, rec.summary, rec.flow_narrative,
                     " ".join(rec.tags), " ".join(rec.affected_classes),
                     " ".join(rec.affected_domains),
                     " ".join(rec.alternatives_considered)]).lower()


def search(paths, *, query: str = "", decision_type: str = "", classes=(),
           tags=(), supersedes_only: bool = False, limit: int = 10,
           excerpt_chars: int = 500) -> dict:
    """트윈의 history 를 조건으로 훑는다. 반환 `{"count", "total", "records", "dir"}`.

    필터는 **AND** 다 — 좁히려고 여러 축을 주는 것이므로. 빈 축은 조건이 아니다.
    `classes` 는 `filter_for_classes` 와 같은 **prefix 관용** 매칭이다(`UManager_X` ↔ `Manager_X`);
    두 자리가 다른 규칙을 쓰면 같은 질문에 다른 답이 나온다.

    [중요] **없으면 없다고 말한다** — 빈 목록 + `dir`(어디를 봤는가)을 함께 돌려준다. 0건과
    「디렉토리를 못 찾았다」는 다르고, 그 차이가 안 보이면 다음 세션이 또 「기록이 없다」고 읽는다.
    """
    cdir, gdir = project_history_dirs(paths)
    recs = walk_histories(cdir, gdir)
    total = len(recs)
    if decision_type:
        recs = [r for r in recs if r.decision_type == decision_type]
    if classes:
        recs = filter_for_classes(recs, set(classes), limit=max(1, int(limit)),
                                  per_record_chars=excerpt_chars)
    if tags:
        want = {str(t).strip().lower() for t in tags if str(t).strip()}
        recs = [r for r in recs if {t.lower() for t in r.tags} & want]
    if supersedes_only:
        recs = [r for r in recs if r.supersedes]
    if query:
        q = str(query).strip().lower()
        recs = [r for r in recs if q in _hay(r)]
    out = recs[:max(1, int(limit))]
    return {"count": len(out), "total": total, "dir": str(cdir),
            "exists": cdir.is_dir(),
            "records": [_row(r, excerpt_chars=excerpt_chars) for r in out]}


# ─────────────────────────────────────────────────────────────────
# startup audit (도메인 coverage, read-only — 원전 η.8.5)
# ─────────────────────────────────────────────────────────────────

def ontology_domain_members(paths) -> dict:
    """{도메인: {멤버 클래스}} — 온톨로지 YAML 이 정본 (원전 class_graph DB 자리).

    멤버 = `ontology/domains/<D>/L*/objects/*.yaml` 의 파일명 stem.
    """
    out: dict = {}
    droot = Path(paths.ontology) / "domains"
    if not droot.is_dir():
        return out
    for d in sorted(droot.iterdir()):
        if not d.is_dir():
            continue
        members = {f.stem for f in d.glob("L*/objects/*.yaml")}
        out[d.name] = members
    return out


def audit_coverage(paths) -> dict:
    """active 도메인별 history 매칭 coverage 진단. read-only — 자동 수정 X."""
    out: dict = {
        "total_domains": 0,
        "matched_domains": 0,
        "unmatched": [],
        "per_domain": {},
        "total_records": 0,
        "claude_count": 0,
        "gemini_count": 0,
    }

    domains = ontology_domain_members(paths)
    if not domains:
        return out

    claude_dir, gemini_dir = project_history_dirs(paths)
    if not claude_dir.exists() and not gemini_dir.exists():
        out["total_domains"] = len(domains)
        out["unmatched"] = sorted(domains)
        return out

    records = walk_histories(claude_dir, gemini_dir)
    out["total_records"] = len(records)
    out["claude_count"] = sum(1 for r in records if r.source == "claude")
    out["gemini_count"] = sum(1 for r in records if r.source == "gemini")

    for dom_name, member_classes in domains.items():
        if not member_classes:
            out["per_domain"][dom_name] = 0
            continue
        matched = filter_for_classes(
            records, member_classes,
            limit=len(records) or 1, per_record_chars=1,
        )
        out["per_domain"][dom_name] = len(matched)

    out["total_domains"] = len(domains)
    out["matched_domains"] = sum(1 for v in out["per_domain"].values() if v > 0)
    out["unmatched"] = sorted(
        d for d, n in out["per_domain"].items() if n == 0
    )
    return out


def log_history_audit(paths) -> dict:
    """audit 실행 + 카나리 로그 (원전 watch.py startup 진입점의 우리 자리)."""
    result = audit_coverage(paths)
    if result["total_records"] == 0 and result["total_domains"] == 0:
        return result
    if result["total_records"] == 0:
        _LOG(
            f"[history audit] records=0 — history 디렉토리 부재/빈 "
            f"(domains={result['total_domains']} 모두 미매칭)"
        )
        return result
    parts = [
        f"records={result['total_records']}",
        f"(claude={result['claude_count']}, gemini={result['gemini_count']})",
        f"coverage={result['matched_domains']}/{result['total_domains']}",
    ]
    if result["unmatched"]:
        parts.append(f"미매칭={result['unmatched']}")
    _LOG("[history audit] " + " ".join(parts))
    return result


def main(argv=None) -> int:
    from ..context_search.paths import resolve
    set_log(print)
    paths = resolve("")
    r = log_history_audit(paths)
    claude_dir, gemini_dir = project_history_dirs(paths)
    print(f"claude={claude_dir} · gemini={gemini_dir}")
    print(r)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
