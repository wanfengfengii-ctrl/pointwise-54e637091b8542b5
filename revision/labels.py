import sqlite3
from dataclasses import dataclass

from intake.row_identity import RowIdentity, record_number


@dataclass(frozen=True, slots=True)
class Label:
    label_id: int
    source: RowIdentity


def initialize_labels(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS labels (
            label_id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            UNIQUE (batch_id, row_number),
            FOREIGN KEY (batch_id, row_number) REFERENCES import_rows(batch_id, row_number)
        )
    ''')


def register_label(db: sqlite3.Connection, source: RowIdentity) -> Label:
    cursor = db.execute(
        'INSERT INTO labels(batch_id, row_number) VALUES (?, ?)',
        (source.batch_id, source.row_number),
    )
    return Label(cursor.lastrowid, source)


def get_label(db: sqlite3.Connection, label_id: int) -> Label:
    record_number(label_id, 'label_id')
    row = db.execute(
        'SELECT batch_id, row_number FROM labels WHERE label_id = ?', (label_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown label: {label_id}')
    return Label(label_id, RowIdentity(*row))
