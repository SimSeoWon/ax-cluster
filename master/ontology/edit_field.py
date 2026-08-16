"""도메인 MD 필드 편집 (#189) — 원전 `ontology_manage.edit_domain_field_impl` 의 이식.

도메인 MD 를 **필드 단위**로 고친다 (통째 덮어쓰기 대신): frontmatter 의
`parent_domain`·`status`·`tags`, 섹션의 `## 협력 도메인`·`## 시스템 개요`.
[중요] 자동 승급을 폐기한 우리에게는 이것이 `/manage-domain` 류의 도메인 수정 유일 경로다 —
사람이 대화형으로 확정한 값만 들어온다.

원전의 두 갈래 그대로:
    결정적·즉시    parent_domain / tags / collaborates_with → **manifest(domain.yaml) 직접
                  패치** + 도메인 인덱스 재빌드 (LLM 0 · 멤버 재분류 0 — 원전이 full refresh
                  를 폐기한 이유: 하위 도메인 연결이 67멤버 재검증을 유발했다)
    MD-only       summary / status → 다음 자연 refresh 에 manifest 반영 (eventually-consistent)

원전과의 차이 (#194 판정의 적용, 2026-08-17):
    지점 7   tags 는 원전대로 **통째 치환**이되, 치환으로 사라지는 **한글 태그**(가중치 3.0
            채널, 이전 마일스톤의 산물)를 결과에 **크게 보고**한다 — 조용한 소실 금지.
    지점 5   parent_domain 이름은 원전처럼 조용히 정규화(`safe_domain_name` → `_` 치환)하지
            않고 `create.validate_name` 으로 **거부**한다 — 한글 허용·위험문자 거부, 조용한
            정규화 금지는 우리 원칙.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import create

_HANGUL_RE = re.compile(r"[가-힣]")

# ── 원전 헬퍼 글자대로 (ontology_manage_util.py) ─────────────────

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.S)


def _split_md(text: str) -> tuple:
    m = _FM_RE.match(text)
    if not m:
        return "", text, False
    return m.group(2), text[m.end():], True


def _rebuild_md(fm_text: str, body: str) -> str:
    return f"---\n{fm_text}\n---\n{body}"


def _set_fm_scalar(fm_text: str, key: str, value: str) -> str:
    """frontmatter 의 스칼라 `key: value` 라인 교체 또는 추가."""
    line = f"{key}: {value}"
    pat = re.compile(rf"^{re.escape(key)}\s*:.*$", re.M)
    if pat.search(fm_text):
        return pat.sub(line, fm_text, count=1)
    # related_classes/source_documents 같은 블록 앞에 끼지 않도록 끝에 추가
    return fm_text.rstrip("\n") + f"\n{line}"


_COLLAB_SECTION_RE = re.compile(r"(##\s*협력\s*도메인\s*\n)(.*?)(?=\n##\s|\Z)", re.S)
_OVERVIEW_SECTION_RE = re.compile(r"(##\s*시스템\s*개요\s*\n)(.*?)(?=\n##\s|\Z)", re.S)


def _set_section_list(body: str, section_re, header: str, items: list) -> str:
    """`## 협력 도메인` 같은 리스트 섹션 본문 교체(없으면 말미에 추가)."""
    block = header + "\n".join(f"- {it}" for it in items) + "\n"
    if section_re.search(body):
        return section_re.sub(lambda m: block, body, count=1)
    return body.rstrip("\n") + "\n\n" + block


def _set_section_text(body: str, section_re, header: str, text: str) -> str:
    if section_re.search(body):
        return section_re.sub(lambda m: header + text.strip() + "\n", body, count=1)
    return body.rstrip("\n") + "\n\n" + header + text.strip() + "\n"


# ── 원전 manifest 패치 헬퍼 글자대로 (ontology_manage_items.py) ──

def _set_manifest_scalar(text: str, key: str, value: str) -> str:
    """manifest 의 스칼라 set/replace. 빈값이면 라인 제거. 없으면 `domain:` 직후 삽입."""
    pat = re.compile(rf"(?m)^{re.escape(key)}:.*$")
    if not value:
        return re.sub(rf"(?m)^{re.escape(key)}:.*\n?", "", text, count=1) \
            if pat.search(text) else text
    line = f"{key}: {value}"
    if pat.search(text):
        return pat.sub(line, text, count=1)
    if re.search(r"(?m)^domain:.*$", text):
        return re.sub(r"(?m)^(domain:.*)$", rf"\1\n{line}", text, count=1)
    return line + "\n" + text


def _set_manifest_list(text: str, key: str, items: list) -> str:
    """manifest 의 블록 리스트 set/replace. 빈 list 면 블록 제거. `\\s` 대신 `[ \\t]` 로
    후속 top-level 키 침범 방지 (원전 주석 그대로)."""
    block_re = re.compile(rf"(?m)^{re.escape(key)}:[ \t]*\n(?:[ \t]+-[ \t].*\n)*")
    new_block = (f"{key}:\n" + "".join(f"  - {it}\n" for it in items)) if items else ""
    if block_re.search(text):
        return block_re.sub(new_block, text, count=1)
    if new_block:
        return text.rstrip("\n") + "\n" + new_block
    return text


# ── 본체 ─────────────────────────────────────────────────────────

def _current_fm_tags(fm_text: str) -> list:
    m = re.search(r"^tags:\s*\[(.*?)\]\s*$", fm_text, re.M)
    if not m:
        return []
    return [t.strip().strip("'\"") for t in m.group(1).split(",") if t.strip()]


def edit_domain_field(paths: ProjectPaths, domain: str, *,
                      parent_domain=None, status=None, tags=None,
                      collaborates_with=None, summary=None,
                      indexer=None, logf=None) -> dict:
    """도메인 MD 의 필드 단위 편집. 제공된 인자만 적용. (원전 시그니처 그대로)

    `indexer(paths)` 주입은 테스트 자리 — 실전은 `domain_index.sync` (LLM 0).
    """
    log = logf or (lambda m: None)
    md = create.md_path(paths, domain)
    if not md.exists():
        return {"status": "not_found", "domain": domain, "reason": "도메인 MD 부재"}
    text = md.read_text(encoding="utf-8")
    fm_text, body, ok = _split_md(text)
    if not ok:
        return {"status": "error", "domain": domain, "reason": "frontmatter 파싱 실패"}

    changed: list = []
    kr_tags_removed: list = []
    if parent_domain is not None:
        if parent_domain.strip():
            # [중요] 원전은 safe_domain_name 으로 조용히 정규화한다 — 우리는 거부한다 (#194 지점 5)
            try:
                val = create.validate_name(parent_domain)
            except create.CreateError as e:
                return {"status": "error", "domain": domain, "reason": str(e)}
            fm_text = _set_fm_scalar(fm_text, "parent_domain", val)
        else:
            fm_text = re.sub(r"^parent_domain\s*:.*$\n?", "", fm_text, flags=re.M).rstrip("\n")
        changed.append("parent_domain")
    if status is not None:
        fm_text = _set_fm_scalar(fm_text, "status", status.strip())
        changed.append("status")
    if tags is not None:
        # [중요] #194 지점 7 — 원전대로 통째 치환하되, 사라지는 한글 태그는 크게 보고한다.
        #    한글 태그는 가중치 3.0 검색 채널이고 이전 마일스톤이 값을 치른 층이다.
        before = _current_fm_tags(fm_text)
        kr_tags_removed = [t for t in before
                           if _HANGUL_RE.search(t) and t not in (tags or [])]
        fm_text = _set_fm_scalar(fm_text, "tags", "[" + ", ".join(tags) + "]")
        changed.append("tags")
    if collaborates_with is not None:
        body = _set_section_list(body, _COLLAB_SECTION_RE, "## 협력 도메인\n", collaborates_with)
        changed.append("collaborates_with")
    if summary is not None:
        body = _set_section_text(body, _OVERVIEW_SECTION_RE, "## 시스템 개요\n\n", summary)
        changed.append("summary")

    if not changed:
        return {"status": "noop", "domain": domain, "reason": "변경 인자 없음"}

    md.write_text(_rebuild_md(fm_text, body), encoding="utf-8")
    result = {"status": "ok", "domain": domain, "changed": changed}
    if kr_tags_removed:
        result["kr_tags_removed"] = kr_tags_removed
        result["warning"] = (f"[중요] 치환으로 한글 태그 {len(kr_tags_removed)}개가 사라졌다 "
                             f"({', '.join(kr_tags_removed)}) — 의도가 아니면 tags 에 도로 "
                             f"넣어라. 한글 태그는 가중치 3.0 검색 채널이다")
        log(result["warning"])

    # 패스스루 메타(parent_domain/collaborates_with/tags)는 manifest 를 직접 패치 — 결정적,
    # 즉시, 멤버 재분류 0. summary/status 는 MD-only (원전 그대로).
    manifest = Path(paths.ontology) / "domains" / domain / "domain.yaml"
    patched: list = []
    if manifest.exists():
        try:
            mtext = mtext0 = manifest.read_text(encoding="utf-8")
            if parent_domain is not None:
                mtext = _set_manifest_scalar(mtext, "parent_domain",
                                             (parent_domain or "").strip())
                patched.append("parent_domain")
            if tags is not None:
                mtext = _set_manifest_list(mtext, "tags", list(tags))
                patched.append("tags")
            if collaborates_with is not None:
                mtext = _set_manifest_list(mtext, "collaborates_with", list(collaborates_with))
                patched.append("collaborates_with")
            if mtext != mtext0:
                manifest.write_text(mtext, encoding="utf-8")
        except Exception:                                # noqa: BLE001
            patched = []
    result["manifest_patched"] = patched

    # 도메인 인덱스 재빌드 (collaborates_with/tags 가 검색 페이로드에 들어감). LLM 0.
    if patched:
        try:
            if indexer is not None:
                indexer(paths)
            else:
                from ..context_search import domain_index
                domain_index.sync(paths)
        except Exception as e:                           # noqa: BLE001
            result["index_note"] = f"[주의] 인덱스 재빌드 실패 — 다음 refresh 가 정합: {e}"
    if summary is not None or status is not None or \
            (parent_domain is not None and not manifest.exists()):
        result["note"] = ("summary/status (및 패키지 미존재 시 parent_domain) 는 MD 반영 — "
                          "manifest·인덱스는 다음 refresh 에 정합(eventually-consistent)")
    return result
