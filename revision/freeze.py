import sqlite3
from dataclasses import dataclass

from revision.labels import get_label
from revision.revisions import Revision, get_revision


@dataclass(frozen=True, slots=True)
class FrozenRevision:
    label_id: int
    revision_id: int
    original: bytes


def freeze_revision(db: sqlite3.Connection, label_id: int, revision_id: int) -> FrozenRevision:
    get_label(db, label_id)
    revision = get_revision(db, revision_id)
    if revision.label_id != label_id:
        raise ValueError('revision does not belong to the requested label')
    return FrozenRevision(label_id, revision_id, revision.original)


def resolve_frozen_revision(db: sqlite3.Connection, frozen: FrozenRevision) -> Revision:
    if not isinstance(frozen, FrozenRevision) or not isinstance(frozen.original, bytes):
        raise ValueError('a frozen revision reference is required')
    revision = get_revision(db, frozen.revision_id)
    if revision.label_id != frozen.label_id or revision.original != frozen.original:
        raise ValueError('frozen reference does not match the stored original')
    return revision
