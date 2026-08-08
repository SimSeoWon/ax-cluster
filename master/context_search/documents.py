"""컨텍스트 MD 파싱·선별 (AgentTest `cs_common.py` 에서 필요분만 이식).

🔴 **색인 문서는 원본 소스가 아니라 컨텍스트 MD 다** (실측 2026-08-08).
`watcher/context_index.py:41,45` 가 소스 파일 → MD 로 매핑한다:

    Source/Foo/Bar.cpp  →  context/Foo/Bar.md   (파일 단위)
                       또는 context/Foo.md      (디렉토리 단위)

§5.2-E 의 "소스 한정" 이 구체적으로 이 매핑이다 — `Content/` 의 uasset 에는 대응 MD 가 없으므로
**범위 밖이 자동으로 성립한다.** 별도 필터가 필요 없다.

**`cs_common.py` 717줄 전체를 가져오지 않았다.** 색인에 실제로 쓰이는 3개 함수(92줄)만 옮겼다 —
나머지는 라우트·감사·온톨로지가 쓰는 것이라 그 단계에서 필요해지면 그때 가져온다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


def parse_frontmatter(content: str) -> dict:
    """MD 의 YAML 프론트매터에서 tags·category·status·type 등을 뽑는다.

    ⚠️ 원본 그대로다 — 정규식 기반이라 완전한 YAML 파서가 아니다. 프론트매터를 생성하는
    쪽(AgentTest 합성기)과 짝이 맞춰져 있으므로 **여기서 '개선' 하면 오히려 어긋난다.**
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}
    fm = match.group(1)
    result: dict = {}

    m = re.search(r"tags:\s*\[([^\]]*)\]", fm)
    if m:
        result["tags"] = [t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()]
    m = re.search(r"category:\s*(.+)", fm)
    if m:
        result["category"] = m.group(1).strip()
    classes = re.findall(r"-\s+(\w+):\s+(.+)", fm)
    if classes:
        result["related_classes"] = {c: p.strip() for c, p in classes}
    for key in ("status", "type"):
        m = re.search(rf"{key}:\s*(\w+)", fm)
        if m:
            result[key] = m.group(1).strip()
    m = re.search(r"content_hash:\s*([0-9a-fA-F]+)", fm)
    if m:
        result["content_hash"] = m.group(1).strip()
    m = re.search(r"source_documents:\s*\n((?:\s+-\s+.+\n?)*)", fm)
    if m:
        result["source_documents"] = re.findall(r"-\s+(\S+)", m.group(1))
    m = re.search(r"created:\s*(.+)", fm)
    if m:
        result["created"] = m.group(1).strip()
    return result


def extract_body(content: str) -> str:
    """프론트매터를 제외한 본문."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL).strip()


def is_excluded(file_id: str) -> bool:
    """`_domains/*.md` 는 메인 색인에서 제외한다.

    도메인 yaml 이 그 MD 의 완전한 상위 집합이라 중복이고, 도메인 검색은 별도 진입점을
    쓴다(소 2.1.1 `sync_domain_index`). MD 자체는 **사람 SSOT 이자 합성기 입력**이라
    보존한다 — **지우면 안 된다.** 색인에서만 뺀다.
    """
    if not file_id:
        return False
    return file_id.replace("\\", "/").startswith("_domains/")


def content_hash(text: str) -> str:
    """프론트매터에 `content_hash` 가 없을 때의 폴백. 원본과 같은 16자 md5."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Document:
    """색인 한 건."""

    file_id: str          # context/ 기준 상대 경로 (slash 통일) — 컬렉션의 id
    body: str
    meta: dict
    fm: dict              # 원본 프론트매터 — 본문이 없을 때 검색 텍스트를 만든다

    @property
    def has_body(self) -> bool:
        return bool(self.body.strip())

    @property
    def search_text(self) -> str:
        """임베딩할 텍스트.

        🔴 **본문이 없어도 버리지 않는다.** 실측(2026-08-08) 컨텍스트 MD 1,055개 중
        **149개(14%)가 프론트매터만 있는 스텁**이다(예: `Manager/ManagerBase.md` 373B).
        본문이 없다고 버리면 `UManagerBase` 같은 **클래스명으로 못 찾게 된다** —
        그게 그 스텁의 존재 이유인데.

        원본도 버리지 않는다(`double_buffered_index.py:113~121` — `_domains/` 와 읽기 실패만
        거른다). 다만 원본은 **원문 전체**를 BM25 에 넣는 반면 여기서는 프론트매터를
        **읽을 수 있는 문장으로 펼쳐** 임베딩한다 — YAML 기호를 그대로 벡터에 넣으면
        노이즈가 되기 때문이다.
        """
        if self.has_body:
            return self.body
        parts = []
        if self.fm.get("category"):
            parts.append(str(self.fm["category"]).replace("/", " "))
        if self.fm.get("tags"):
            parts.append(" ".join(self.fm["tags"]))
        rc = self.fm.get("related_classes") or {}
        if rc:
            parts.append(" ".join(rc))           # 클래스명 — 이게 핵심이다
            parts.append(" ".join(rc.values()))  # 경로도 검색에 걸리게
        return " ".join(p for p in parts if p).strip()


def load(path: Path, context_dir: Path) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    body = extract_body(text)
    file_id = path.relative_to(context_dir).as_posix()
    meta = {
        "file_id": file_id,
        "path": str(path),
        "content_hash": fm.get("content_hash") or content_hash(body),
    }
    # ChromaDB 메타데이터는 스칼라만 받는다 — 리스트/딕트는 문자열로 눕힌다.
    if fm.get("tags"):
        meta["tags"] = ",".join(fm["tags"])
    for k in ("category", "status", "type", "created"):
        if fm.get(k):
            meta[k] = str(fm[k])
    if fm.get("related_classes"):
        meta["related_classes"] = ",".join(sorted(fm["related_classes"]))
    meta["has_body"] = bool(body.strip())   # 스텁인지 결과에서 구분할 수 있게
    return Document(file_id=file_id, body=body, meta=meta, fm=fm)


def iter_documents(context_dir: Path):
    """색인 대상 MD 를 순회한다. 제외 규칙과 빈 문서를 여기서 거른다."""
    if not context_dir.is_dir():
        return
    for path in sorted(context_dir.rglob("*.md")):
        file_id = path.relative_to(context_dir).as_posix()
        if is_excluded(file_id):
            continue
        doc = load(path, context_dir)
        if not doc.search_text:
            # 프론트매터도 본문도 없다 — 진짜로 넣을 것이 없는 경우만 건너뛴다.
            continue
        yield doc
