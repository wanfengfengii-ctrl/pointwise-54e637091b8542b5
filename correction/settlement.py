import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from correction.receipt_records import Receipt, record_receipt
from correction.requests import CorrectionRequest, validate_request
from correction.source_rewrite import plan_source_rewrite
from correction.view_edits import build_edit_target
from issue.issued_sheets import get_issued_sheet
from revision.heads import advance_head, get_head
from revision.revisions import Revision, append_revision, get_revision


class StaleSheet(ValueError):
    """The issued revision has been superseded."""


@dataclass(frozen=True, slots=True)
class SettlementResult:
    revision: Revision
    view: str
    receipt: Receipt


def apply_correction(
    db: sqlite3.Connection, request: CorrectionRequest, *,
    before_commit: Callable[[sqlite3.Connection], None] | None = None,
) -> SettlementResult:
    validate_request(request)
    with db:
        db.execute('BEGIN IMMEDIATE')
        sheet = get_issued_sheet(db, request.sheet_id)
        if get_head(db, sheet.label_id) != sheet.revision_id:
            raise StaleSheet(f'proof sheet {sheet.sheet_id} is stale')
        parent = get_revision(db, sheet.revision_id)
        target = build_edit_target(sheet.view, request)
        candidate = plan_source_rewrite(parent.original, sheet, target)
        successor = append_revision(db, parent, candidate.original)
        advance_head(db, parent, successor)
        receipt = record_receipt(db, sheet, successor)
        if before_commit is not None:
            before_commit(db)
    return SettlementResult(successor, candidate.view, receipt)
