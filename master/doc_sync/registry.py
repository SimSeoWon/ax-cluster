"""명시적으로 등록된 문서와 근거만 읽는 수집기."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from master.doc_sync import DocSyncError, digest, read_text

MAX_DOCUMENT_CHARS = 500_000
_DENIED_PARTS = {'.git', '.ax', '.codex', '.claude', '.ssh', '.aws',
                 'node_modules', '__pycache__', '.venv', 'delivered', 'delivery',
                 'tokens', 'secrets', 'credentials'}


def _root(root):
    try:
        result = Path(root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        raise DocSyncError(f'잘못된 root: {root}') from exc
    if not result.is_dir():
        raise DocSyncError(f'root가 디렉토리가 아니다: {result}')
    return result


def _safe_name(path):
    for part in path.parts:
        name = part.lower()
        if (name in _DENIED_PARTS or name == '.env' or name.startswith('.env.')
                or name.endswith(('.pem', '.key'))
                or any(word in name for word in ('token', 'secret', 'credential'))):
            raise DocSyncError(f'비밀·운영 부산물 경로는 등록할 수 없다: {path}')


def _file(root, value, *, external_link=False):
    if not isinstance(value, str) or not value.strip():
        raise DocSyncError('파일 경로는 비어 있지 않은 문자열이어야 한다')
    given = Path(value)
    lexical = given if given.is_absolute() else root / given
    _safe_name(given)
    try:
        target = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DocSyncError(f'파일 경로를 찾을 수 없다: {value}') from exc
    if not target.is_relative_to(root):
        raise DocSyncError(f'root 밖 정본은 등록할 수 없다: {value}')
    if not lexical.is_relative_to(root) and not (external_link and lexical.is_symlink()):
        raise DocSyncError(f'외부 경로는 명시적 심볼릭링크만 허용한다: {value}')
    _safe_name(target.relative_to(root))
    if not target.is_file():
        raise DocSyncError(f'일반 파일이 아니다: {value}')
    return target


def load_registry(registry_path, root):
    """전체 등록목록을 검증하고 정본 상대경로를 덧붙인다."""
    root = _root(root)
    registry = _file(root, str(registry_path))
    try:
        data = json.loads(read_text(registry))
    except (ValueError, TypeError) as exc:
        raise DocSyncError(f'잘못된 등록 JSON: {registry}') from exc
    if (not isinstance(data, dict) or type(data.get('version')) is not int
            or data['version'] != 1 or not isinstance(data.get('documents'), list)):
        raise DocSyncError('등록목록은 version=1, documents 배열이어야 한다')
    documents, seen_ids, seen_targets = [], set(), set()
    for entry in data['documents']:
        if not isinstance(entry, dict):
            raise DocSyncError('문서 등록은 객체여야 한다')
        doc_id = entry.get('id')
        if not isinstance(doc_id, str) or not doc_id.strip() or doc_id in seen_ids:
            raise DocSyncError(f'비어 있거나 중복된 문서 id: {doc_id}')
        if (not isinstance(entry.get('role'), str) or not entry['role'].strip()
                or type(entry.get('protected')) is not bool
                or not isinstance(entry.get('instructions'), str)
                or not isinstance(entry.get('evidence'), list)):
            raise DocSyncError(f'문서 필드가 올바르지 않다: {doc_id}')
        target = _file(root, entry.get('path'), external_link=True)
        relative = target.relative_to(root).as_posix()
        if relative in seen_targets:
            raise DocSyncError(f'중복 문서 정본: {relative}')
        protected = (Path(entry['path']).name.upper() in {'CLAUDE.MD', 'AGENTS.MD'}
                     or target.name.lower() in {'sim-desktop-agents.md', 'sim-desktop-claude.md',
                                               'sim-desktop.md'}
                     or target.name.upper() in {'CLAUDE.MD', 'AGENTS.MD'})
        if protected and not entry['protected']:
            raise DocSyncError(f'자동 로드 문서는 protected=true가 필요하다: {doc_id}')
        evidence = []
        for source in entry['evidence']:
            path = _file(root, source)
            evidence.append(path.relative_to(root).as_posix())
        documents.append(dict(entry, target=relative, evidence=evidence))
        seen_ids.add(doc_id)
        seen_targets.add(relative)
    return {'version': 1, 'documents': documents}


def _git(root, *args):
    try:
        result = subprocess.run(['git', '-C', str(root), *args],
                                capture_output=True, check=False)
    except OSError as exc:
        raise DocSyncError(f'Git 실행 실패: {exc}') from exc
    if result.returncode:
        raise DocSyncError(f'Git 조회 실패 (rc={result.returncode}): '
                           f'{result.stderr.decode("utf-8", errors="replace").strip()}')
    return result.stdout


def _changes(root, since, until):
    commits = []
    for value in (since, until or 'HEAD'):
        if not isinstance(value, str) or not value.strip():
            raise DocSyncError('변경 범위는 비어 있지 않은 커밋이어야 한다')
        commits.append(_git(root, 'rev-parse', '--verify', '--end-of-options',
                            value + '^{commit}').decode('ascii').strip())
    # rename을 삭제+추가로 보아 이전/새 경로 모두 의존 대조에 포함한다.
    raw = _git(root, 'diff', '--name-only', '-z', '--no-renames', *commits, '--')
    try:
        paths = sorted(set(raw.decode('utf-8').rstrip('\0').split('\0'))) if raw else []
    except UnicodeError as exc:
        raise DocSyncError('Git 변경 경로는 UTF-8이어야 한다') from exc
    return {'since': commits[0], 'until': commits[1], 'changed_paths': paths,
            'included': [], 'excluded': []}


def collect(root, registry_path, ids=None, *, since=None, until=None):
    """원문·근거 해시를 보존하며 읽기 전용 계획을 만든다."""
    root = _root(root)
    registry = _file(root, str(registry_path))
    manifest = load_registry(registry, root)
    if ids is not None and (not isinstance(ids, (list, tuple, set))
                            or any(not isinstance(i, str) for i in ids)):
        raise DocSyncError('ids는 문서 id 목록이어야 한다')
    selected = set(ids) if ids is not None else None
    known = {doc['id'] for doc in manifest['documents']}
    if selected is not None and selected - known:
        raise DocSyncError(f'등록되지 않은 문서 id: {sorted(selected - known)}')
    if until is not None and since is None:
        raise DocSyncError('until에는 since가 필요하다')
    selection = _changes(root, since, until) if since is not None else None
    if selection is not None:
        selection['content_source'] = 'current-working-tree'
        selection['content_head'] = _git(root, 'rev-parse', 'HEAD').decode('ascii').strip()
        selection['working_tree_dirty'] = bool(_git(root, 'status', '--porcelain', '-z'))
        selection['registry_changed'] = registry.relative_to(root).as_posix() in selection['changed_paths']
    documents = []
    for entry in manifest['documents']:
        matched = (sorted(set(selection['changed_paths']) &
                          {entry['target'], *entry['evidence']}) if selection else [])
        if selection is not None:
            reason = ('explicit-id-filter' if selected is not None and entry['id'] not in selected
                      else 'registry-changed' if selection['registry_changed']
                      else 'registered-dependency-changed' if matched
                      else 'no-registered-dependency-change')
            bucket = 'included' if reason in ('registry-changed', 'registered-dependency-changed') else 'excluded'
            selection[bucket].append({'id': entry['id'], 'reason': reason,
                                      'matched_paths': matched})
            if bucket == 'excluded':
                continue
        if selected is not None and entry['id'] not in selected:
            continue
        before = read_text(root / entry['target'])
        size = len(before)
        evidence = []
        for source in entry['evidence']:
            text = read_text(root / source)
            size += len(text)
            if size > MAX_DOCUMENT_CHARS:
                raise DocSyncError(f'문서·근거 크기 제한 초과: {entry["id"]}')
            evidence.append({'path': source, 'sha256': digest(text), 'text': text})
        if size > MAX_DOCUMENT_CHARS:
            raise DocSyncError(f'문서·근거 크기 제한 초과: {entry["id"]}')
        documents.append(dict(entry, before=before, before_sha256=digest(before), evidence=evidence))
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=False)
        head = result.stdout.strip() if result.returncode == 0 else ''
    except OSError:
        head = ''
    plan = {'schema_version': 1, 'root': str(root), 'registry': str(registry),
            'registry_hash': digest(read_text(registry)), 'head': head, 'documents': documents}
    if selection is not None:
        plan['selection'] = selection
    return plan
