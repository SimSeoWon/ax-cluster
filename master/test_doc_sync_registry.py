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
from master.doc_sync.registry import collect, load_registry


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


if __name__ == '__main__':
    unittest.main()
