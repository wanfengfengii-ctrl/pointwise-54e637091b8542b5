import argparse
import json
import sqlite3
import sys
import unicodedata
from contextlib import closing
from dataclasses import asdict, is_dataclass
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog.historical_delivery import read_delivery
from catalog.manifests import initialize_manifests, publish_manifest
from correction.receipt_records import initialize_receipts
from correction.requests import AccentEdit, CorrectionRequest
from correction.settlement import apply_correction
from correction.source_rewrite import UnwritableCorrection
from intake.batches import import_batch
from intake.import_records import initialize_import_records
from issue.issued_sheets import get_issued_sheet, initialize_issued_sheets
from issue.offline_delivery import decode_proof_sheet, encode_proof_sheet
from issue.proof_sheet import issue_proof_sheet
from revision.freeze import freeze_revision
from revision.heads import initialize_heads
from revision.labels import initialize_labels
from revision.revisions import initialize_revisions


def initialize_workroom(db: sqlite3.Connection) -> None:
    if db.in_transaction:
        raise ValueError('workroom initialization requires an idle connection')
    db.execute('PRAGMA foreign_keys = ON')
    with db:
        db.execute('BEGIN IMMEDIATE')
        initialize_import_records(db)
        initialize_labels(db)
        initialize_revisions(db)
        initialize_heads(db)
        initialize_issued_sheets(db)
        initialize_receipts(db)
        initialize_manifests(db)


def open_workroom(path: str | PathLike[str]) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    try:
        initialize_workroom(db)
    except BaseException:
        db.close()
        raise
    return db


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding='utf-8'))


def _batch_input(data: object) -> tuple[str, list[tuple[int, bytes]]]:
    if not isinstance(data, dict) or not isinstance(data.get('labels'), list):
        raise ValueError('batch JSON requires batch_id and a labels array')
    records = []
    for row in data['labels']:
        if not isinstance(row, dict) or not isinstance(row.get('original_hex'), str):
            raise ValueError('label JSON requires row_number and original_hex')
        records.append((row['row_number'], bytes.fromhex(row['original_hex'])))
    return data['batch_id'], records


def _correction_input(data: object) -> CorrectionRequest:
    if not isinstance(data, dict) or not isinstance(data.get('edits'), list):
        raise ValueError('correction JSON requires sheet_id and an edits array')
    edits = []
    for edit in data['edits']:
        if not isinstance(edit, dict) or set(edit) != {'start', 'end', 'replacement'}:
            raise ValueError('edit JSON requires start, end and replacement')
        edits.append(AccentEdit(**edit))
    return CorrectionRequest(data['sheet_id'], tuple(edits))


def _json_default(value):
    if isinstance(value, bytes):
        return value.hex()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f'cannot encode {type(value).__name__}')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Specimen label workroom')
    parser.add_argument('--db', type=Path, help='SQLite workroom path')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo', help='run the sample workday in a temporary workroom')
    import_parser = commands.add_parser('import')
    import_parser.add_argument('input', type=Path)
    for name in ('freeze', 'issue'):
        command = commands.add_parser(name)
        command.add_argument('label_id', type=int)
        command.add_argument('revision_id', type=int)
    sheet = commands.add_parser('sheet')
    sheet.add_argument('sheet_id', type=int)
    apply = commands.add_parser('apply')
    apply.add_argument('input', type=Path)
    publish = commands.add_parser('publish')
    publish.add_argument('roster', type=Path)
    read = commands.add_parser('read')
    read.add_argument('kind', choices=('manifest', 'revision', 'receipt'))
    read.add_argument('number', type=int)
    return parser


def _dispatch(db: sqlite3.Connection, args: argparse.Namespace):
    if args.command == 'import':
        return import_batch(db, *_batch_input(_read_json(args.input)))
    if args.command == 'freeze':
        return freeze_revision(db, args.label_id, args.revision_id)
    if args.command == 'issue':
        original = freeze_revision(db, args.label_id, args.revision_id)
        return json.loads(encode_proof_sheet(issue_proof_sheet(db, original)))
    if args.command == 'sheet':
        return json.loads(encode_proof_sheet(get_issued_sheet(db, args.sheet_id)))
    if args.command == 'apply':
        return apply_correction(db, _correction_input(_read_json(args.input)))
    if args.command == 'publish':
        return publish_manifest(db, _read_json(args.roster))
    return read_delivery(db, args.kind, args.number)


def _expect(actual, expected, field: str) -> None:
    if actual != expected:
        raise AssertionError(f'{field}: expected {expected!r}, got {actual!r}')


