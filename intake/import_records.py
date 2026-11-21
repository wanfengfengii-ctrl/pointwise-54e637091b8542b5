import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from intake.row_identity import RowIdentity


@dataclass(frozen=True, slots=True)
class ImportRow:
    source: RowIdentity
    original: bytes


def initialize_import_records(db: sqlite3.Connection) -> None:
    db.execute('CREATE TABLE IF NOT EXISTS batches (batch_id TEXT PRIMARY KEY NOT NULL)')
    db.execute('''
        CREATE TABLE IF NOT EXISTS import_rows (
            batch_id TEXT NOT NULL REFERENCES batches(batch_id),
            row_number INTEGER NOT NULL CHECK (row_number > 0),
            original BLOB NOT NULL,
            PRIMARY KEY (batch_id, row_number)
        )
    ''')


def register_import_records(
    db: sqlite3.Connection, batch_id: str, rows: Sequence[ImportRow]
) -> None:
    if db.execute('SELECT 1 FROM batches WHERE batch_id = ?', (batch_id,)).fetchone():
        raise ValueError(f'batch already registered: {batch_id!r}')
    if any(row.source.batch_id != batch_id for row in rows):
        raise ValueError('row does not belong to the submitted batch')
    db.execute('INSERT INTO batches(batch_id) VALUES (?)', (batch_id,))
    db.executemany(
        'INSERT INTO import_rows(batch_id, row_number, original) VALUES (?, ?, ?)',
        ((batch_id, row.source.row_number, row.original) for row in rows),
    )


def get_import_row(db: sqlite3.Connection, source: RowIdentity) -> ImportRow:
    row = db.execute(
        'SELECT original FROM import_rows WHERE batch_id = ? AND row_number = ?',
        (source.batch_id, source.row_number),
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown import row: {source!r}')
    return ImportRow(source, row[0])
