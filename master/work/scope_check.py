from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

_HUNK_HEADER_RE = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
)
_IMPORT_RE = re.compile(
    r"^(?:import\s+[A-Za-z_][\w.]*(?:\s+as\s+[A-Za-z_]\w*)?(?:\s*,\s*[A-Za-z_][\w.]*(?:\s+as\s+[A-Za-z_]\w*)?)*"
    r"|from\s+[A-Za-z_.][\w.]*\s+import\s+.+)$"
)


@dataclass
class ScopeReport:
    out_of_scope_count: int = 0
    by_kind: dict[str, int] = field(
        default_factory=lambda: {"other": 0, "import": 0, "comment": 0}
    )
    details: list[str] = field(default_factory=list)

    def render_line(self) -> str:
        if self.out_of_scope_count == 0:
            return ""
        parts = [
            f"{kind} {self.by_kind.get(kind, 0)}"
            for kind in ("other", "import", "comment")
            if self.by_kind.get(kind, 0) > 0
        ]
        breakdown = " · ".join(parts)
        return f"범위 밖 변경 덩어리 {self.out_of_scope_count}건 ({breakdown})"


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s[0], s[1]))
    merged: list[tuple[int, int]] = [sorted_spans[0]]
    for start, end in sorted_spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def find_pseudo_spans(source: str) -> list[tuple[int, int]]:
    if not source:
        return []

    lines = source.splitlines()
    pseudo_lines = [
        idx for idx, line in enumerate(lines, start=1) if "[PSEUDO]" in line
    ]
    if not pseudo_lines:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _merge_spans([(ln, ln) for ln in pseudo_lines])

    block_nodes: list[ast.AST] = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
    ]

    raw_spans: list[tuple[int, int]] = []
    for ln in pseudo_lines:
        enclosing: list[tuple[int, int]] = []
        for node in block_nodes:
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            if start <= ln <= end:
                enclosing.append((start, end))

        if enclosing:
            innermost = min(enclosing, key=lambda s: (s[1] - s[0], -s[0]))
            raw_spans.append(innermost)
            continue

        matched_top = False
        for stmt in tree.body:
            stmt_start = stmt.lineno
            stmt_end = getattr(stmt, "end_lineno", None) or stmt_start
            if stmt_start <= ln <= stmt_end:
                raw_spans.append((min(ln, stmt_start), stmt_end))
                matched_top = True
                break
            if stmt_start > ln:
                raw_spans.append((ln, stmt_end))
                matched_top = True
                break

        if not matched_top:
            raw_spans.append((ln, ln))

    return _merge_spans(raw_spans)


def parse_diff_hunks(diff_text: str) -> list[dict]:
    if not diff_text:
        return []

    hunks: list[dict] = []
    current: dict | None = None
    old_cursor = 0

    for raw_line in diff_text.splitlines():
        m = _HUNK_HEADER_RE.match(raw_line)
        if m:
            if current is not None:
                _finalize_hunk(current)
                hunks.append(current)
            old_start = int(m.group(1))
            old_len = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_len = int(m.group(4)) if m.group(4) is not None else 1
            current = {
                "header": raw_line,
                "old_start": old_start,
                "old_len": old_len,
                "new_start": new_start,
                "new_len": new_len,
                "added": [],
                "deleted": [],
                "lines": [],
                "_touched_old_lines": [],
            }
            old_cursor = old_start
            continue

        if current is None:
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue

        if raw_line.startswith("+"):
            content = raw_line[1:]
            current["added"].append(content)
            current["lines"].append(raw_line)
            anchor = old_cursor if old_cursor >= current["old_start"] else current["old_start"]
            if current["old_len"] == 0:
                current["_touched_old_lines"].append(current["old_start"])
            else:
                current["_touched_old_lines"].append(
                    min(anchor, current["old_start"] + max(current["old_len"] - 1, 0))
                )
        elif raw_line.startswith("-"):
            content = raw_line[1:]
            current["deleted"].append(content)
            current["lines"].append(raw_line)
            current["_touched_old_lines"].append(old_cursor)
            old_cursor += 1
        elif raw_line.startswith(" "):
            current["lines"].append(raw_line)
            old_cursor += 1
        elif raw_line.startswith("\\"):
            continue

    if current is not None:
        _finalize_hunk(current)
        hunks.append(current)

    return hunks


def _finalize_hunk(hunk: dict) -> None:
    touched = hunk.pop("_touched_old_lines", [])
    if touched:
        hunk["effective_old_start"] = min(touched)
        hunk["effective_old_end"] = max(touched)
    else:
        old_start = hunk["old_start"]
        old_len = hunk["old_len"]
        hunk["effective_old_start"] = old_start
        hunk["effective_old_end"] = (
            old_start if old_len == 0 else old_start + old_len - 1
        )


def _is_import_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
        if not stripped:
            return False
    return bool(_IMPORT_RE.match(stripped))


def _is_comment_or_docstring_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if (
        (stripped.startswith('"""') and stripped.endswith('"""') and len(stripped) >= 6)
        or (stripped.startswith("'''") and stripped.endswith("'''") and len(stripped) >= 6)
        or stripped in ('"""', "'''")
    ):
        return True
    return False


def classify_hunk(hunk: dict) -> str:
    changed = list(hunk.get("added", [])) + list(hunk.get("deleted", []))
    non_ws = [line for line in changed if line.strip()]

    if not non_ws:
        return "comment"

    if all(_is_comment_or_docstring_line(line) for line in non_ws):
        return "comment"

    if all(_is_import_line(line) for line in non_ws):
        return "import"

    return "other"


def check_scope(
    base_source: str, diff_text: str, filename: str = ""
) -> ScopeReport:
    report = ScopeReport()
    hunks = parse_diff_hunks(diff_text)
    if not hunks:
        return report

    spans = find_pseudo_spans(base_source)
    prefix = f"{filename}:" if filename else ""

    for hunk in hunks:
        h_start = hunk.get("effective_old_start", hunk["old_start"])
        h_end = hunk.get(
            "effective_old_end",
            hunk["old_start"] + max(hunk["old_len"] - 1, 0),
        )

        in_scope = any(
            span_start <= h_start and h_end <= span_end
            for span_start, span_end in spans
        )
        if in_scope:
            continue

        kind = classify_hunk(hunk)
        report.out_of_scope_count += 1
        report.by_kind[kind] = report.by_kind.get(kind, 0) + 1
        report.details.append(f"{prefix}L{h_start}-{h_end} ({kind})")

    return report