def _run_demo() -> None:
    samples = Path(__file__).resolve().parents[1] / 'samples'
    fixture = _read_json(samples / 'corrections.json')
    expected_sheet = decode_proof_sheet(json.dumps(fixture['proof_sheet']))
    with TemporaryDirectory(prefix='specimen-workroom-') as directory:
        path = Path(directory) / 'catalog.sqlite3'
        with closing(open_workroom(path)) as db:
            batch = import_batch(db, *_batch_input(_read_json(samples / 'batch.json')))
            ordinary, _, precomposed, _, decomposed = batch.rows
            roster = [precomposed.label_id, decomposed.label_id, ordinary.label_id]
            before = publish_manifest(db, roster)
            original = freeze_revision(db, precomposed.label_id, precomposed.revision_id)
            sheet = issue_proof_sheet(db, original)
            offline = decode_proof_sheet(encode_proof_sheet(sheet))
            _expect(offline, expected_sheet, 'offline occurrence evidence')
            reject = _correction_input(fixture['reject_precomposed'])
            try:
                apply_correction(db, reject)
            except UnwritableCorrection:
                pass
            else:
                raise AssertionError('precomposed original must retain its unedited byte span')
            other_original = freeze_revision(db, decomposed.label_id, decomposed.revision_id)
            other_sheet = issue_proof_sheet(db, other_original)
            _expect(other_sheet.view, sheet.view, 'equivalent spelling views')
            other = apply_correction(db, CorrectionRequest(other_sheet.sheet_id, reject.edits))
            _expect(other.view, 'e\u0300\u0301', 'decomposed spelling target')
            request = _correction_input(fixture['change_acute'])
            corrected = apply_correction(db, request)
            corrected_ref = freeze_revision(db, corrected.revision.label_id, corrected.revision.revision_id)
            reissued = issue_proof_sheet(db, corrected_ref)
            after = publish_manifest(db, roster)

        with closing(open_workroom(path)) as db:
            old = read_delivery(db, 'manifest', before.manifest_id).entries[0]
            new = read_delivery(db, 'manifest', after.manifest_id).entries[0]
            receipt = read_delivery(db, 'receipt', corrected.receipt.receipt_id)
            expected = {'view': 'e\u0323\u0300', 'original_hex': '65cca3cc80'}
            actual = {'view': reissued.view, 'original_hex': corrected.revision.original.hex()}
            expected_delivery = {'old_hex': 'c3a9cca3', 'new_hex': '65cca3cc80', 'row': 30,
                                 'receipt_matches': True}
            actual_delivery = {
                'old_hex': old.source.revision.original.hex(),
                'new_hex': new.source.revision.original.hex(),
                'row': new.entry.source.row_number,
                'receipt_matches': (receipt.receipt == corrected.receipt
                                    and receipt.sheet == offline
                                    and receipt.parent == old.source.revision
                                    and receipt.successor == new.source),
            }
            _expect(actual, expected, 'reissued corrected view and bytes')
            _expect(actual_delivery, expected_delivery, 'reopened catalog and receipt')
            _expect(reissued.occurrences[1].product_index, 0, 'preserved independent dot product')
            evidence = reissued.occurrences[1]
            _expect(corrected.revision.original[evidence.byte_start:evidence.byte_end], b'\xcc\xa3',
                    'preserved independent dot bytes')
            print('POINTWISE_SCENARIO ' + json.dumps({
                'case_id': 'V4',
                'input': {'original_hex': original.original.hex(), 'edits': fixture['change_acute']['edits']},
                'expected': expected, 'actual': actual,
                'downstream_expected': expected_delivery, 'downstream_actual': actual_delivery,
                'code_paths': ['issue/occurrence_evidence.py', 'correction/view_edits.py',
                               'correction/source_rewrite.py', 'correction/settlement.py',
                               'catalog/manifests.py', 'catalog/historical_delivery.py'],
                'oracle': 'Hand-counted UTF-8 spans, codepoints and paper batch row 30. The supplied fixture gives the independently enumerated offline evidence.',
            }, ensure_ascii=True, sort_keys=True))
            print(json.dumps({'previous_manifest': before.manifest_id, 'new_manifest': after.manifest_id,
                              'receipt': receipt.receipt.receipt_id, 'python': sys.version.split()[0],
                              'unicode_data': unicodedata.unidata_version}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command != 'demo' and args.db is None:
        parser.error('--db is required for workroom operations')
    try:
        if args.command == 'demo':
            _run_demo()
        else:
            with closing(open_workroom(args.db)) as db:
                result = _dispatch(db, args)
            print(json.dumps(result, default=_json_default, sort_keys=True, ensure_ascii=True))
    except (AssertionError, KeyError, ValueError, OSError, sqlite3.Error) as error:
        print(f'{args.command}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
