"""도메인 MD 파싱 — 재합성의 입력 (소 1.3.3 의 결정적 부분, LLM 0).

원본: `watcher/ontology_md_parse.py` 의 `parse_domain_md` · `_extract_list_items` ·
`_parse_boundary`.

## 🔴 원본 파서를 그대로 옮기면 6/7 도메인이 조용히 빈 결과가 된다

원본은 섹션 이름 6개를 **고정 정규식**으로 찾는다 — `## 시스템 개요` · `## 핵심 책임` ·
`## 도메인 경계` · `## 핵심 invariants` · `## 협력 도메인` · `## 사용자 의도 메모`.

받아온 실물을 세어 보니 그 스키마를 쓰는 것은 **`MissionEditor` 하나뿐**이었다
(실측 2026-08-09):

    MissionEditor                  시스템 개요 · 핵심 책임 · 도메인 경계 · 핵심 invariants
                                   · 협력 도메인 · 사용자 의도 메모      ← 원본 스키마
    나머지 6개                      시스템 개요 · 핵심 구현 패턴 · 확장 포인트   ← 다른 스키마

원본 파서를 옮겼으면 6개 도메인에서 `responsibilities=[]` · `boundary=[]` · `invariants=[]`
가 나오고, **파싱은 "성공"으로 보고된다.** 그 상태로 합성하면 근거가 반쪽인 문서가 생기고
아무도 모른다. 이 저장소가 반복해서 잡아온 그 모양이다 — `is_empty` 필터가 문서 149건을
버린 것, `_slugify` 가 한글을 전멸시킨 것과 같은 계열.

## 그래서 이렇게 한다

**섹션을 먼저 전부 읽고, 아는 이름만 골라 쓴다.** 모르는 섹션은 버리지 않고
`extra` 에 남긴다 — `## 핵심 구현 패턴` 은 액션 추출의 **가장 강한 신호**다.
고정 스키마를 강요하는 대신 있는 것을 쓴다.

🔴 그리고 **무엇이 없었는지 결과에 적는다**(`missing`). 결손을 숨기면 다음 세션이
"원래 이 도메인은 책임이 없나 보다" 로 읽는다 — 매니페스트 결손 명시와 같은 규칙이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import yaml_io

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
_LIST_ITEM = re.compile(r"^\s*-\s+(.+?)\s*$", re.M)

# 아는 섹션 이름 → 필드. 🔴 **둘 다 실물에 존재하는 스키마다** (위 독스트링 실측).
# 공백 차이를 흡수하려고 정규화 후 비교한다(`핵심 invariants` ↔ `핵심invariants`).
_CANON = {
    "시스템개요": "summary",
    "핵심책임": "responsibilities",
    "도메인경계": "boundary",
    "핵심invariants": "invariants",
    "협력도메인": "collaborators",
    "사용자의도메모": "intent_notes",
}

# 🔴 원본에 없는 매핑 — 우리 실물 6/7 이 쓰는 스키마. 버리면 근거가 사라진다.
#   `핵심 구현 패턴` → 액션 추출의 최강 신호 (누가 무엇을 어떤 순서로)
#   `확장 포인트`    → 경계 신호 (어디까지가 이 도메인인가)
_CANON_EXTRA = {
    "핵심구현패턴": "patterns",
    "확장포인트": "extension_points",
}

_BOUNDARY_IN = re.compile(r"\*\*포함\*\*\s*:?\s*\n(.+?)(?=\n\*\*제외\*\*|\Z)", re.S)
_BOUNDARY_OUT = re.compile(r"\*\*제외\*\*\s*:?\s*\n(.+?)\Z", re.S)


def _key(title: str) -> str:
    return re.sub(r"\s+", "", title).lower().replace("invariants", "invariants")


@dataclass
class DomainDoc:
    """도메인 MD 하나. **없는 것은 없다고 말한다.**"""
    domain: str
    path: Path
    frontmatter: dict = field(default_factory=dict)
    summary: str = ""
    responsibilities: list = field(default_factory=list)
    boundary_in: list = field(default_factory=list)
    boundary_out: list = field(default_factory=list)
    invariants: list = field(default_factory=list)
    collaborators: list = field(default_factory=list)
    intent_notes: str = ""
    patterns: str = ""              # `## 핵심 구현 패턴` — 6/7 도메인의 주력 신호
    extension_points: str = ""      # `## 확장 포인트`
    extra: dict = field(default_factory=dict)     # 그 밖의 `## ` 섹션 원문
    missing: list = field(default_factory=list)   # 🔴 없었던 정규 섹션

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status") or "").strip()

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def related_classes(self) -> dict:
        """frontmatter 의 `related_classes` → `{클래스: 파일}`.

        실물은 **단일키 dict 의 리스트**다(`- UFoo: Source/…/Foo.h`). dict 로 온 경우도
        받는다 — 두 형태가 섞여 있어도 조용히 한쪽을 버리지 않기 위해서다.
        """
        raw = self.frontmatter.get("related_classes")
        out: dict = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                out[str(k)] = str(v or "")
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    for k, v in item.items():
                        out[str(k)] = str(v or "")
                elif isinstance(item, str) and item.strip():
                    out[item.strip()] = ""
        return out

    @property
    def tags(self) -> list:
        raw = self.frontmatter.get("tags")
        if isinstance(raw, list):
            return [str(t) for t in raw if str(t).strip()]
        if isinstance(raw, str):
            return [t.strip() for t in raw.strip("[]").split(",") if t.strip()]
        return []

    @property
    def source_documents(self) -> list:
        raw = self.frontmatter.get("source_documents")
        return [str(x) for x in raw] if isinstance(raw, list) else []

    @property
    def summary_text(self) -> str:
        """프롬프트에 넣을 도메인 서술. **있는 절을 모아 준다.**

        `## 시스템 개요` 만 쓰면 6/7 도메인이 개요 한 문단으로 끝난다 — 그 도메인들의
        실질 내용은 `## 핵심 구현 패턴` 에 있다.
        """
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.responsibilities:
            parts.append("핵심 책임:\n" + "\n".join(f"- {r}" for r in self.responsibilities))
        if self.patterns:
            parts.append("핵심 구현 패턴:\n" + self.patterns)
        if self.extension_points:
            parts.append("확장 포인트:\n" + self.extension_points)
        if self.boundary_in or self.boundary_out:
            b = []
            if self.boundary_in:
                b.append("포함: " + " / ".join(self.boundary_in))
            if self.boundary_out:
                b.append("제외: " + " / ".join(self.boundary_out))
            parts.append("도메인 경계:\n" + "\n".join(b))
        return "\n\n".join(parts)

    @property
    def summary_note(self) -> str:
        """결손 보고 한 줄. 🔴 **빈 것을 숨기지 않는다.**"""
        s = (f"{self.domain}: 멤버 {len(self.related_classes)}"
             f" · 서술 {len(self.summary_text)}자")
        if self.extra:
            s += f" · 미지 섹션 {len(self.extra)}"
        if self.missing:
            s += f" · 정규 섹션 없음 {', '.join(self.missing)}"
        return s


def domains_dir(paths: ProjectPaths) -> Path:
    return paths.context / "_domains"


def parse_text(text: str, *, domain: str = "", path: Path | None = None) -> DomainDoc:
    """MD 원문 → `DomainDoc`. **아는 섹션을 골라 쓰고 나머지는 남긴다.**"""
    doc = DomainDoc(domain=domain, path=path or Path(domain))

    m = _FRONTMATTER.match(text)
    body = text
    if m:
        loaded = yaml_io.load(m.group(1))
        doc.frontmatter = loaded if isinstance(loaded, dict) else {}
        body = text[m.end():]

    # `## ` 헤더로 잘라 전 섹션을 dict 로. 원본처럼 이름별 정규식을 따로 두지 않는다 —
    # 그러면 모르는 이름이 조용히 사라진다.
    marks = list(_SECTION.finditer(body))
    sections: dict = {}
    for i, mk in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        sections[mk.group(1).strip()] = body[mk.end():end].strip()

    seen: set = set()
    for title, content in sections.items():
        k = _key(title)
        field_name = _CANON.get(k) or _CANON_EXTRA.get(k)
        if field_name is None:
            doc.extra[title] = content
            continue
        seen.add(field_name)
        if field_name == "summary":
            doc.summary = content
        elif field_name == "responsibilities":
            doc.responsibilities = _items(content)
        elif field_name == "boundary":
            doc.boundary_in, doc.boundary_out = _boundary(content)
        elif field_name == "invariants":
            doc.invariants = _items(content)
        elif field_name == "collaborators":
            doc.collaborators = _items(content)
        elif field_name == "intent_notes":
            doc.intent_notes = content
        elif field_name == "patterns":
            doc.patterns = content
        elif field_name == "extension_points":
            doc.extension_points = content

    doc.missing = [name for name in dict.fromkeys(_CANON.values()) if name not in seen]
    return doc


def _items(section: str) -> list:
    """`- 항목` 만 뽑는다. 마크다운 강조는 보존한다(원본과 같다)."""
    return [m.group(1).strip() for m in _LIST_ITEM.finditer(section or "") if m.group(1).strip()]


def _boundary(section: str) -> tuple:
    """`## 도메인 경계` → (포함, 제외). 마크가 없으면 전부 포함으로 본다(원본의 관대 폴백)."""
    if not section:
        return [], []
    a = _BOUNDARY_IN.search(section)
    b = _BOUNDARY_OUT.search(section)
    inc = _items(a.group(1)) if a else []
    exc = _items(b.group(1)) if b else []
    if not inc and not exc:
        inc = _items(section)
    return inc, exc


def read(paths: ProjectPaths, domain: str) -> DomainDoc | None:
    """도메인 MD 하나를 읽는다. **없으면 `None`** — 빈 문서로 위장하지 않는다."""
    p = domains_dir(paths) / f"{domain}.md"
    if not p.is_file():
        return None
    from .. import source_text
    d = source_text.read(p)
    if d is None:
        return None
    return parse_text(d.text, domain=domain, path=p)


def read_all(paths: ProjectPaths, *, active_only: bool = True) -> list:
    """모든 도메인 MD. `_` 로 시작하는 것은 도메인이 아니다(`_overview`·`_unassigned` 등)."""
    root = domains_dir(paths)
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_"):
            continue
        doc = read(paths, p.stem)
        if doc is None:
            continue
        if active_only and not doc.active:
            continue
        out.append(doc)
    return out
