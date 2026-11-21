import sqlite3
from dataclasses import dataclass

from catalog.entries import ManifestEntry
from catalog.manifests import get_manifest
from catalog.reconciliation import ReceiptDelivery, RevisionSource, reconcile_receipt, reconcile_revision
from correction.receipt_records import get_receipt


@dataclass(frozen=True, slots=True)
class DeliveredEntry:
    entry: ManifestEntry
    source: RevisionSource


@dataclass(frozen=True, slots=True)
class CatalogDelivery:
    manifest_id: int
    entries: tuple[DeliveredEntry, ...]


def read_delivery(
    db: sqlite3.Connection, kind: str, number: int
) -> CatalogDelivery | RevisionSource | ReceiptDelivery:
    if kind == 'revision':
        return reconcile_revision(db, number)
    if kind == 'receipt':
        return reconcile_receipt(db, get_receipt(db, number))
    if kind != 'manifest':
        raise ValueError('delivery kind must be manifest, revision or receipt')

    manifest = get_manifest(db, number)
    delivered = []
    for entry in manifest.entries:
        source = reconcile_revision(db, entry.revision_id)
        receipt_id = None if source.receipt is None else source.receipt.receipt_id
        if (entry.label_id, entry.source, entry.receipt_id) != (
            source.revision.label_id, source.lineage.source, receipt_id
        ):
            raise ValueError('manifest entry does not match its fixed revision')
        delivered.append(DeliveredEntry(entry, source))
    return CatalogDelivery(manifest.manifest_id, tuple(delivered))
