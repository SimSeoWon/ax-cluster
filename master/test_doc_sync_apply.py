"""문서 수정안의 승인·정본·오래된 입력 경계를 검사한다."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.doc_sync import DocSyncError, digest
from master.doc_sync.apply import apply_draft
from master.doc_sync.registry import collect


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = self.root / 'guide.md'
        self.doc.write_text('old\n', encoding='utf-8')
        (self.root / 'source.py').write_text('VALUE = 1\n', encoding='utf-8')
        self.registry = self.root / 'registry.json'
        self.entries = [dict(id='guide', path='guide.md', role='guide', protected=False,
                             instructions='', evidence=['source.py'])]
        self.save_registry()

    def save_registry(self):
        self.registry.write_text(json.dumps(dict(version=1, documents=self.entries)), encoding='utf-8')

    def artifact(self, after='new\n'):
        plan = collect(self.root, self.registry)
        for doc in plan['documents']:
            doc.update(decision='update', after=after, after_sha256=digest(after),
                       reason='refresh', citations=['source.py:1'], diff='')
        return plan

    def apply(self, artifact, **kwargs):
        return apply_draft(self.root, self.registry, artifact, **kwargs)

    def test_preview_and_explicit_selection(self):
        draft = self.artifact()
        self.assertEqual(self.apply(draft)['changed'], ['guide'])
        self.assertEqual(self.doc.read_text(), 'old\n')
        self.assertEqual(self.apply(draft, confirm=True)['skipped'], ['guide'])
        self.assertEqual(self.doc.read_text(), 'old\n')
        self.apply(draft, confirm=True, approved_ids=['guide'])
        self.assertEqual(self.doc.read_text(), 'new\n')
        self.assertEqual(self.apply(draft, confirm=True, approved_ids=['guide'])['unchanged'], ['guide'])

    def test_stale_document_and_evidence(self):
        draft = self.artifact()
        self.doc.write_text('someone else\n')
        with self.assertRaises(DocSyncError):
            self.apply(draft, confirm=True, approved_ids=['guide'])
        self.doc.write_text('old\n')
        (self.root / 'source.py').write_text('VALUE = 2\n')
        with self.assertRaises(DocSyncError):
            self.apply(draft)

    def test_registry_and_artifact_tampering(self):
        draft = self.artifact()
        for key, value in [('target', '../outside'), ('protected', True), ('before_sha256', '0')]:
            tampered = copy.deepcopy(draft)
            tampered['documents'][0][key] = value
            with self.assertRaises(DocSyncError):
                self.apply(tampered)
        self.entries[0]['instructions'] = 'changed'
        self.save_registry()
        with self.assertRaises(DocSyncError):
            self.apply(draft)

    def test_symlink_and_mode_preserved(self):
        link = self.root / 'entry.md'
        link.symlink_to('guide.md')
        self.entries[0]['path'] = 'entry.md'
        self.save_registry()
        self.doc.chmod(0o640)
        self.apply(self.artifact(), confirm=True, approved_ids=['guide'])
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(), 'new\n')
        self.assertEqual(self.doc.stat().st_mode & 0o777, 0o640)

    def test_protected_requires_distinct_approval(self):
        self.entries[0]['protected'] = True
        self.save_registry()
        draft = self.artifact()
        with self.assertRaises(DocSyncError):
            self.apply(draft, confirm=True, approved_ids=['guide'])
        self.apply(draft, confirm=True, approved_ids=['guide'], allow_protected=True)

    def test_marker_and_new_broken_links(self):
        self.doc.write_text('AX-ENTRY-MARK: test\n[old](missing.md)\n')
        with self.assertRaises(DocSyncError):
            self.apply(self.artifact('removed\n'))
        after = self.doc.read_text() + '[new](new-missing.md)\n'
        with self.assertRaises(DocSyncError):
            self.apply(self.artifact(after))
        after = self.doc.read_text() + '[web](https://example.org) [anchor](#test)\n```md\n[x](example.md)\n```\n'
        self.apply(self.artifact(after), confirm=True, approved_ids=['guide'])
        self.assertEqual(self.doc.read_text(), after)

    def test_all_documents_validated_before_any_write(self):
        (self.root / 'second.md').write_text('old\n')
        self.entries.append(dict(self.entries[0], id='second', path='second.md'))
        self.save_registry()
        draft = self.artifact()
        draft['documents'][1]['after_sha256'] = 'invalid'
        with self.assertRaises(DocSyncError):
            self.apply(draft, confirm=True, approved_ids=['guide', 'second'])
        self.assertEqual(self.doc.read_text(), 'old\n')

    def test_edited_artifact_cannot_remove_content_or_evidence(self):
        for changes in [dict(after=' \n', after_sha256=digest(' \n')),
                        dict(reason='  '), dict(citations=[]),
                        dict(citations=['unknown.py:1']),
                        dict(citations=['source.py:0']),
                        dict(citations=['source.py:2']),
                        dict(citations=['source.py:abc'])]:
            draft = self.artifact()
            draft['documents'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(DocSyncError):
                self.apply(draft, confirm=True, approved_ids=['guide'])
        self.assertEqual(self.doc.read_text(), 'old\n')

    def test_flags_require_bools_and_surrogate_is_rejected(self):
        for flags in [dict(confirm='yes'), dict(allow_protected=1)]:
            with self.assertRaises(DocSyncError):
                self.apply(self.artifact(), **flags)
        draft = self.artifact()
        draft['documents'][0]['after'] = '\ud800'
        with self.assertRaises(DocSyncError):
            self.apply(draft)


if __name__ == '__main__':
    unittest.main()
