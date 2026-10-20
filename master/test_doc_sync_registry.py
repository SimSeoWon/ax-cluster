"""등록문서 경계·원문·선택 수집 회귀 검사 (#838)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
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


if __name__ == '__main__':
    unittest.main()
