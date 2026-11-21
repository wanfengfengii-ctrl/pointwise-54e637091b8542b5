import sqlite3

from issue.issued_sheets import save_issued_sheet
from issue.normalization import normalize_view
from issue.occurrence_evidence import build_occurrence_evidence
from issue.offline_delivery import ProofSheet
from revision.freeze import FrozenRevision, resolve_frozen_revision


def issue_proof_sheet(db: sqlite3.Connection, frozen: FrozenRevision) -> ProofSheet:
    revision = resolve_frozen_revision(db, frozen)
    view = normalize_view(revision.original.decode('utf-8'))
    occurrences = build_occurrence_evidence(revision.original)
    if ''.join(item.character for item in occurrences) != view:
        raise ValueError('issued occurrences do not project to the view')
    with db:
        db.execute('BEGIN IMMEDIATE')
        return save_issued_sheet(db, revision, view, occurrences)
