from catalog.historical_delivery import read_delivery
from intake.batches import import_batch
from intake.import_records import get_import_row
from intake.row_identity import RowIdentity
from revision.freeze import freeze_revision
from revision.heads import get_head
from tests import WorkroomTestCase


class TestIntake(WorkroomTestCase):
    def assert_empty_intake(self):
        counts = self.db.execute('''
            SELECT (SELECT COUNT(*) FROM batches), (SELECT COUNT(*) FROM import_rows),
                   (SELECT COUNT(*) FROM labels), (SELECT COUNT(*) FROM revisions),
                   (SELECT COUNT(*) FROM heads)
        ''').fetchone()
        self.assertEqual(counts, (0, 0, 0, 0, 0))

    def test_equal_text_distinct_rows(self):
        original = b'\xc3\xa9\xcc\xa3'
        first, second = import_batch(self.db, 'labels', [(8, original), (3, original)]).rows
        self.assertNotEqual(first.label_id, second.label_id)
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertEqual((first.source, second.source), (RowIdentity('labels', 8), RowIdentity('labels', 3)))
        for row in (first, second):
            frozen = freeze_revision(self.db, row.label_id, row.revision_id)
            self.assertEqual(frozen.original, original)
            self.assertEqual(get_import_row(self.db, row.source).original, original)
            self.assertEqual(read_delivery(self.db, 'revision', row.revision_id).lineage.source, row.source)
            self.assertEqual(get_head(self.db, row.label_id), row.revision_id)

    def test_invalid_utf8_rejects_batch(self):
        with self.assertRaisesRegex(ValueError, 'invalid UTF-8 at row 2'):
            import_batch(self.db, 'labels', [(1, b'Moss'), (2, b'\xff')])
        self.reopen()
        self.assert_empty_intake()
        with self.assertRaises(KeyError):
            get_import_row(self.db, RowIdentity('labels', 1))
        self.assertEqual(len(import_batch(self.db, 'labels', [(1, b'Moss'), (2, b'Moss')]).rows), 2)

    def test_duplicate_row(self):
        with self.assertRaisesRegex(ValueError, 'duplicate row'):
            import_batch(self.db, 'labels', [(2, b'Moss'), (2, b'Fern')])
        self.assert_empty_intake()

    def test_freeze_ownership(self):
        first, second = self.import_labels('Moss', 'Fern')
        with self.assertRaises(KeyError):
            freeze_revision(self.db, 999, first.revision_id)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            freeze_revision(self.db, first.label_id, second.revision_id)
        with self.assertRaises(KeyError):
            freeze_revision(self.db, first.label_id, 999)

    def test_empty_label_and_missing_field(self):
        with self.assertRaises(ValueError):
            import_batch(self.db, 'labels', [(1, b'Moss'), (2,)])
        self.assert_empty_intake()
        row, = import_batch(self.db, 'labels', [(1, b'')]).rows
        self.assertEqual(freeze_revision(self.db, row.label_id, row.revision_id).original, b'')
        sheet = self.issue(row)
        self.assertEqual((sheet.view, sheet.occurrences), ('', ()))

    def test_duplicate_batch_keeps_registered_bytes(self):
        row, = import_batch(self.db, 'labels', [(1, b'Moss')]).rows
        with self.assertRaisesRegex(ValueError, 'already registered'):
            import_batch(self.db, 'labels', [(1, b'Fern'), (2, b'Fern')])
        self.assertEqual(freeze_revision(self.db, row.label_id, row.revision_id).original, b'Moss')
        with self.assertRaises(KeyError):
            get_import_row(self.db, RowIdentity('labels', 2))
