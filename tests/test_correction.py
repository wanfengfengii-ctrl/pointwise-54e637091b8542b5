import sqlite3

from catalog.historical_delivery import read_delivery
from catalog.manifests import publish_manifest
from correction.requests import AccentEdit, CorrectionRequest
from correction.settlement import StaleSheet, apply_correction
from correction.source_rewrite import UnwritableCorrection
from issue.issued_sheets import get_issued_sheet
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import freeze_revision
from revision.heads import get_head
from tests import WorkroomTestCase


def _reject_commit(db):
    db.execute('PRAGMA defer_foreign_keys = ON')
    db.execute('INSERT INTO heads(label_id, revision_id) VALUES (-1, -1)')


class TestCorrection(WorkroomTestCase):
    def reissue(self, result):
        revision = result.revision
        return issue_proof_sheet(self.db, freeze_revision(self.db, revision.label_id, revision.revision_id))

    def test_change_one_product(self):
        row, = self.import_labels('é\u0323')
        sheet = self.issue(row)
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(2, 3, '\u0300'),)))
        self.assertEqual(result.view, 'e\u0323\u0300', 'V4: target view')
        self.assertEqual(result.revision.original, b'e\xcc\xa3\xcc\x80', 'V4: original bytes')
        reissued = self.reissue(result)
        self.assertEqual(reissued.view, result.view)
        dot = reissued.occurrences[1]
        self.assertEqual((dot.character, dot.byte_start, dot.byte_end, dot.product_index), ('\u0323', 1, 3, 0))
        parent = read_delivery(self.db, 'revision', row.revision_id)
        delivered = read_delivery(self.db, 'receipt', result.receipt.receipt_id)
        self.assertEqual(parent.revision.original, b'\xc3\xa9\xcc\xa3')
        self.assertEqual((delivered.sheet, delivered.parent), (sheet, parent.revision))
        self.assertEqual(delivered.successor.revision, result.revision)

    def test_same_view_different_admissibility(self):
        precomposed, decomposed = self.import_labels('é\u0323', 'e\u0323\u0301')
        first, second = self.issue(precomposed), self.issue(decomposed)
        self.assertEqual(first.view, second.view)
        changes = (AccentEdit(1, 2, '\u0300'),)
        with self.assertRaises(UnwritableCorrection, msg='V5: untouched é cannot split'):
            apply_correction(self.db, CorrectionRequest(first.sheet_id, changes))
        self.assertEqual(self.settlement_counts(), (2, 0))
        self.assertEqual(get_head(self.db, precomposed.label_id), precomposed.revision_id)
        result = apply_correction(self.db, CorrectionRequest(second.sheet_id, changes))
        self.assertEqual(self.reissue(result).view, 'e\u0300\u0301')
        self.assertEqual(result.revision.original, b'e\xcc\x80\xcc\x81')
        self.assertEqual(self.settlement_counts(), (3, 1))

    def test_requires_relocation(self):
        row, = self.import_labels('e\u0301\u0323')
        sheet = self.issue(row)
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(1, 2, '\u0300'),)))
        self.assertEqual(result.revision.original, b'e\xcc\x80\xcc\x81', 'V5: move grave before retained acute')
        self.assertEqual(self.reissue(result).view, 'e\u0300\u0301')

    def test_same_old_view(self):
        row, = self.import_labels('e\u0323\u0301\u0302')
        sheet = self.issue(row)
        edits = (AccentEdit(1, 2, ''), AccentEdit(2, 3, '\u0300'))
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, edits))
        self.assertEqual(self.reissue(result).view, 'e\u0300\u0302')
        self.assertEqual(result.revision.original, b'e\xcc\x80\xcc\x82')

    def test_invalid_spans(self):
        row, plain, multi = self.import_labels('e\u0323\u0301', '', 'Ab\u0301')
        sheet = self.issue(row)
        for edits in (
            (), (AccentEdit(0, 1, ''),), (AccentEdit(1, 1, ''),), (AccentEdit(-1, 2, ''),),
            (AccentEdit(2, 4, ''),), (AccentEdit(1, 3, ''), AccentEdit(2, 3, '')),
            (AccentEdit(True, 2, ''),), (AccentEdit(1, 2, 'A'),),
        ):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                apply_correction(self.db, CorrectionRequest(sheet.sheet_id, edits))
        for target in (plain, multi):
            invalid = self.issue(target)
            with self.assertRaisesRegex(ValueError, 'one base'):
                apply_correction(self.db, CorrectionRequest(invalid.sheet_id, (AccentEdit(1, 2, ''),)))
        self.assertEqual(self.settlement_counts(), (3, 0))
        self.assertEqual(get_head(self.db, row.label_id), row.revision_id)

    def test_equal_output_marks_still_have_distinct_identities(self):
        row, = self.import_labels('é\u0323')
        sheet = self.issue(row)
        # The new acute would have to precede the acute already encoded inside é.
        with self.assertRaises(UnwritableCorrection):
            apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(1, 2, '\u0301'),)))
        self.assertEqual(self.settlement_counts(), (1, 0))

    def test_replacement_decomposes_and_retains_other_products(self):
        row, = self.import_labels('ấ\u0323')
        sheet = self.issue(row)
        self.assertEqual(sheet.view, 'a\u0323\u0302\u0301')
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(3, 4, '\u0344'),)))
        self.assertEqual(self.reissue(result).view, 'a\u0323\u0302\u0308\u0301')
        self.assertEqual(result.revision.original, b'a\xcc\xa3\xcc\x82\xcc\x88\xcc\x81')

    def test_delete_class_zero_mark_merges_reordering_runs(self):
        row, = self.import_labels('e\u0301\u20dd\u0323')
        sheet = self.issue(row)
        self.assertEqual(sheet.view, 'e\u0301\u20dd\u0323')
        result = apply_correction(self.db, CorrectionRequest(sheet.sheet_id, (AccentEdit(2, 3, ''),)))
        self.assertEqual(result.revision.original, b'e\xcc\x81\xcc\xa3')
        self.assertEqual(self.reissue(result).view, 'e\u0323\u0301')

    def test_stale_sheet(self):
        row, = self.import_labels('e\u0301')
        first, second = self.issue(row), self.issue(row)
        edits = (AccentEdit(1, 2, '\u0300'),)
        result = apply_correction(self.db, CorrectionRequest(first.sheet_id, edits))
        with self.assertRaises(StaleSheet):
            apply_correction(self.db, CorrectionRequest(second.sheet_id, edits))
        self.assertEqual(get_head(self.db, row.label_id), result.revision.revision_id)
        self.assertEqual(get_issued_sheet(self.db, second.sheet_id), second)
        self.assertEqual(self.settlement_counts(), (2, 1))

    def failed_correction(self):
        row, = self.import_labels('e\u0323\u0301\u0302')
        earlier = publish_manifest(self.db, [row.label_id])
        sheet = self.issue(row)
        request = CorrectionRequest(sheet.sheet_id, (AccentEdit(1, 2, ''), AccentEdit(2, 3, '\u0300')))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            apply_correction(self.db, request, before_commit=_reject_commit)
        self.reopen()
        return row, earlier, request

    def test_commit_failure(self):
        row, earlier, _ = self.failed_correction()
        original = b'e\xcc\xa3\xcc\x81\xcc\x82'
        self.assertEqual(self.settlement_counts(), (1, 0))
        self.assertEqual(get_head(self.db, row.label_id), row.revision_id)
        delivery = read_delivery(self.db, 'manifest', earlier.manifest_id)
        self.assertEqual(delivery.entries[0].source.revision.original, original)
        self.assertIsNone(delivery.entries[0].source.receipt)
        with self.assertRaises(KeyError):
            read_delivery(self.db, 'revision', row.revision_id + 1)
        with self.assertRaises(KeyError):
            read_delivery(self.db, 'receipt', 1)

    def test_retry_after_rollback(self):
        row, earlier, request = self.failed_correction()
        result = apply_correction(self.db, request)
        self.assertEqual(self.reissue(result).view, 'e\u0300\u0302')
        self.assertEqual(self.settlement_counts(), (2, 1))
        self.assertEqual(get_head(self.db, row.label_id), result.revision.revision_id)
        self.assertEqual(read_delivery(self.db, 'manifest', earlier.manifest_id).entries[0].entry.revision_id,
                         row.revision_id)
        self.assertEqual(read_delivery(self.db, 'receipt', result.receipt.receipt_id).receipt, result.receipt)
