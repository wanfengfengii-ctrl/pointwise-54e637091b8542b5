import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog.workroom import open_workroom
from intake.batches import import_batch
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import freeze_revision


class WorkroomTestCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='specimen-tests-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'workroom.sqlite3'
        self.db = open_workroom(self.path)
        self.addCleanup(self.db.close)

    def reopen(self):
        self.db.close()
        self.db = open_workroom(self.path)
        self.addCleanup(self.db.close)

    def import_labels(self, *texts):
        return import_batch(self.db, 'field-batch', [
            (index * 10, text.encode('utf-8')) for index, text in enumerate(texts, 1)
        ]).rows

    def issue(self, row):
        return issue_proof_sheet(self.db, freeze_revision(self.db, row.label_id, row.revision_id))

    def settlement_counts(self):
        return self.db.execute('SELECT (SELECT COUNT(*) FROM revisions), (SELECT COUNT(*) FROM receipts)').fetchone()
