"""도메인 게시판 — **읽기 전용** (목록·상세). 쓰기는 걷었다 (`#812`, 사용자 결정 2026-10-11).

> *"이제는 메인 작업 PC와 인프라 컴퓨터 - 워커 3단계로만 작업 진행하니까 필요없어"*

🔴 `#812` — 원전 `domain_viewer_routes.py` 에서 복각했던 mutation 경로(생성·채팅·갱신·활성화·
삭제·채팅 비우기)와 그것만 쓰던 도우미(LLM 호출·관련 문서 검색·채팅 히스토리 저장·원자적 쓰기)를
**코드에서 지웠다.** 웹 라우트는 405 이고(`app.py`), 원전 화면의 쓰기 버튼·채팅 칸은 서빙 시점에
숨긴다(`routes.context_server_html`). 상세 응답은 `chat_history` 를 더 싣지 않는다 — 채팅이 없다.
[주의] 다시 필요하면 git 기록에서 되살리되 **토큰 뒤에** 둔다(공개 접두어 `/api/v1` 금지).

## [중요] 게시판은 온톨로지 패키지가 **아니다** — 이걸 헷갈리면 안 된다

    /api/v1/domains          → `context/_domains/*.md`      사람이 읽는 **도메인 문서**
                                (frontmatter `status: draft|active` · source_documents · tags)
    /api/v1/ontology/domains → `ontology/domains/*/domain.yaml`  기계가 쓰는 **온톨로지 패키지**

우리 `domain.yaml` 이 주석에 *"사람 편집 위치 = `_domains/<D>.md`"* 라고 적어 둔 그 관계다.

## [중요] 읽기 안전장치

- **이름 검사 + 경로 이중 확인**: 구분자·`..`·제어문자를 막고, 만든 경로가 디렉토리 안인지
  `resolve().relative_to()` 로 다시 본다. [주의] **한글 이름은 허용한다** — 막아야 하는 것은
  경로 이탈이지 문자 종류가 아니다
- `_` 로 시작하는 파일은 게시판에 올리지 않는다 — `_overview.md`·`_unassigned.md` 같은 관리 문서다
"""
from __future__ import annotations

import re
from pathlib import Path

# [중요] **한글 이름을 허용한다** — 원전은 경로 위험문자(`\/:*?"<>|`)만 걸렀고 한글 파일명을 그대로
#    썼다. 내가 `[A-Za-z0-9_-]` 로 좁혔더니 **한글 도메인명이 통째로 날아가** 파일명이 `domain`
#    이 됐다(실측 2026-08-13). 리눅스에서 한글 파일명은 문제가 아니다.
#    막아야 하는 것은 **경로 이탈**이므로 그것만 막는다(구분자·`..`·제어문자·앞뒤 공백/점).
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _name_ok(name: str) -> bool:
    n = (name or "").strip()
    if not n or len(n) > 80 or n != name:
        return False
    if n.startswith("_") or n.startswith(".") or n.endswith("."):
        return False
    if ".." in n or _BAD_CHARS.search(n):
        return False
    return True


FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class BoardError(RuntimeError):
    """게시판 요청을 처리할 수 없다. [중요] 사유를 화면에 그대로 보인다."""


# ── 경로 ────────────────────────────────────────────────────────────────────────

def domains_dir(paths) -> Path:
    return paths.context / "_domains"


def md_path(paths, name: str) -> Path:
    """[중요] 이름을 검사하고 나서만 경로를 만든다. `_` 시작은 관리 문서라 거부."""
    if not _name_ok(name):
        raise BoardError(f"허용되지 않는 도메인 이름이다: {name!r} "
                         f"(경로 구분자·`..`·제어문자 금지, `_`/`.` 로 시작 금지 — 관리 문서 보호)")
    d = domains_dir(paths)
    p = (d / f"{name}.md")
    # [중요] 이중 방어 — 이름 검사를 통과해도 실제 경로가 디렉토리 밖이면 거부한다
    try:
        p.resolve().relative_to(d.resolve())
    except ValueError:
        raise BoardError(f"디렉토리 밖을 가리킨다: {name!r}") from None
    return p


# ── frontmatter (원전 `_parse_frontmatter` 등가 — 우리 문서 형식 그대로) ──────────

def parse_front(content: str) -> dict:
    """`---` 블록 → dict. [중요] 우리 문서의 실제 형식만 읽는다(리스트 두 표기 모두)."""
    m = FRONT.match(content or "")
    if not m:
        return {}
    out: dict = {}
    key = None
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and key:
            item = line[4:].strip()
            if item.startswith("#"):
                continue
            # `- Name: path` (related_classes) 도 있다 — 앞쪽만 쓴다
            out.setdefault(key, []).append(item)
            continue
        m2 = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m2:
            continue
        key, val = m2.group(1), m2.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            out[key] = [x.strip() for x in inner.split(",") if x.strip()]
        elif val:
            out[key] = val
        else:
            out[key] = []
    return out


def extract_body(content: str) -> str:
    m = FRONT.match(content or "")
    return (content or "")[m.end():] if m else (content or "")


# ── 목록 · 상세 (원전 모양 그대로) ───────────────────────────────────────────────

def list_board(paths) -> dict:
    d = domains_dir(paths)
    if not d.is_dir():
        return {"domains": [], "counts": {"draft": 0, "active": 0}}
    domains: list = []
    counts = {"draft": 0, "active": 0}
    for f in sorted(d.glob("*.md")):
        if f.name.startswith("_"):
            continue                              # 관리 문서는 게시판에 올리지 않는다
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta = parse_front(content)
        status = str(meta.get("status") or "active")
        counts[status] = counts.get(status, 0) + 1
        body = extract_body(content)
        m = re.search(r"## 시스템 개요\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
        domains.append({
            "name": f.stem,
            "file": f"_domains/{f.name}",
            "status": status,
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "source_documents": meta.get("source_documents", []),
            "summary": (m.group(1).strip()[:200] if m else ""),
            "created": meta.get("created", ""),
        })
    return {"domains": domains, "counts": counts}


def get_board_domain(paths, name: str) -> dict | None:
    p = md_path(paths, name)
    if not p.is_file():
        return None
    content = p.read_text(encoding="utf-8", errors="replace")
    meta = parse_front(content)
    srcs: list = []
    for src in meta.get("source_documents", []):
        sp = paths.context / str(src)
        if sp.is_file():
            try:
                srcs.append({"file": src, "content": sp.read_text(encoding="utf-8",
                                                                  errors="replace")})
            except OSError:
                srcs.append({"file": src, "content": "(읽기 실패)"})
        else:
            srcs.append({"file": src, "content": "(파일 없음)"})
    return {"name": name, "status": meta.get("status", "active"), "content": content,
            "source_documents": srcs}
