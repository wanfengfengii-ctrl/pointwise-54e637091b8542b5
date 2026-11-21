import json
from dataclasses import asdict, dataclass

from intake.row_identity import record_number
from issue.occurrence_evidence import OccurrenceEvidence


@dataclass(frozen=True, slots=True)
class ProofSheet:
    sheet_id: int
    label_id: int
    revision_id: int
    view: str
    occurrences: tuple[OccurrenceEvidence, ...]


def encode_proof_sheet(sheet: ProofSheet) -> str:
    return json.dumps(asdict(sheet), sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def decode_proof_sheet(payload: str) -> ProofSheet:
    data = json.loads(payload)
    if not isinstance(data, dict) or set(data) != {'sheet_id', 'label_id', 'revision_id', 'view', 'occurrences'}:
        raise ValueError('invalid proof sheet fields')
    view, rows = data['view'], data['occurrences']
    if not isinstance(view, str) or not isinstance(rows, list) or len(view) != len(rows):
        raise ValueError('proof view and occurrence table must have the same length')
    view.encode('utf-8')
    occurrences = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            'position', 'character', 'byte_start', 'byte_end', 'product_index'
        }:
            raise ValueError('invalid occurrence fields')
        evidence = OccurrenceEvidence(**row)
        bounds = (evidence.position, evidence.byte_start, evidence.byte_end, evidence.product_index)
        if any(type(value) is not int or value < 0 for value in bounds):
            raise ValueError('occurrence positions and offsets must be nonnegative integers')
        if (evidence.position != position or evidence.byte_start >= evidence.byte_end
                or evidence.character != view[position]):
            raise ValueError('invalid proof occurrence')
        occurrences.append(evidence)
    return ProofSheet(
        record_number(data['sheet_id'], 'sheet_id'), record_number(data['label_id'], 'label_id'),
        record_number(data['revision_id'], 'revision_id'), view, tuple(occurrences),
    )
