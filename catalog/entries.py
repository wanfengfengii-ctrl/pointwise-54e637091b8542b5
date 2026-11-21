import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from catalog.reconciliation import reconcile_revision
from intake.row_identity import RowIdentity
from revision.heads import get_head


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    position: int
    label_id: int
    revision_id: int
    source: RowIdentity
    receipt_id: int | None


def build_manifest_entries(
    db: sqlite3.Connection, roster: Sequence[int]
) -> tuple[ManifestEntry, ...]:
    if not isinstance(roster, Sequence) or isinstance(roster, (str, bytes, bytearray)):
        raise ValueError('an explicit ordered label roster is required')
    entries = []
    for position, label_id in enumerate(roster):
        revision_id = get_head(db, label_id)
        source = reconcile_revision(db, revision_id)
        receipt_id = None if source.receipt is None else source.receipt.receipt_id
        entries.append(ManifestEntry(position, label_id, revision_id, source.lineage.source, receipt_id))
    return tuple(entries)
