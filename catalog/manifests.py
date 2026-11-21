import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from catalog.entries import ManifestEntry, build_manifest_entries
from intake.row_identity import RowIdentity, record_number


@dataclass(frozen=True, slots=True)
class Manifest:
    manifest_id: int
    entries: tuple[ManifestEntry, ...]


def initialize_manifests(db: sqlite3.Connection) -> None:
    db.execute('CREATE TABLE IF NOT EXISTS manifests (manifest_id INTEGER PRIMARY KEY)')
    db.execute('''
        CREATE TABLE IF NOT EXISTS manifest_entries (
            manifest_id INTEGER NOT NULL REFERENCES manifests(manifest_id),
            position INTEGER NOT NULL CHECK (position >= 0),
            label_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            receipt_id INTEGER REFERENCES receipts(receipt_id),
            PRIMARY KEY (manifest_id, position),
            FOREIGN KEY (label_id, revision_id) REFERENCES revisions(label_id, revision_id),
            FOREIGN KEY (batch_id, row_number) REFERENCES import_rows(batch_id, row_number)
        )
    ''')


def publish_manifest(db: sqlite3.Connection, roster: Sequence[int]) -> Manifest:
    with db:
        db.execute('BEGIN IMMEDIATE')
        entries = build_manifest_entries(db, roster)
        manifest_id = db.execute('INSERT INTO manifests DEFAULT VALUES').lastrowid
        db.executemany('''
            INSERT INTO manifest_entries(
                manifest_id, position, label_id, revision_id, batch_id, row_number, receipt_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ((manifest_id, entry.position, entry.label_id, entry.revision_id,
               entry.source.batch_id, entry.source.row_number, entry.receipt_id) for entry in entries))
    return Manifest(manifest_id, entries)


def get_manifest(db: sqlite3.Connection, manifest_id: int) -> Manifest:
    record_number(manifest_id, 'manifest_id')
    if db.execute('SELECT 1 FROM manifests WHERE manifest_id = ?', (manifest_id,)).fetchone() is None:
        raise KeyError(f'unknown manifest: {manifest_id}')
    rows = db.execute('''
        SELECT position, label_id, revision_id, batch_id, row_number, receipt_id
        FROM manifest_entries WHERE manifest_id = ? ORDER BY position
    ''', (manifest_id,))
    return Manifest(manifest_id, tuple(
        ManifestEntry(position, label_id, revision_id, RowIdentity(batch_id, row_number), receipt_id)
        for position, label_id, revision_id, batch_id, row_number, receipt_id in rows
    ))
