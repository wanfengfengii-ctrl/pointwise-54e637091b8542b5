import sqlite3
from dataclasses import dataclass

from intake.import_records import get_import_row
from intake.row_identity import record_number
from intake.utf8_labels import decode_label
from revision.labels import Label, get_label


@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: int
    label_id: int
    parent_revision_id: int | None
    original: bytes


def initialize_revisions(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS revisions (
            revision_id INTEGER PRIMARY KEY,
            label_id INTEGER NOT NULL REFERENCES labels(label_id),
            parent_revision_id INTEGER,
            corrected_bytes BLOB,
            UNIQUE (label_id, revision_id),
            FOREIGN KEY (label_id, parent_revision_id) REFERENCES revisions(label_id, revision_id),
            CHECK ((parent_revision_id IS NULL) = (corrected_bytes IS NULL))
        )
    ''')
    db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS one_root_per_label
        ON revisions(label_id) WHERE parent_revision_id IS NULL
    ''')


def create_initial_revision(db: sqlite3.Connection, label: Label) -> Revision:
    source = get_import_row(db, label.source)
    cursor = db.execute('INSERT INTO revisions(label_id) VALUES (?)', (label.label_id,))
    return Revision(cursor.lastrowid, label.label_id, None, source.original)


def append_revision(db: sqlite3.Connection, parent: Revision, original: bytes) -> Revision:
    decode_label(original)
    cursor = db.execute(
        'INSERT INTO revisions(label_id, parent_revision_id, corrected_bytes) VALUES (?, ?, ?)',
        (parent.label_id, parent.revision_id, original),
    )
    return Revision(cursor.lastrowid, parent.label_id, parent.revision_id, original)


def get_revision(db: sqlite3.Connection, revision_id: int) -> Revision:
    record_number(revision_id, 'revision_id')
    row = db.execute(
        'SELECT label_id, parent_revision_id, corrected_bytes FROM revisions WHERE revision_id = ?',
        (revision_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown revision: {revision_id}')
    label_id, parent_revision_id, original = row
    if parent_revision_id is None:
        label = get_label(db, label_id)
        original = get_import_row(db, label.source).original
    return Revision(revision_id, label_id, parent_revision_id, original)
