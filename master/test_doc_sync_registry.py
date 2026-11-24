"""등록문서 경계·원문·선택 수집 회귀 검사 (#838)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.doc_sync import DocSyncError, digest
from master.doc_sync.registry import (INVENTORY_PATH, INVENTORY_REASON, build_inventory,
                                      collect, is_inventory_source, load_registry)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        (self.root / 'README.md').write_bytes('한글\r\n원문\n'.encode())
        (self.root / 'source.py').write_text('answer = 42\n', encoding='utf-8')
        self.registry = self.root / 'documents.json'
        self.entry = dict(id='readme', path='README.md', role='overview',
                          evidence=['source.py'], protected=False, instructions='근거 준수')
        self.save([self.entry])

    def save(self, entries):
        self.registry.write_text(json.dumps(dict(version=1, documents=entries)), encoding='utf-8')

    def test_original_selection_and_read_only(self):
        before = (self.root / 'README.md').read_bytes()
        plan = collect(self.root, self.registry, ['readme'])
        doc = plan['documents'][0]
        self.assertEqual(doc['before'], '한글\r\n원문\n')
        self.assertEqual(doc['before_sha256'], digest(doc['before']))
        self.assertEqual(doc['evidence'][0]['text'], 'answer = 42\n')
        self.assertEqual(collect(self.root, self.registry, [])['documents'], [])
        self.assertEqual((self.root / 'README.md').read_bytes(), before)
        with self.assertRaises(DocSyncError):
            collect(self.root, self.registry, ['missing'])

    def test_external_explicit_symlink_and_protection(self):
        link = Path(self.temp.name) / 'CLAUDE.md'
        link.symlink_to(self.root / 'README.md')
        self.save([dict(self.entry, path=str(link), protected=True)])
        self.assertEqual(collect(self.root, self.registry)['documents'][0]['target'], 'README.md')
        self.assertTrue(link.is_symlink())
        self.save([dict(self.entry, path=str(link), protected=False)])
        with self.assertRaises(DocSyncError):
            load_registry(self.registry, self.root)

    def test_sim_desktop_canonical_documents_require_protection(self):
        machines = self.root / 'machines'
        machines.mkdir()
        for name in ('sim-desktop.md', 'sim-desktop-agents.md'):
            (machines / name).write_text('운영 지침', encoding='utf-8')
            with self.subTest(name=name):
                self.save([dict(self.entry, path=f'machines/{name}')])
                with self.assertRaises(DocSyncError):
                    load_registry(self.registry, self.root)
                self.save([dict(self.entry, path=f'machines/{name}', protected=True)])
                self.assertTrue(load_registry(self.registry, self.root)['documents'][0]['protected'])

    def test_escaping_symlink_and_duplicate_target(self):
        outside = Path(self.temp.name) / 'outside.md'
        outside.write_text('external', encoding='utf-8')
        (self.root / 'escape.md').symlink_to(outside)
        self.save([dict(self.entry, path='escape.md')])
        with self.assertRaises(DocSyncError):
            collect(self.root, self.registry)
        (self.root / 'alias.md').symlink_to(self.root / 'README.md')
        self.save([self.entry, dict(self.entry, id='alias', path='alias.md')])
        with self.assertRaises(DocSyncError):
            load_registry(self.registry, self.root)

    def test_invalid_inputs(self):
        for path in ['missing.md', '.', '.env', 'api-token.txt']:
            if path not in ['missing.md', '.']:
                (self.root / path).write_text('private', encoding='utf-8')
            with self.subTest(path=path):
                self.save([dict(self.entry, evidence=[path])])
                with self.assertRaises(DocSyncError):
                    collect(self.root, self.registry)
        self.save([self.entry, self.entry])
        with self.assertRaises(DocSyncError):
            load_registry(self.registry, self.root)
        self.registry.write_text('{broken', encoding='utf-8')
        with self.assertRaises(DocSyncError):
            load_registry(self.registry, self.root)

    def test_utf8_and_limit_are_errors(self):
        (self.root / 'source.py').write_bytes(b'\xff')
        with self.assertRaises(DocSyncError):
            collect(self.root, self.registry)
        (self.root / 'source.py').write_text('x' * 500_001, encoding='utf-8')
        with self.assertRaises(DocSyncError):
            collect(self.root, self.registry)


class ImpactTests(unittest.TestCase):
    """임시 Git 저장소로 실제 커밋 범위와 현재 파일의 경계를 검사한다."""

    def setUp(self):
        RegistryTests.setUp(self)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Doc Sync Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()

    save = RegistryTests.save

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def test_source_change_exact_match_and_id_intersection(self):
        (self.root / 'other.md').write_text('other', encoding='utf-8')
        (self.root / 'unrelated.py').write_text('other', encoding='utf-8')
        self.save([self.entry, dict(self.entry, id='other', path='other.md',
                                    evidence=['unrelated.py'])])
        self.commit()
        base = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'source.py').write_text('answer = 43\n', encoding='utf-8')
        self.commit()
        plan = collect(self.root, self.registry, since=base)
        self.assertEqual([d['id'] for d in plan['documents']], ['readme'])
        self.assertEqual(plan['selection']['included'][0]['matched_paths'], ['source.py'])
        self.assertEqual(plan['selection']['excluded'][0]['reason'], 'no-registered-dependency-change')
        selected = collect(self.root, self.registry, ['other'], since=base)
        self.assertEqual(selected['documents'], [])
        self.assertEqual(selected['selection']['excluded'][0]['reason'], 'explicit-id-filter')

    def test_registry_change_includes_all_documents(self):
        self.save([dict(self.entry, instructions='new instruction')])
        self.commit()
        plan = collect(self.root, self.registry, since=self.base)
        self.assertTrue(plan['selection']['registry_changed'])
        self.assertEqual(plan['selection']['included'][0]['reason'], 'registry-changed')

    def test_rename_and_delete_paths_are_preserved(self):
        self.git('mv', 'source.py', 'renamed.py')
        (self.root / 'unused.py').write_text('unused', encoding='utf-8')
        self.save([dict(self.entry, evidence=['renamed.py'])])
        self.commit()
        paths = collect(self.root, self.registry, since=self.base)['selection']['changed_paths']
        self.assertIn('source.py', paths)
        self.assertIn('renamed.py', paths)
        base = self.git('rev-parse', 'HEAD').strip()
        self.git('rm', 'unused.py')
        self.commit()
        plan = collect(self.root, self.registry, since=base)
        self.assertEqual(plan['documents'], [])
        self.assertEqual(plan['selection']['changed_paths'], ['unused.py'])

    def test_no_changes_and_historical_range_uses_current_content_explicitly(self):
        plan = collect(self.root, self.registry, since=self.base)
        self.assertEqual(plan['documents'], [])
        self.assertEqual(plan['selection']['changed_paths'], [])
        (self.root / 'source.py').write_text('committed\n', encoding='utf-8')
        self.commit()
        end = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'source.py').write_text('latest\n', encoding='utf-8')
        self.commit()
        (self.root / 'README.md').write_text('uncommitted\n', encoding='utf-8')
        plan = collect(self.root, self.registry, since=self.base, until=end)
        self.assertEqual(plan['selection']['until'], end)
        self.assertNotEqual(plan['selection']['content_head'], end)
        self.assertEqual(plan['selection']['content_source'], 'current-working-tree')
        self.assertTrue(plan['selection']['working_tree_dirty'])
        self.assertEqual(plan['documents'][0]['before'], 'uncommitted\n')
        self.assertEqual(plan['documents'][0]['evidence'][0]['text'], 'latest\n')

    def test_bad_revision_and_until_without_since_are_errors(self):
        with self.assertRaisesRegex(DocSyncError, 'Git 조회 실패'):
            collect(self.root, self.registry, since='missing-commit')
        with self.assertRaisesRegex(DocSyncError, 'since'):
            collect(self.root, self.registry, until='HEAD')


class InventoryTests(unittest.TestCase):
    """inventory=true 문서의 결정적 인벤토리·--since 새 사유·미언급 목록 (#1016)."""

    def setUp(self):
        ImpactTests.setUp(self)
        files = {
            'master/alpha.py': '"""알파 모듈.\n\n자세히."""\n',
            'master/pkg/__init__.py': '',
            'master/pkg/beta.py': 'x = 1\n',
            'master/pkg/broken.py': 'def (:\n',
            'master/test_alpha.py': '"""테스트."""\n',
            'master/pkg/tests/helper.py': '"""헬퍼."""\n',
            'master/skills/ax-demo/SKILL.md': '---\nname: ax-demo\ndescription: 데모 스킬\n---\n본문\n',
            'master/projects/mcp_server.py': ('mcp = object()\n@mcp.tool()\ndef b_tool():\n    pass\n'
                                              '@mcp.tool()\ndef a_tool():\n    pass\n'
                                              'def helper_tool():\n    pass\n'),
        }
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        cache = self.root / 'master' / '__pycache__'
        cache.mkdir()
        (cache / 'alpha.py').write_text('', encoding='utf-8')
        (self.root / 'README.md').write_text('alpha 와 pkg/beta.py 를 설명한다\n', encoding='utf-8')
        self.entry = dict(self.entry, inventory=True)
        self.save([self.entry, dict(self.entry, id='plain', path='plain.md', inventory=False)])
        (self.root / 'plain.md').write_text('plain\n', encoding='utf-8')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()

    save = RegistryTests.save
    git = ImpactTests.git
    commit = ImpactTests.commit

    def test_inventory_is_deterministic_virtual_evidence(self):
        first = collect(self.root, self.registry)
        second = collect(self.root, self.registry)
        doc, plain = first['documents']
        item = doc['evidence'][-1]
        self.assertEqual([e['path'] for e in doc['evidence']], ['source.py', INVENTORY_PATH])
        self.assertEqual(item['sha256'], digest(item['text']))
        self.assertEqual(item, second['documents'][0]['evidence'][-1])
        self.assertFalse((self.root / INVENTORY_PATH).exists())
        text = item['text']
        self.assertIn('master/alpha.py — 알파 모듈.', text)
        self.assertIn('master/pkg/beta.py — (docstring 없음)', text)
        self.assertIn('master/pkg/broken.py — (구문 오류)', text)
        self.assertIn('ax-demo — 데모 스킬', text)
        self.assertLess(text.index('a_tool'), text.index('b_tool'))
        self.assertNotIn('helper_tool', text)
        for excluded in ('test_alpha', 'tests/helper', '__pycache__'):
            self.assertNotIn(excluded, text)
        self.assertEqual([e['path'] for e in plain['evidence']], ['source.py'])
        self.assertNotIn('undocumented', plain)

    def test_undocumented_lists_unmentioned_modules(self):
        doc = collect(self.root, self.registry, ['readme'])['documents'][0]
        # pkg/__init__.py 는 패키지 이름 pkg 로 언급된 것으로 본다(pkg/beta.py).
        self.assertEqual(doc['undocumented'], ['master/pkg/broken.py',
                                               'master/projects/mcp_server.py'])

    def test_inventory_counts_toward_size_limit(self):
        _, modules = build_inventory(self.root)
        size = len(build_inventory(self.root)[0])
        self.assertTrue(modules)
        (self.root / 'source.py').write_text('x' * (500_000 - size - len('alpha 와 pkg/beta.py 를 설명한다\n') + 1),
                                             encoding='utf-8')
        self.save([dict(self.entry, inventory=False)])
        collect(self.root, self.registry)
        self.save([self.entry])
        with self.assertRaisesRegex(DocSyncError, '크기 제한'):
            collect(self.root, self.registry)

    def test_invalid_inventory_type(self):
        self.save([dict(self.entry, inventory='yes')])
        with self.assertRaises(DocSyncError):
            load_registry(self.registry, self.root)

    def test_source_paths_by_pattern(self):
        for path in ('master/gone.py', 'master/skills/x/SKILL.md', 'master/projects/mcp_server.py',
                     'master/task_queue/mcp_server.py'):
            self.assertTrue(is_inventory_source(path), path)
        for path in ('master/test_gone.py', 'master/a/tests/x.py', 'master/__pycache__/a.py',
                     'master/api_token.py', 'docs/a.py', 'master/skills/x/notes.md', 'master/a.txt'):
            self.assertFalse(is_inventory_source(path), path)

    def test_since_includes_on_module_change_and_deletion(self):
        (self.root / 'master' / 'gamma.py').write_text('"""새 모듈."""\n', encoding='utf-8')
        self.git('rm', '-q', 'master/pkg/beta.py')
        (self.root / 'master' / 'test_alpha.py').write_text('changed\n', encoding='utf-8')
        self.commit()
        plan = collect(self.root, self.registry, since=self.base)
        self.assertEqual([d['id'] for d in plan['documents']], ['readme'])
        included = plan['selection']['included'][0]
        self.assertEqual(included['reason'], INVENTORY_REASON)
        self.assertEqual(included['matched_paths'], ['master/gamma.py', 'master/pkg/beta.py'])
        self.assertEqual(plan['selection']['excluded'][0],
                         {'id': 'plain', 'reason': 'no-registered-dependency-change',
                          'matched_paths': []})
        self.assertIn('master/gamma.py — 새 모듈.', plan['documents'][0]['evidence'][-1]['text'])

    def test_since_test_only_change_and_precedence(self):
        (self.root / 'master' / 'test_alpha.py').write_text('changed\n', encoding='utf-8')
        self.commit()
        plan = collect(self.root, self.registry, since=self.base)
        self.assertEqual(plan['documents'], [])
        base = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'master' / 'alpha.py').write_text('y = 2\n', encoding='utf-8')
        (self.root / 'source.py').write_text('answer = 43\n', encoding='utf-8')
        self.commit()
        plan = collect(self.root, self.registry, since=base)
        self.assertEqual(plan['selection']['included'][0]['reason'], 'registered-dependency-changed')
        self.assertEqual(plan['selection']['included'][0]['matched_paths'], ['source.py'])
        filtered = collect(self.root, self.registry, ['plain'], since=base)
        self.assertEqual(filtered['selection']['excluded'][0]['reason'], 'explicit-id-filter')


if __name__ == '__main__':
    unittest.main()
