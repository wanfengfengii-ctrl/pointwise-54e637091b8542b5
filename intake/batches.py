import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from intake.import_records import ImportRow, register_import_records
from intake.row_identity import RowIdentity, make_row_identity, validate_batch_id, validate_unique_rows
from intake.utf8_labels import decode_label
from revision.heads import register_head
from revision.labels import register_label
from revision.revisions import create_initial_revision


@dataclass(frozen=True, slots=True)
class ImportedLabel:
    source: RowIdentity
    label_id: int
    revision_id: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch_id: str
    rows: tuple[ImportedLabel, ...]


def import_batch(
    db: sqlite3.Connection, batch_id: str, records: Sequence[tuple[int, bytes]]
) -> ImportResult:
    validate_batch_id(batch_id)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise ValueError('records must be an ordered sequence of row numbers and bytes')
    rows = []
    for record in records:
        if not isinstance(record, (list, tuple)) or len(record) != 2:
            raise ValueError('each record must contain a row number and original bytes')
        row_number, original = record
        source = make_row_identity(batch_id, row_number)
        try:
            decoded = decode_label(original)
        except UnicodeDecodeError as error:
            raise ValueError(f'invalid UTF-8 at row {row_number}') from error
        rows.append(ImportRow(source, decoded.original))
    validate_unique_rows(row.source for row in rows)

    imported = []
    with db:
        db.execute('BEGIN IMMEDIATE')
        register_import_records(db, batch_id, rows)
        for row in rows:
            label = register_label(db, row.source)
            revision = create_initial_revision(db, label)
            register_head(db, revision)
            imported.append(ImportedLabel(row.source, label.label_id, revision.revision_id))
    return ImportResult(batch_id, tuple(imported))
