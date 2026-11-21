import sqlite3
from dataclasses import dataclass

from correction.receipt_records import Receipt, get_receipt_for_revision
from issue.issued_sheets import get_issued_sheet
from issue.offline_delivery import ProofSheet
from revision.revisions import Revision, get_revision
from revision.source_lineage import SourceLineage, resolve_source_lineage


@dataclass(frozen=True, slots=True)
class RevisionSource:
    revision: Revision
    lineage: SourceLineage
    receipt: Receipt | None


@dataclass(frozen=True, slots=True)
class ReceiptDelivery:
    receipt: Receipt
    sheet: ProofSheet
    parent: Revision
    successor: RevisionSource


def reconcile_revision(db: sqlite3.Connection, revision_id: int) -> RevisionSource:
    revision = get_revision(db, revision_id)
    lineage = resolve_source_lineage(db, revision)
    receipt = get_receipt_for_revision(db, revision_id)
    if revision.parent_revision_id is None:
        if receipt is not None:
            raise ValueError('initial revision has a correction receipt')
    elif receipt is None or receipt.parent_revision_id != lineage.parent_revision_id:
        raise ValueError('corrected revision is missing its settlement lineage')
    return RevisionSource(revision, lineage, receipt)


def reconcile_receipt(db: sqlite3.Connection, receipt: Receipt) -> ReceiptDelivery:
    sheet = get_issued_sheet(db, receipt.sheet_id)
    parent = get_revision(db, receipt.parent_revision_id)
    successor = reconcile_revision(db, receipt.revision_id)
    if ((sheet.label_id, sheet.revision_id) != (parent.label_id, parent.revision_id)
            or successor.revision.label_id != parent.label_id or successor.receipt != receipt):
        raise ValueError('receipt does not match its issued sheet and fixed revisions')
    return ReceiptDelivery(receipt, sheet, parent, successor)
