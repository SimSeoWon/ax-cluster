"""검증된 문서 수정안을 명시적으로 승인한 정본에 적용한다."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import unquote, urlsplit

from . import DocSyncError, digest, read_text
from .registry import collect


def _digest(text):
    if not isinstance(text, str):
        raise DocSyncError("문자열 본문 필요")
    try:
        return digest(text)
    except UnicodeError as exc:
        raise DocSyncError("UTF-8로 저장할 수 없는 본문") from exc


def _links(text, target):
    text = re.sub(r"^\s*(```|~~~).*?^\s*\1[^\n]*$", "", text, flags=re.M | re.S)
    links = re.findall(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)", text)
    missing = set()
    for link in links:
        link = link.strip("<>")
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path = Path(unquote(parsed.path))
        resolved = path if path.is_absolute() else target.parent / path
        if not resolved.exists():
            missing.add(str(resolved.resolve()))
    return missing


def _check_text(before, after, target):
    marks = re.findall(r"^.*AX-ENTRY-MARK:[^\r\n]*", before, re.M)
    if any(mark not in after.splitlines() for mark in marks):
        raise DocSyncError(f"AX-ENTRY-MARK 보존 위반: {target}")
    broken = _links(after, target) - _links(before, target)
    if broken:
        raise DocSyncError(f"새 깨진 문서 링크: {target}: {sorted(broken)}")


def _replace(target, data, mode):
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".doc-sync-", delete=False) as out:
            name = out.name
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, mode)
        os.replace(name, target)
        name = None
    finally:
        if name is not None:
            os.unlink(name)


def apply_draft(root, registry_path, artifact, *, confirm=False,
                approved_ids=None, allow_protected=False):
    """기본은 쓰기 없는 미리보기이며 승인 ID만 일괄 사전 검증 후 쓴다."""
    if type(confirm) is not bool or type(allow_protected) is not bool:
        raise DocSyncError("confirm/allow_protected는 bool이어야 한다")
    if not isinstance(artifact, dict) or artifact.get("schema_version") != 1:
        raise DocSyncError("지원하지 않는 수정안 형식")
    current = collect(root, registry_path)
    for key in ("root", "registry", "registry_hash"):
        if artifact.get(key) != current[key]:
            raise DocSyncError(f"현재 등록목록과 수정안 불일치: {key}")
    registered = {doc["id"]: doc for doc in current["documents"]}
    documents = artifact.get("documents")
    if not isinstance(documents, list):
        raise DocSyncError("documents 목록 필요")
    if approved_ids is not None and (not isinstance(approved_ids, (list, tuple, set))
                                     or any(not isinstance(item, str) for item in approved_ids)):
        raise DocSyncError("approved_ids는 문서 ID 목록이어야 한다")
    approved = set(approved_ids or [])
    if approved - set(registered):
        raise DocSyncError("미등록 승인 문서 ID")
    seen, changes, unchanged, skipped, pending = set(), [], [], [], []
    for doc in documents:
        if not isinstance(doc, dict) or doc.get("id") not in registered or doc["id"] in seen:
            raise DocSyncError("미등록 또는 중복 문서 ID")
        ident = doc["id"]
        seen.add(ident)
        expected = registered[ident]
        for key in ("path", "target", "protected", "role", "instructions"):
            if doc.get(key) != expected.get(key):
                raise DocSyncError(f"등록 문서 정보 변조: {ident}: {key}")
        target = (Path(current["root"]) / expected["target"]).resolve()
        if not target.is_relative_to(Path(current["root"]).resolve()):
            raise DocSyncError(f"정본 경계 이탈: {ident}")
        before, after = doc.get("before"), doc.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            raise DocSyncError(f"문서 본문 누락: {ident}")
        if _digest(before) != doc.get("before_sha256") or _digest(after) != doc.get("after_sha256"):
            raise DocSyncError(f"문서 해시 불일치: {ident}")
        if doc.get("decision") not in ("update", "unchanged"):
            raise DocSyncError(f"문서 결정 누락: {ident}")
        if doc["decision"] == "unchanged" and before != after:
            raise DocSyncError(f"unchanged 본문 불일치: {ident}")
        if doc["decision"] == "update" and not after.strip():
            raise DocSyncError(f"빈 문서 수정안 거부: {ident}")
        if not isinstance(doc.get("reason"), str) or not doc["reason"].strip():
            raise DocSyncError(f"문서 수정 사유 필요: {ident}")
        evidence = doc.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != len(expected["evidence"]):
            raise DocSyncError(f"근거 목록 불일치: {ident}")
        for old, now in zip(evidence, expected["evidence"]):
            if not isinstance(old, dict) or old.get("path") != now["path"] or old.get("sha256") != now["sha256"] or _digest(old.get("text", "")) != now["sha256"]:
                raise DocSyncError(f"오래되거나 변조된 근거: {ident}")
        citations = doc.get("citations")
        if not isinstance(citations, list) or (doc["decision"] == "update" and not citations):
            raise DocSyncError(f"문서 근거 인용 필요: {ident}")
        source_lines = {source["path"]: len(source["text"].splitlines()) for source in expected["evidence"]}
        for citation in citations:
            if not isinstance(citation, str):
                raise DocSyncError(f"잘못된 근거 인용: {ident}")
            path, separator, line = citation.rpartition(":")
            if not separator or path not in source_lines or not line.isascii() or not line.isdigit() or not 1 <= int(line) <= source_lines[path]:
                raise DocSyncError(f"근거 경로 또는 줄번호 불일치: {ident}: {citation}")
        live = read_text(target)
        if live not in (before, after):
            raise DocSyncError(f"문서가 수정안 생성 후 변경됨: {ident}")
        _check_text(before, after, target)
        if confirm and ident not in approved:
            skipped.append(ident)
            continue
        protected = expected["protected"] or Path(expected["path"]).name.upper() in ("CLAUDE.MD", "AGENTS.MD") or target.name.upper() in ("CLAUDE.MD", "AGENTS.MD")
        if confirm and protected and not allow_protected:
            raise DocSyncError(f"보호 문서 별도 승인 필요: {ident}")
        if live == after:
            unchanged.append(ident)
        else:
            changes.append(ident)
            try:
                mode = stat.S_IMODE(target.stat().st_mode)
            except OSError as exc:
                raise DocSyncError(f"문서 모드 조회 실패: {target}: {exc}") from exc
            pending.append((target, before.encode("utf-8"), after.encode("utf-8"), mode))
    if approved - seen:
        raise DocSyncError("승인 ID가 수정안에 없음")
    written = []
    if confirm:
        try:
            for target, before, after, mode in pending:
                if target.read_bytes() != before:
                    raise DocSyncError(f"적용 직전 문서 변경: {target}")
                _replace(target, after, mode)
                written.append((target, before, after, mode))
        except (OSError, DocSyncError) as exc:
            failures = []
            for target, before, after, mode in reversed(written):
                try:
                    if target.read_bytes() == after:
                        _replace(target, before, mode)
                    else:
                        failures.append(str(target))
                except OSError:
                    failures.append(str(target))
            raise DocSyncError(f"문서 적용 실패: {exc}; 복구 실패={failures}") from exc
    return {"ok": True, "changed": changes, "unchanged": unchanged,
            "skipped": skipped, "confirm": bool(confirm)}
