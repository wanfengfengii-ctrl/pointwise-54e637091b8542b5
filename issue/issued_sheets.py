import sqlite3

from intake.row_identity import record_number
from issue.occurrence_evidence import OccurrenceEvidence
from issue.offline_delivery import ProofSheet, decode_proof_sheet, encode_proof_sheet
from revision.revisions import Revision


def initialize_issued_sheets(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS issued_sheets (
            sheet_id INTEGER PRIMARY KEY,
            label_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY (label_id, revision_id) REFERENCES revisions(label_id, revision_id)
        )
    ''')


def save_issued_sheet(
    db: sqlite3.Connection, revision: Revision, view: str,
    occurrences: tuple[OccurrenceEvidence, ...],
) -> ProofSheet:
    # The issuer holds the write transaction while allocating the number and storing the sheet.
    sheet_id = db.execute('SELECT COALESCE(MAX(sheet_id), 0) + 1 FROM issued_sheets').fetchone()[0]
    sheet = ProofSheet(sheet_id, revision.label_id, revision.revision_id, view, occurrences)
    db.execute(
        'INSERT INTO issued_sheets(sheet_id, label_id, revision_id, payload) VALUES (?, ?, ?, ?)',
        (sheet_id, revision.label_id, revision.revision_id, encode_proof_sheet(sheet)),
    )
    return sheet


def get_issued_sheet(db: sqlite3.Connection, sheet_id: int) -> ProofSheet:
    record_number(sheet_id, 'sheet_id')
    row = db.execute(
        'SELECT label_id, revision_id, payload FROM issued_sheets WHERE sheet_id = ?', (sheet_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown proof sheet: {sheet_id}')
    label_id, revision_id, payload = row
    sheet = decode_proof_sheet(payload)
    if (sheet.sheet_id, sheet.label_id, sheet.revision_id) != (sheet_id, label_id, revision_id):
        raise ValueError('proof payload does not match its archive reference')
    return sheet
