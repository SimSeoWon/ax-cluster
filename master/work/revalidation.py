"""로컬 생성 기록과 표시된 문서의 클라우드 재합성 (#840).

조각 기록은 원래 브랜치·응답 스풀과 별도로 보존한다. 이 모듈은 조각 상태나
Git 브랜치를 변경하지 않는다. 문서 재합성은 기존 게이트와 쓰기 직전 지문 대조를 쓴다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def artifact_fingerprint(path):
    """파일 bytes 또는 디렉터리의 상대경로→파일 bytes hash를 비교한다."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"재검증 대상은 심볼릭 링크일 수 없다: {path}")
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise FileNotFoundError(path)
    files = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"재검증 대상에 심볼릭 링크가 있다: {item}")
        if item.is_file():
            files[item.relative_to(path).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return hashlib.sha256(_canonical(files).encode("utf-8")).hexdigest()


def source_fingerprint(paths, files):
    from .. import source_text
    if not isinstance(files, list) or not files:
        raise ValueError("재검증 소스 목록이 비어 있다")
    bodies = {}
    repo = Path(paths.repo).resolve()
    for name in files:
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise ValueError("잘못된 재검증 소스 경로")
        target = repo / name
        if not target.resolve().is_relative_to(repo) or target.is_symlink():
            raise ValueError(f"재검증 소스 경계 이탈: {name}")
        if not paths.scope.contains(name):
            raise ValueError(f"등록 소스 경계 밖: {name}")
        source = source_text.read(target)
        if source is None:
            raise FileNotFoundError(target)
        bodies[name] = source.text
    # 생성기가 기록한 source_fingerprint와 같은 직렬화 규약.
    return hashlib.sha256(json.dumps(bodies, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@contextmanager
def _store(root):
    directory = Path(root) / "revalidation"
    if directory.is_symlink():
        raise ValueError("재검증 기록 디렉터리는 심볼릭 링크일 수 없다")
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "records.lock"
    if lock_path.is_symlink():
        raise ValueError("재검증 잠금은 심볼릭 링크일 수 없다")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = directory / "records.json"
        if path.is_symlink():
            raise ValueError("재검증 기록은 심볼릭 링크일 수 없다")
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
            raise ValueError("손상된 재검증 기록")
        yield path, data


def _save(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".records-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical(data) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _identity(kind, key):
    if kind not in ("context", "ontology", "task") or not isinstance(key, str) or not key.strip():
        raise ValueError("재검증 종류·key가 올바르지 않다")
    return _canonical([kind, key])


def mark(root, kind, key, *, fingerprint, metadata):
    identity = _identity(kind, key)
    if not isinstance(fingerprint, str) or not fingerprint or not isinstance(metadata, dict):
        raise ValueError("재검증 지문·metadata가 올바르지 않다")
    # 입력이 JSON 왕복 가능함을 쓰기 전에 검사한다.
    metadata = json.loads(_canonical(metadata))
    with _store(root) as (path, data):
        old = data.get(identity)
        if old and old.get("fingerprint") == fingerprint:
            return old
        entry = dict(kind=kind, key=key, fingerprint=fingerprint, metadata=metadata,
                     needs_revalidation=True, created_at=datetime.now(timezone.utc).isoformat())
        data[identity] = entry
        _save(path, data)
        return entry


def pending(root, *, limit=100):
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("limit는 음수가 아닌 정수여야 한다")
    path = Path(root) / "revalidation" / "records.json"
    if not path.exists():
        return []
    with _store(root) as (_, data):
        return [v for _, v in sorted(data.items()) if v.get("needs_revalidation") is True][:limit]


def clear(root, kind, key, *, fingerprint):
    """처리한 지문과 현재 기록이 같을 때만 해제한다. 새 결과를 지우지 않는다."""
    identity = _identity(kind, key)
    with _store(root) as (path, data):
        if identity not in data or data[identity].get("fingerprint") != fingerprint:
            return False
        del data[identity]
        _save(path, data)
        return True


def marked_documents(paths):
    """기존 생성기 표기만 읽는다. 전체 문서를 재생성 대상으로 삼지 않는다."""
    import yaml
    documents = []
    context = Path(getattr(paths, "context", Path(paths.root) / "context"))
    ontology = Path(getattr(paths, "ontology", Path(paths.root) / "ontology"))
    # 항목 단위 symlink 검사만으로는 루트 자체가 트윈 밖을 가리키는 경우를 못 막는다.
    twin = Path(paths.root).resolve()
    for scan_root in (context, ontology, ontology / "domains"):
        if scan_root.is_symlink() or (scan_root.exists()
                                      and not scan_root.resolve().is_relative_to(twin)):
            raise ValueError(f"재검증 스캔 루트가 트윈 경계 밖이다: {scan_root}")
    if context.is_dir():
        for path in sorted(context.rglob("*.md")):
            if path.is_symlink():
                continue
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                continue
            _, header, *_rest = text.split("---", 2) if text.count("---") >= 2 else ("", "", "")
            meta = yaml.safe_load(header) or {}
            if isinstance(meta, dict) and meta.get("needs_revalidation") is True:
                documents.append(dict(kind="context", key=path.relative_to(context).as_posix()[:-3],
                                      path=path, source_files=meta.get("generation_source_files"),
                                      source_fingerprint=meta.get("generation_source_fingerprint")))
    domains = ontology / "domains"
    if domains.is_dir():
        from ..ontology import yaml_io, package
        for path in sorted(domains.glob("*/" + package.MANIFEST)):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            meta = (yaml_io.read(path) or {}).get("generation") or {}
            if isinstance(meta, dict) and meta.get("needs_revalidation") is True:
                documents.append(dict(kind="ontology", key=path.parent.name, path=path.parent,
                                      source_files=meta.get("source_files"),
                                      source_fingerprint=meta.get("source_fingerprint")))
    return documents


def _attempts_path(paths):
    directory = Path(paths.root) / "revalidation"
    if directory.is_symlink():
        raise ValueError("재검증 기록 디렉터리는 심볼릭 링크일 수 없다")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "document_attempts.json"
    if path.is_symlink():
        raise ValueError("재검증 시도 기록은 심볼릭 링크일 수 없다")
    return path


def _read_attempts(paths):
    path = _attempts_path(paths)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("손상된 재검증 시도 기록")
    return data


def run_documents(paths, *, limit=2, context_runner=None, ontology_runner=None):
    """표시된 대상만 기존 게이트로 재합성한다. 실패·변경 시에는 표시를 남긴다.

    `limit` 은 재합성 호출 수다 — 소스 변경·경계 거절처럼 호출 전에 끝나는 대상은 세지 않는다.
    호출한 대상은 시도 시각을 남겨 다음 주기에 가장 오래 안 본 것부터 고른다. 그러지 않으면
    정렬 앞쪽의 영구 실패가 매 주기 예산을 먹어 뒤 문서가 영영 안 돈다.
    """
    from ..context_synth import synth as context_synth
    from ..ontology import synth as ontology_synth
    context_runner = context_runner or context_synth.synthesize_group
    ontology_runner = ontology_runner or ontology_synth.refresh_domain
    attempts = _read_attempts(paths)
    entries = marked_documents(paths)
    entries.sort(key=lambda e: attempts.get(_identity(e["kind"], e["key"]), ""))
    outcomes = []
    calls = 0
    for entry in entries:
        if calls >= limit:
            break
        outcome = dict(kind=entry["kind"], key=entry["key"], ok=False)
        try:
            source_hash = source_fingerprint(paths, entry["source_files"])
            if source_hash != entry["source_fingerprint"]:
                outcome["reason"] = "소스 변경 — 표시와 기존 결과 보존"
                outcomes.append(outcome)
                continue
            artifact_hash = artifact_fingerprint(entry["path"])
            args = dict(cloud_only=True, expected_source_fingerprint=source_hash,
                        expected_artifact_fingerprint=artifact_hash)
            calls += 1
            attempts[_identity(entry["kind"], entry["key"])] = datetime.now(timezone.utc).isoformat()
            _save(_attempts_path(paths), attempts)
            if entry["kind"] == "context":
                result = context_runner(paths, entry["key"], entry["source_files"], **args)
                outcome["ok"] = bool(result.written and not result.needs_revalidation)
                outcome["reason"] = result.reason
            else:
                result = ontology_runner(paths, entry["key"], **args)
                outcome["ok"] = bool(result.ok and result.written and not result.needs_revalidation)
                outcome["reason"] = " / ".join(result.reasons)
        except (OSError, ValueError, TypeError) as exc:
            outcome["reason"] = f"재검증 실패 — {type(exc).__name__}: {exc}"
        outcomes.append(outcome)
    return dict(ok=all(o["ok"] for o in outcomes), entries=len(outcomes), outcomes=outcomes,
                reason="; ".join(o.get("reason", "") for o in outcomes if not o["ok"]))
