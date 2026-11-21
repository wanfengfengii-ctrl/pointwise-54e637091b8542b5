import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog.historical_delivery import read_delivery
from catalog.manifests import publish_manifest
from catalog.workroom import open_workroom
from correction.requests import AccentEdit, CorrectionRequest
from correction.settlement import apply_correction
from correction.source_rewrite import UnwritableCorrection
from intake.batches import import_batch
from issue.issued_sheets import get_issued_sheet
from issue.offline_delivery import decode_proof_sheet, encode_proof_sheet
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import freeze_revision


CASES = (
    ("acute", "c3a9cca3", 2),
    ("dot_precomposed", "c3a9cca3", 1),
    ("dot_decomposed", "65cca3cc81", 1),
)
MARKER = "SPECIMEN_ACCENT_HANDOFF_MISMATCH"


def provenance(sheet):
    return tuple((item.byte_start, item.byte_end, item.product_index) for item in sheet.occurrences)


def observe(path):
    with closing(open_workroom(path)) as db:
        batch = import_batch(db, "accent-handoff", [
            (number, bytes.fromhex(raw)) for number, (_, raw, _) in enumerate(CASES, 30)
        ])
        roster = [row.label_id for row in batch.rows]
        before = publish_manifest(db, roster)
        attempts = []
        for row, (_, _, start) in zip(batch.rows, CASES):
            issued = issue_proof_sheet(db, freeze_revision(db, row.label_id, row.revision_id))
            sheet = decode_proof_sheet(encode_proof_sheet(get_issued_sheet(db, issued.sheet_id)))
            request = CorrectionRequest(sheet.sheet_id, (AccentEdit(start, start + 1, "\u0300"),))
            try:
                result = apply_correction(db, request)
            except UnwritableCorrection:
                attempts.append((sheet, None, None))
                continue
            revision = result.revision
            reissued = issue_proof_sheet(db, freeze_revision(db, revision.label_id, revision.revision_id))
            attempts.append((sheet, result, reissued))
        after = publish_manifest(db, roster)

    with closing(open_workroom(path)) as db:
        old = read_delivery(db, "manifest", before.manifest_id).entries
        new = read_delivery(db, "manifest", after.manifest_id).entries
        counts = db.execute(
            "SELECT (SELECT COUNT(*) FROM revisions), (SELECT COUNT(*) FROM receipts)"
        ).fetchone()
        observed = {
            "old_bytes": tuple(entry.source.revision.original.hex() for entry in old),
            "old_views_match": all(sheet.view == "e\u0323\u0301" for sheet, _, _ in attempts),
            "offline_acute_provenance": provenance(attempts[0][0]),
            "formal_counts": counts,
        }
        for (name, _, _), (sheet, result, reissued), old_entry, new_entry in zip(CASES, attempts, old, new):
            if result is None:
                observed[name] = {"decision": "unwritable", "entry_unchanged": old_entry == new_entry}
                continue
            receipt = read_delivery(db, "receipt", result.receipt.receipt_id)
            observed[name] = {
                "decision": "signed",
                "original_hex": new_entry.source.revision.original.hex(),
                "view": result.view,
                "reissued_view": reissued.view,
                "same_source_row": new_entry.entry.source == old_entry.entry.source,
                "receipt_matches": (receipt.sheet == sheet and receipt.parent == old_entry.source.revision
                                    and receipt.successor == new_entry.source and receipt.receipt == result.receipt),
            }
            if name == "acute":
                dot = reissued.occurrences[1]
                raw = new_entry.source.revision.original
                observed[name]["retained_dot"] = (dot.character, raw[dot.byte_start:dot.byte_end].hex(), dot.product_index)
        return observed


def main():
    expected = {
        "old_bytes": ("c3a9cca3", "c3a9cca3", "65cca3cc81"),
        "old_views_match": True,
        "offline_acute_provenance": ((0, 2, 0), (2, 4, 0), (0, 2, 1)),
        "formal_counts": (5, 2),
        "acute": {"decision": "signed", "original_hex": "65cca3cc80", "view": "e\u0323\u0300",
                  "reissued_view": "e\u0323\u0300", "same_source_row": True, "receipt_matches": True,
                  "retained_dot": ("\u0323", "cca3", 0)},
        "dot_precomposed": {"decision": "unwritable", "entry_unchanged": True},
        "dot_decomposed": {"decision": "signed", "original_hex": "65cc80cc81", "view": "e\u0300\u0301",
                           "reissued_view": "e\u0300\u0301", "same_source_row": True, "receipt_matches": True},
    }
    with TemporaryDirectory(prefix="accent-handoff-") as directory:
        actual = observe(Path(directory) / "workroom.sqlite3")
    print(json.dumps({"expected": expected, "actual": actual}, ensure_ascii=True, sort_keys=True))
    failures = [key for key, value in expected.items() if actual[key] != value]
    if failures:
        print(MARKER + " " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
