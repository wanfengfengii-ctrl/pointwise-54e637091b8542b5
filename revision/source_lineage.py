import sqlite3
from dataclasses import dataclass

from intake.row_identity import RowIdentity
from revision.labels import get_label
from revision.revisions import Revision


@dataclass(frozen=True, slots=True)
class SourceLineage:
    source: RowIdentity
    parent_revision_id: int | None


def resolve_source_lineage(db: sqlite3.Connection, revision: Revision) -> SourceLineage:
    label = get_label(db, revision.label_id)
    return SourceLineage(label.source, revision.parent_revision_id)
