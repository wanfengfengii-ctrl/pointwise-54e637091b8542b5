from dataclasses import dataclass
from operator import attrgetter

from issue.normalization import canonical_order, normalize_view


@dataclass(frozen=True, slots=True)
class OccurrenceEvidence:
    position: int
    character: str
    byte_start: int
    byte_end: int
    product_index: int


def build_occurrence_evidence(original: bytes) -> tuple[OccurrenceEvidence, ...]:
    # Each product carries its own source span and intra-character index.  The
    # whole record must travel through the canonical reordering together;
    # pairing the reordered view with the unordered products swaps provenance
    # whenever two marks change relative order.
    products = []
    start = 0
    for source_character in original.decode("utf-8"):
        end = start + len(source_character.encode("utf-8"))
        for index, character in enumerate(normalize_view(source_character)):
            products.append(OccurrenceEvidence(0, character, start, end, index))
        start = end
    ordered = canonical_order(products, attrgetter("character"))
    return tuple(
        OccurrenceEvidence(position, item.character, item.byte_start, item.byte_end, item.product_index)
        for position, item in enumerate(ordered)
    )
