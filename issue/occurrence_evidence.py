from dataclasses import dataclass
from operator import itemgetter

from issue.normalization import canonical_order, normalize_view


@dataclass(frozen=True, slots=True)
class OccurrenceEvidence:
    position: int
    character: str
    byte_start: int
    byte_end: int
    product_index: int


def build_occurrence_evidence(original: bytes) -> tuple[OccurrenceEvidence, ...]:
    products = []
    start = 0
    for source_character in original.decode("utf-8"):
        end = start + len(source_character.encode("utf-8"))
        for index, character in enumerate(normalize_view(source_character)):
            products.append((character, start, end, index))
        start = end
    ordered = canonical_order(products, itemgetter(0))
    return tuple(
        OccurrenceEvidence(position, visible[0], *source[1:])
        for position, (visible, source) in enumerate(zip(ordered, products))
    )
