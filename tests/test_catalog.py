from catalog.historical_delivery import read_delivery
from catalog.manifests import get_manifest, publish_manifest
from catalog.workroom import initialize_workroom
from correction.requests import AccentEdit, CorrectionRequest
from correction.settlement import apply_correction
from issue.issued_sheets import get_issued_sheet
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import freeze_revision
from revision.heads import get_head
from tests import WorkroomTestCase


class TestCatalog(WorkroomTestCase):
    def correct(self, row, revision_id, replacement):
        sheet = issue_proof_sheet(self.db, freeze_revision(self.db, row.label_id, revision_id))
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(1, 2, replacement),)))
        return sheet, result

    def two_publications(self):
        row, = self.import_labels('é')
        before = publish_manifest(self.db, [row.label_id])
        sheet, result = self.correct(row, row.revision_id, '\u0300')
        after = publish_manifest(self.db, [row.label_id])
        return row, before, sheet, result, after

    def test_historical_retrieval(self):
        row, before, sheet, result, after = self.two_publications()
        self.reopen()
        old = read_delivery(self.db, 'manifest', before.manifest_id).entries[0]
        new = read_delivery(self.db, 'manifest', after.manifest_id).entries[0]
        self.assertEqual((old.entry.revision_id, new.entry.revision_id),
                         (row.revision_id, result.revision.revision_id))
        self.assertEqual((old.source.revision.original, new.source.revision.original),
                         (b'\xc3\xa9', b'e\xcc\x80'))
        self.assertEqual((old.entry.source, new.entry.source), (row.source, row.source))
        self.assertIsNone(old.entry.receipt_id)
        self.assertEqual(new.entry.receipt_id, result.receipt.receipt_id)
        delivered = read_delivery(self.db, 'receipt', result.receipt.receipt_id)
        self.assertEqual((delivered.sheet, delivered.parent, delivered.successor),
                         (sheet, old.source.revision, new.source))

    def test_roster_order(self):
        first, second = self.import_labels('Moss', 'Fern')
        roster = [second.label_id, first.label_id, second.label_id]
        manifest = publish_manifest(self.db, roster)
        self.assertEqual([(entry.position, entry.label_id) for entry in manifest.entries], list(enumerate(roster)))
        self.reopen()
        delivered = read_delivery(self.db, 'manifest', manifest.manifest_id)
        self.assertEqual([item.entry for item in delivered.entries], list(manifest.entries))
        self.assertEqual([item.entry.source for item in delivered.entries], [second.source, first.source, second.source])
        self.assertEqual([item.source.revision.original for item in delivered.entries], [b'Fern', b'Moss', b'Fern'])

    def test_invalid_roster(self):
        row, = self.import_labels('Moss')
        with self.assertRaises(KeyError):
            publish_manifest(self.db, [row.label_id, 999])
        with self.assertRaises(ValueError):
            publish_manifest(self.db, None)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM manifests').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM manifest_entries').fetchone()[0], 0)

    def test_empty_roster(self):
        manifest = publish_manifest(self.db, [])
        self.reopen()
        self.assertEqual(get_manifest(self.db, manifest.manifest_id), manifest)
        self.assertEqual(read_delivery(self.db, 'manifest', manifest.manifest_id).entries, ())

    def test_unknown_id(self):
        self.two_publications()
        for kind in ('manifest', 'revision', 'receipt'):
            with self.subTest(kind=kind), self.assertRaises(KeyError):
                read_delivery(self.db, kind, 999)

    def test_receipt_lineage(self):
        row, before, first_sheet, first, middle = self.two_publications()
        second_sheet, second = self.correct(row, first.revision.revision_id, '\u0302')
        after = publish_manifest(self.db, [row.label_id])
        self.reopen()
        old = read_delivery(self.db, 'receipt', first.receipt.receipt_id)
        new = read_delivery(self.db, 'receipt', second.receipt.receipt_id)
        self.assertEqual((old.sheet, new.sheet), (first_sheet, second_sheet))
        self.assertEqual(old.parent.revision_id, row.revision_id)
        self.assertEqual(old.successor.revision, first.revision)
        self.assertEqual(new.parent, first.revision)
        self.assertEqual(new.successor.revision, second.revision)
        for manifest, revision_id, receipt_id, raw in (
            (before, row.revision_id, None, b'\xc3\xa9'),
            (middle, first.revision.revision_id, first.receipt.receipt_id, b'e\xcc\x80'),
            (after, second.revision.revision_id, second.receipt.receipt_id, b'e\xcc\x82'),
        ):
            item = read_delivery(self.db, 'manifest', manifest.manifest_id).entries[0]
            self.assertEqual((item.entry.revision_id, item.entry.receipt_id), (revision_id, receipt_id))
            self.assertEqual(item.source.lineage.source, row.source)
            self.assertEqual(item.source.revision.original, raw)

    def test_reinitialize(self):
        row, before, sheet, result, after = self.two_publications()
        initialize_workroom(self.db)
        initialize_workroom(self.db)
        self.reopen()
        self.assertEqual(get_head(self.db, row.label_id), result.revision.revision_id)
        self.assertEqual(freeze_revision(self.db, row.label_id, row.revision_id).original, b'\xc3\xa9')
        self.assertEqual(read_delivery(self.db, 'revision', result.revision.revision_id).revision.original, b'e\xcc\x80')
        self.assertEqual(get_issued_sheet(self.db, sheet.sheet_id), sheet)
        self.assertEqual((get_manifest(self.db, before.manifest_id), get_manifest(self.db, after.manifest_id)),
                         (before, after))
        self.assertEqual(read_delivery(self.db, 'receipt', result.receipt.receipt_id).receipt, result.receipt)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM batches').fetchone()[0], 1)
        self.assertEqual(self.settlement_counts(), (2, 1))
