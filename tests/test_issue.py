import json

from issue.issued_sheets import get_issued_sheet
from issue.occurrence_evidence import OccurrenceEvidence
from issue.offline_delivery import decode_proof_sheet, encode_proof_sheet
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import FrozenRevision
from tests import WorkroomTestCase


class TestIssue(WorkroomTestCase):
    def test_decomposition_and_reorder(self):
        row, = self.import_labels('é\u0323')
        sheet = self.issue(row)
        self.assertEqual(sheet.view, 'e\u0323\u0301', 'V3: canonical view')
        self.assertEqual(sheet.occurrences, (
            OccurrenceEvidence(0, 'e', 0, 2, 0),
            OccurrenceEvidence(1, '\u0323', 2, 4, 0),
            OccurrenceEvidence(2, '\u0301', 0, 2, 1),
        ), 'V3: original occurrence identity')

    def test_equal_class_order(self):
        row, = self.import_labels('e\u0301\u0323\u0300\u0301')
        sheet = self.issue(row)
        self.assertEqual(sheet.view, 'e\u0323\u0301\u0300\u0301')
        self.assertEqual([item.byte_start for item in sheet.occurrences], [0, 3, 1, 5, 7])
        self.assertEqual([item.product_index for item in sheet.occurrences], [0, 0, 0, 0, 0])

    def test_offline_roundtrip(self):
        row, = self.import_labels('é\u0323')
        issued = self.issue(row)
        payload = encode_proof_sheet(issued)
        self.reopen()
        expected = get_issued_sheet(self.db, issued.sheet_id)
        self.assertEqual(decode_proof_sheet(payload), expected)
        self.assertEqual(encode_proof_sheet(expected), payload)
        data = json.loads(payload)
        data['occurrences'][2]['position'] = 1
        with self.assertRaises(ValueError):
            decode_proof_sheet(json.dumps(data))

    def test_invalid_reference(self):
        first, second = self.import_labels('Moss', 'Fern')
        with self.assertRaises(ValueError):
            issue_proof_sheet(self.db, FrozenRevision(first.label_id, first.revision_id, b'Fern'))
        with self.assertRaises(ValueError):
            issue_proof_sheet(self.db, FrozenRevision(first.label_id, second.revision_id, b'Fern'))
        with self.assertRaises(KeyError):
            issue_proof_sheet(self.db, FrozenRevision(first.label_id, 999, b'Moss'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM issued_sheets').fetchone()[0], 0)

    def test_reordering_stops_at_starters(self):
        row, = self.import_labels('\u0301\u0323éB\u0301\u0323')
        sheet = self.issue(row)
        self.assertEqual(sheet.view, '\u0323\u0301e\u0301B\u0323\u0301')
        self.assertEqual([item.byte_start for item in sheet.occurrences], [2, 0, 4, 4, 6, 9, 7])
