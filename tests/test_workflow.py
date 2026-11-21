import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from catalog.workroom import main
from tests import WorkroomTestCase


class TestWorkflow(WorkroomTestCase):
    def invoke(self, *args, expected_status=0):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(['--db', str(self.path), *map(str, args)])
        self.assertEqual(status, expected_status, stderr.getvalue())
        if status != 0:
            self.assertEqual(stdout.getvalue(), '')
            return stderr.getvalue()
        return json.loads(stdout.getvalue())

    def write_input(self, name, value):
        path = self.path.parent / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_offline_to_historical_catalog(self):
        samples = Path(__file__).resolve().parents[1] / 'samples'
        fixture = json.loads((samples / 'corrections.json').read_text(encoding='utf-8'))
        imported = self.invoke('import', samples / 'batch.json')
        first, second, precomposed, reordered, decomposed = imported['rows']
        self.assertNotEqual(first['label_id'], second['label_id'])
        self.assertEqual(self.invoke('freeze', reordered['label_id'], reordered['revision_id'])['original'], '65cc81cca3')
        selected = [decomposed['label_id'], precomposed['label_id']]
        roster = self.write_input('roster.json', selected)
        before = self.invoke('publish', roster)
        issued = self.invoke('issue', precomposed['label_id'], precomposed['revision_id'])
        self.assertEqual(issued, fixture['proof_sheet'])
        self.assertEqual(self.invoke('sheet', issued['sheet_id']), issued)
        bad = self.write_input('bad-correction.json', fixture['reject_precomposed'])
        self.assertIn('intact original bytes', self.invoke('apply', bad, expected_status=1))
        edits = self.write_input('edits.json', fixture['change_acute'])
        corrected = self.invoke('apply', edits)
        self.assertEqual(corrected['view'], 'e\u0323\u0300')
        self.assertEqual(corrected['revision']['original'], '65cca3cc80')
        self.assertIn('stale', self.invoke('apply', edits, expected_status=1))
        after = self.invoke('publish', roster)
        self.reopen()
        old = self.invoke('read', 'manifest', before['manifest_id'])
        new = self.invoke('read', 'manifest', after['manifest_id'])
        self.assertEqual([e['entry']['label_id'] for e in new['entries']], selected)
        self.assertEqual(old['entries'][0], new['entries'][0])
        old_label, new_label = old['entries'][1], new['entries'][1]
        self.assertEqual(old_label['source']['revision']['original'], 'c3a9cca3')
        self.assertEqual(new_label['source']['revision']['original'], '65cca3cc80')
        self.assertEqual(old_label['entry']['source'], {'batch_id': 'north-shore-01', 'row_number': 30})
        self.assertEqual(new_label['entry']['source'], old_label['entry']['source'])
        receipt = self.invoke('read', 'receipt', corrected['receipt']['receipt_id'])
        self.assertEqual(receipt['sheet'], issued)
        self.assertEqual(receipt['parent'], old_label['source']['revision'])
        self.assertEqual(receipt['successor'], new_label['source'])
        self.assertEqual(self.settlement_counts(), (6, 1))
