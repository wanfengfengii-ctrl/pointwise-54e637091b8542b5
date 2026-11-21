import sqlite3
from dataclasses import dataclass

from intake.row_identity import record_number
from issue.offline_delivery import ProofSheet
from revision.revisions import Revision


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: int
    sheet_id: int
    parent_revision_id: int
    revision_id: int


def initialize_receipts(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id INTEGER PRIMARY KEY,
            sheet_id INTEGER NOT NULL UNIQUE REFERENCES issued_sheets(sheet_id),
            parent_revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
            revision_id INTEGER NOT NULL UNIQUE REFERENCES revisions(revision_id)
        )
    ''')


def record_receipt(db: sqlite3.Connection, sheet: ProofSheet, revision: Revision) -> Receipt:
    if (sheet.label_id, sheet.revision_id) != (revision.label_id, revision.parent_revision_id):
        raise ValueError('receipt must bind a sheet to its direct successor')
    cursor = db.execute(
        'INSERT INTO receipts(sheet_id, parent_revision_id, revision_id) VALUES (?, ?, ?)',
        (sheet.sheet_id, sheet.revision_id, revision.revision_id),
    )
    return Receipt(cursor.lastrowid, sheet.sheet_id, sheet.revision_id, revision.revision_id)


def get_receipt(db: sqlite3.Connection, receipt_id: int) -> Receipt:
    record_number(receipt_id, 'receipt_id')
    row = db.execute(
        'SELECT sheet_id, parent_revision_id, revision_id FROM receipts WHERE receipt_id = ?',
        (receipt_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown receipt: {receipt_id}')
    return Receipt(receipt_id, *row)


def get_receipt_for_revision(db: sqlite3.Connection, revision_id: int) -> Receipt | None:
    record_number(revision_id, 'revision_id')
    row = db.execute(
        'SELECT receipt_id, sheet_id, parent_revision_id, revision_id FROM receipts WHERE revision_id = ?',
        (revision_id,),
    ).fetchone()
    return None if row is None else Receipt(*row)
