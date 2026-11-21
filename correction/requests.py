from dataclasses import dataclass

from intake.row_identity import record_number


@dataclass(frozen=True, slots=True)
class AccentEdit:
    start: int
    end: int
    replacement: str


@dataclass(frozen=True, slots=True)
class CorrectionRequest:
    sheet_id: int
    edits: tuple[AccentEdit, ...]


def validate_request(request: CorrectionRequest) -> None:
    if not isinstance(request, CorrectionRequest):
        raise ValueError('a correction request is required')
    record_number(request.sheet_id, 'sheet_id')
    if not isinstance(request.edits, tuple) or not request.edits:
        raise ValueError('edits must be a nonempty tuple')
    for edit in request.edits:
        if not isinstance(edit, AccentEdit):
            raise ValueError('each edit must be an AccentEdit')
        if type(edit.start) is not int or type(edit.end) is not int or not isinstance(edit.replacement, str):
            raise ValueError('an edit requires integer offsets and replacement text')
