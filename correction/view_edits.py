from dataclasses import dataclass
from operator import attrgetter
from unicodedata import category, combining

from correction.requests import CorrectionRequest, validate_request
from issue.normalization import canonical_order, normalize_view


@dataclass(frozen=True, slots=True)
class TargetOccurrence:
    character: str
    old_position: int | None


@dataclass(frozen=True, slots=True)
class EditTarget:
    view: str
    edited_positions: frozenset[int]
    occurrences: tuple[TargetOccurrence, ...]


def _is_mark(character: str) -> bool:
    return category(character).startswith('M')


def build_edit_target(view: str, request: CorrectionRequest) -> EditTarget:
    validate_request(request)
    if (not view or _is_mark(view[0]) or combining(view[0]) != 0
            or any(not _is_mark(character) for character in view[1:])):
        raise ValueError('correction requires one base followed by combining marks')

    products = []
    edited = set()
    cursor = 0
    for edit in sorted(request.edits, key=attrgetter('start')):
        if not 1 <= edit.start < edit.end <= len(view) or edit.start < cursor:
            raise ValueError('edit spans must cover disjoint marks in the old view')
        replacement = normalize_view(edit.replacement)
        if any(not _is_mark(character) for character in replacement):
            raise ValueError('a replacement may only contribute combining marks')
        products.extend(TargetOccurrence(view[index], index) for index in range(cursor, edit.start))
        products.extend(TargetOccurrence(character, None) for character in replacement)
        edited.update(range(edit.start, edit.end))
        cursor = edit.end
    products.extend(TargetOccurrence(view[index], index) for index in range(cursor, len(view)))
    ordered = canonical_order(products, attrgetter('character'))
    return EditTarget(''.join(item.character for item in ordered), frozenset(edited), ordered)
