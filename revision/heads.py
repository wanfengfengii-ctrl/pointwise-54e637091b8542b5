import sqlite3

from intake.row_identity import record_number
from revision.revisions import Revision


def initialize_heads(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS heads (
            label_id INTEGER PRIMARY KEY,
            revision_id INTEGER NOT NULL,
            FOREIGN KEY (label_id, revision_id) REFERENCES revisions(label_id, revision_id)
        )
    ''')


def register_head(db: sqlite3.Connection, initial: Revision) -> None:
    if initial.parent_revision_id is not None:
        raise ValueError('initial head must refer to a root revision')
    db.execute(
        'INSERT INTO heads(label_id, revision_id) VALUES (?, ?)',
        (initial.label_id, initial.revision_id),
    )


def get_head(db: sqlite3.Connection, label_id: int) -> int:
    record_number(label_id, 'label_id')
    row = db.execute('SELECT revision_id FROM heads WHERE label_id = ?', (label_id,)).fetchone()
    if row is None:
        raise KeyError(f'unknown current label: {label_id}')
    return row[0]


def advance_head(db: sqlite3.Connection, expected: Revision, successor: Revision) -> None:
    cursor = db.execute('''
        UPDATE heads SET revision_id = ?
        WHERE label_id = ? AND revision_id = ? AND EXISTS (
            SELECT 1 FROM revisions
            WHERE revision_id = ? AND label_id = ? AND parent_revision_id = ?
        )
    ''', (successor.revision_id, expected.label_id, expected.revision_id,
          successor.revision_id, expected.label_id, expected.revision_id))
    if cursor.rowcount != 1:
        raise ValueError('expected current parent could not be advanced')
