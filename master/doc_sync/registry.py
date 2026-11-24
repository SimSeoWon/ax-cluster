"""명시적으로 등록된 문서와 근거만 읽는 수집기.

inventory=true 문서에는 등록 근거 뒤에 결정적 인벤토리(가상 경로 INVENTORY_PATH)를
붙인다 — 운영 모듈·스킬·MCP 도구의 짧은 목록이며 파일 본문은 싣지 않는다 (#1016).
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

from master.doc_sync import DocSyncError, digest, read_text

MAX_DOCUMENT_CHARS = 500_000
_DENIED_PARTS = {'.git', '.ax', '.codex', '.claude', '.ssh', '.aws',
                 'node_modules', '__pycache__', '.venv', 'delivered', 'delivery',
                 'tokens', 'secrets', 'credentials'}
# 인벤토리 가상 근거. 실제 파일이 아니므로 _file 검증을 거치지 않는다.
INVENTORY_PATH = 'inventory:master'
INVENTORY_REASON = 'inventory-source-changed'
_MCP_SERVERS = ('master/projects/mcp_server.py', 'master/task_queue/mcp_server.py')


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
                or not isinstance(entry.get('evidence'), list)
                or type(entry.get('inventory', False)) is not bool):
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


def _is_module_path(path):
    """운영 모듈 판정 — 경로 모양만 본다(삭제된 경로도 판정 가능해야 한다)."""
    pure = PurePosixPath(path)
    if (len(pure.parts) < 2 or pure.parts[0] != 'master' or pure.suffix != '.py'
            or pure.name.startswith('test_') or 'tests' in pure.parts[:-1]):
        return False
    try:
        _safe_name(Path(*pure.parts))
    except DocSyncError:
        return False
    return True


def _is_skill_path(path):
    parts = PurePosixPath(path).parts
    return len(parts) == 4 and parts[:2] == ('master', 'skills') and parts[3] == 'SKILL.md'


def is_inventory_source(path):
    """--since 대조용: 이 경로가 바뀌면 인벤토리 문서가 영향을 받는다."""
    return _is_module_path(path) or _is_skill_path(path) or path in _MCP_SERVERS


def _modules(root):
    """master/ 아래 운영 모듈의 root 기준 posix 경로(정렬). 심볼릭링크는 따라가지 않는다."""
    base = root / 'master'
    found = []
    if not base.is_dir() or base.is_symlink():
        return found
    for current, dirs, files in os.walk(base, followlinks=False):
        here = Path(current)
        dirs[:] = [d for d in dirs if not (here / d).is_symlink()]
        for name in files:
            full = here / name
            if full.is_symlink() or not full.is_file():
                continue
            relative = full.relative_to(root).as_posix()
            if _is_module_path(relative):
                found.append(relative)
    return sorted(found)


def _parse(root, relative):
    try:
        return ast.parse(read_text(root / relative))
    except DocSyncError:
        return None
    except (SyntaxError, ValueError):
        return False


def _docline(tree):
    if tree is None:
        return '(읽기 실패)'
    if tree is False:
        return '(구문 오류)'
    doc = ast.get_docstring(tree)
    lines = [line.strip() for line in (doc or '').splitlines() if line.strip()]
    return lines[0] if lines else '(docstring 없음)'


def _skill_line(root, relative):
    try:
        text = read_text(root / relative)
    except DocSyncError:
        return '(읽기 실패)'
    lines = text.splitlines()
    if lines and lines[0].strip() == '---':
        for line in lines[1:]:
            if line.strip() == '---':
                break
            if line.startswith('description:'):
                value = line[len('description:'):].strip().strip('"\'')
                return value or '(description 없음)'
    return '(description 없음)'


def _is_tool_decorator(node):
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Attribute) and target.attr == 'tool'


def _tools(tree):
    """@<server>.tool() 로 꾸민 최상위 함수 이름. import 하지 않고 AST 로만 읽는다."""
    names = []
    for node in tree.body:
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(_is_tool_decorator(d) for d in node.decorator_list)):
            names.append(node.name)
    return sorted(names)


def build_inventory(root):
    """운영 모듈·스킬·MCP 도구의 결정적 목록. 같은 작업 트리면 같은 텍스트다."""
    modules = _modules(root)
    out = ['# 운영 모듈 (master/**/*.py, 테스트 제외) — 경로 — docstring 첫 줄']
    out += [f'{path} — {_docline(_parse(root, path))}' for path in modules]
    skills_dir = root / 'master' / 'skills'
    skills = sorted(p.relative_to(root).as_posix() for p in skills_dir.glob('*/SKILL.md')
                    if p.is_file() and not p.is_symlink()) if skills_dir.is_dir() else []
    out += ['', '# 스킬 (master/skills/*/SKILL.md) — 이름 — description']
    out += [f'{PurePosixPath(path).parts[2]} — {_skill_line(root, path)}' for path in skills]
    tool_count = 0
    for server in _MCP_SERVERS:
        if not (root / server).is_file():
            continue
        tree = _parse(root, server)
        out += ['', f'# MCP 도구 ({server}, @*.tool() 데코레이터)']
        if tree in (None, False):
            out.append(_docline(tree))
            continue
        names = _tools(tree)
        tool_count += len(names)
        out += names or ['(도구 없음)']
    print(f'[doc-sync] 인벤토리: 모듈 {len(modules)} · 스킬 {len(skills)} · '
          f'MCP 도구 {tool_count}', file=sys.stderr)
    return '\n'.join(out) + '\n', modules


def _mentioned(text, path):
    """문서 본문이 모듈을 언급하는가.

    규칙: root 기준 경로(master/a/b.py), master/ 기준 경로(a/b.py), 점 표기
    (master.a.b) 중 하나가 부분 문자열로 있거나, 이름(stem)이 단어 경계로 있으면 언급이다.
    __init__/__main__ 은 이름 대신 소속 패키지 디렉토리 이름을 쓴다. 단어 경계는 \w 기준이라
    'logic' 은 'logic_claim' 에 걸리지 않는다. 목록 전용(판정·거절에 쓰지 않는다).
    """
    pure = PurePosixPath(path)
    inner = PurePosixPath(*pure.parts[1:])
    dotted = '.'.join(pure.with_suffix('').parts)
    if any(form in text for form in (path, inner.as_posix(), dotted)):
        return True
    name = pure.parent.name if pure.stem in ('__init__', '__main__') else pure.stem
    return bool(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text))


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
    documents, inventory = [], None
    for entry in manifest['documents']:
        matched = (sorted(set(selection['changed_paths']) &
                          {entry['target'], *entry['evidence']}) if selection else [])
        if selection is not None:
            reason = ('explicit-id-filter' if selected is not None and entry['id'] not in selected
                      else 'registry-changed' if selection['registry_changed']
                      else 'registered-dependency-changed' if matched
                      else 'no-registered-dependency-change')
            if reason == 'no-registered-dependency-change' and entry.get('inventory'):
                sources = sorted(p for p in selection['changed_paths'] if is_inventory_source(p))
                if sources:
                    reason, matched = INVENTORY_REASON, sources
            bucket = ('included' if reason in ('registry-changed', 'registered-dependency-changed',
                                               INVENTORY_REASON) else 'excluded')
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
        extra = {}
        if entry.get('inventory'):
            if inventory is None:
                inventory = build_inventory(root)
            text, modules = inventory
            size += len(text)
            evidence.append({'path': INVENTORY_PATH, 'sha256': digest(text), 'text': text})
            extra['undocumented'] = [m for m in modules if not _mentioned(before, m)]
            print(f'[doc-sync] 인벤토리 근거: {entry["id"]} {len(text)}자 · '
                  f'문서 미언급 모듈 {len(extra["undocumented"])}/{len(modules)}', file=sys.stderr)
        if size > MAX_DOCUMENT_CHARS:
            raise DocSyncError(f'문서·근거 크기 제한 초과: {entry["id"]}')
        documents.append(dict(entry, before=before, before_sha256=digest(before),
                              evidence=evidence, **extra))
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
