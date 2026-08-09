"""도메인 생성 — 씨앗 MD 를 만든다 (소 1.3.1, 상위 지정 포함).

원본: `mcp/context_search/ontology_manage.py` 의 `create_domain_impl`.

## 🔴 만드는 것은 **MD 씨앗**이지 패키지가 아니다

    create()  →  context/_domains/<D>.md      사람의 의도. 여기가 원천이다
    합성      →  ontology/domains/<D>/*.yaml   기계가 만든다 (소 1.3.3)

거꾸로 하면 안 된다. yaml 을 먼저 만들면 **의도 없는 도메인**이 생기고, 재합성이 그것을
근거 삼아 액션·invariant 를 지어낸다.

## 🔴 멤버십을 추측하지 않는다

원본 주석 그대로 — *"명시 스펙으로 도메인 MD 생성 (검색·LLM 추측 멤버십 없음)"*. 자동 승급이
크게 데인 자리다(2026-06-01 영구 비활성, 사용자 확인 *"오동작이 심했다"*). 멤버는 사람이
`collect.propose` 의 후보를 보고 고른다.

## 🔴 이름은 ASCII PascalCase 다

한글 도메인명은 경로·URL·검색 식별자에서 깨진다. 원본이 같은 이유로 거부한다. 한글은
**태그와 별칭**으로 넣는다 — 그쪽이 검색에 실제로 쓰이는 자리다(중 1.4).

## 🔴 `## 도메인 경계` 를 빈 채로라도 넣는다

실측 2026-08-09: 7개 도메인 중 **6개에 이 절이 없다.** 그리고 그 절이 없으면 합성이 다른
도메인의 클래스를 끌어온다(`allowed_classes` 필터와 사실 게이트가 지금 그걸 막고 있다).
새로 만드는 문서에서까지 그 빚을 지지 않는다 — **채워 달라는 표시와 함께** 자리를 만든다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

STATUS_DRAFT = "draft"          # 🔴 기본은 draft — 활성화는 사람이 명시한다
_PASCAL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 씨앗에 넣는 절. 🔴 순서·표기가 `domain_md._CANON` 과 왕복돼야 한다.
SECTIONS = (
    ("시스템 개요", "이 도메인이 무엇을 하는 곳인지 한두 문단."),
    ("핵심 책임", "- "),
    ("도메인 경계", "🔴 **무엇이 이 도메인이 아닌지** 적는다. 비워 두면 합성이 다른 "
                    "도메인의 클래스를 끌어온다(실측)."),
    ("핵심 invariants", "- "),
    ("협력 도메인", "- "),
    ("사용자 의도 메모", ""),
)


class CreateError(RuntimeError):
    """만들 수 없다. 🔴 **덮어쓰지 않는다.**"""


@dataclass
class CreateResult:
    domain: str
    path: str = ""
    parent: str = ""
    linked: bool = False
    notes: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = f"{self.domain} 생성 · status={STATUS_DRAFT}"
        if self.parent:
            s += f" · 상위 {self.parent}" + ("" if self.linked else " (🔴 연결 실패)")
        if self.notes:
            s += " · " + "; ".join(self.notes[:2])
        return s


def validate_name(name: str) -> str:
    """도메인명 검사. 🔴 **고쳐 주지 않는다** — 조용히 바꾼 이름은 사람이 찾지 못한다."""
    n = (name or "").strip()
    if not n:
        raise CreateError("도메인명이 비었다")
    if not n.isascii():
        raise CreateError(
            f"도메인명에 비ASCII 가 있다: {n!r} — 경로·URL·검색 식별자에서 깨진다. "
            f"영문 PascalCase 로 짓고, 한글은 **태그와 별칭**으로 넣는다(중 1.4)")
    if not _PASCAL.match(n):
        raise CreateError(f"도메인명은 영문자로 시작하는 PascalCase 여야 한다: {n!r}")
    return n


def md_path(paths: ProjectPaths, domain: str):
    return paths.root / "context" / "_domains" / f"{domain}.md"


def render(domain: str, *, tags=(), parent: str = "", summary: str = "",
           collaborators=()) -> str:
    """씨앗 본문. 🔴 **빈 절도 남긴다** — 없는 절은 다음 사람이 있는 줄도 모른다."""
    fm = ["---",
          "tags: [" + ", ".join(str(t) for t in tags) + "]",
          f"category: 도메인/{domain}",
          "type: domain",
          f"status: {STATUS_DRAFT}"]
    if parent:
        fm.append(f"parent_domain: {parent}")
    fm.append("---")

    body = [""]
    for title, hint in SECTIONS:
        body.append(f"## {title}")
        body.append("")
        if title == "시스템 개요" and summary:
            body.append(summary)
        elif title == "협력 도메인" and collaborators:
            body += [f"- {c}" for c in collaborators]
        elif hint:
            body.append(hint)
        body.append("")
    return "\n".join(fm + body).rstrip() + "\n"


def create(paths: ProjectPaths, name: str, *, tags=(), parent: str = "",
           summary: str = "", collaborators=()) -> CreateResult:
    """도메인 씨앗 MD 를 만든다. **이미 있으면 예외 — 덮지 않는다.**"""
    domain = validate_name(name)
    p = md_path(paths, domain)
    if p.exists():
        raise CreateError(f"이미 있다: {p} — 덮지 않는다. 고치려면 그 파일을 편집하라")

    parent_name = validate_name(parent) if parent else ""
    res = CreateResult(domain=domain, path=str(p), parent=parent_name)

    if parent_name and not md_path(paths, parent_name).exists():
        # 🔴 없는 상위를 조용히 받아 두면 계층이 끊긴 채로 남는다
        raise CreateError(f"상위 도메인 MD 가 없다: {parent_name} — 먼저 만들어라")

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(domain, tags=tags, parent=parent_name, summary=summary,
                        collaborators=collaborators), encoding="utf-8")

    if parent_name:
        # 패키지가 아직 없을 수 있다(합성 전) — 그때는 frontmatter 의 parent_domain 만 남는다
        try:
            from . import hierarchy
            r = hierarchy.add_child(paths, parent_name, domain)
            res.linked = bool(getattr(r, "ok", False))
            if not res.linked:
                res.notes.append(f"패키지 계층 연결 보류({r.status}) — frontmatter 에는 기록됨")
        except Exception as e:                            # noqa: BLE001
            res.notes.append(f"계층 연결 보류({type(e).__name__}) — frontmatter 에는 기록됨")

    if not tags:
        # 🔴 실측: 태그 채널(가중치 3.0)이 한글 0개라 한글 질의가 최고 가중치를 놓친다
        res.notes.append("태그가 비었다 — 한글 태그를 넣으면 한글 검색이 산다(중 1.4)")
    return res
