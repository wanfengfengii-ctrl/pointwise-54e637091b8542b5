from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RowIdentity:
    batch_id: str
    row_number: int


def record_number(value: int, name: str) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ValueError(f'{name} must be a positive SQLite integer')
    return value


def validate_batch_id(batch_id: str) -> str:
    if not isinstance(batch_id, str) or not batch_id:
        raise ValueError('batch_id must be a nonempty UTF-8 string')
    batch_id.encode('utf-8')
    return batch_id


def make_row_identity(batch_id: str, row_number: int) -> RowIdentity:
    return RowIdentity(validate_batch_id(batch_id), record_number(row_number, 'row_number'))


def validate_unique_rows(rows: Iterable[RowIdentity]) -> None:
    seen = set()
    for row in rows:
        if row in seen:
            raise ValueError(f'duplicate row {row.row_number} in batch {row.batch_id!r}')
        seen.add(row)
