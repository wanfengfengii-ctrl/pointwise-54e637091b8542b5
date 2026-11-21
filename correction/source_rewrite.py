from dataclasses import dataclass

from correction.view_edits import EditTarget
from issue.normalization import normalize_view
from issue.offline_delivery import ProofSheet


class UnwritableCorrection(ValueError):
    """The target cannot be written while retaining its required source occurrences."""


@dataclass(frozen=True, slots=True)
class SourceRewrite:
    original: bytes
    view: str


def plan_source_rewrite(original: bytes, sheet: ProofSheet, target: EditTarget) -> SourceRewrite:
    edited_spans = set()
    for position in target.edited_positions:
        evidence = sheet.occurrences[position]
        edited_spans.add((evidence.byte_start, evidence.byte_end))

    all_spans = sorted({(item.byte_start, item.byte_end) for item in sheet.occurrences})
    retained_by_span: dict[tuple[int, int], set[tuple[str, int]]] = {span: set() for span in all_spans}
    span_of_target: list[tuple[int, int] | None] = []
    for item in target.occurrences:
        if item.old_position is None:
            span_of_target.append(None)
            continue
        evidence = sheet.occurrences[item.old_position]
        span = (evidence.byte_start, evidence.byte_end)
        retained_by_span[span].add((evidence.character, evidence.product_index))
        span_of_target.append(span)

    # Identity audit for unedited spans.  Such a span is copied whole, so the
    # products the target keeps from it must be exactly its full NFD
    # decomposition, matching character and intra-character product index.  A
    # precomposed span forced to surrender a product — an untouched é whose
    # acute must yield to another mark — fails here even when a replacement
    # mark of the same value would hide the loss in the projected view.
    for span in all_spans:
        if span in edited_spans:
            continue
        actual = {
            (character, index)
            for index, character in enumerate(normalize_view(original[span[0]:span[1]].decode("utf-8")))
        }
        if actual != retained_by_span[span]:
            raise UnwritableCorrection(
                'correction cannot keep intact original bytes while reproducing the target view'
            )

    # Contiguity audit for unedited spans.  A whole-copied span is one
    # indivisible byte chunk: all of its target positions must form one
    # contiguous run in the canonical target.  If a foreign product (a
    # replacement mark or another span's product) has to sit between two
    # products of the same unedited span — a new acute forced between the base
    # and the acute inside an untouched é, for example — the span cannot remain
    # whole and the correction is unwritable.
    for span in all_spans:
        if span in edited_spans:
            continue
        positions = [index for index, owner in enumerate(span_of_target) if owner == span]
        if positions and positions != list(range(min(positions), max(positions) + 1)):
            raise UnwritableCorrection(
                'correction cannot keep intact original bytes while reproducing the target view'
            )

    # Merge two streams.  Movable items — retained products of edited spans and
    # fresh replacement marks — keep canonical target order; each carries its
    # target index.  Fixed unedited chunks keep their original source order, and
    # each is labelled with the canonical index of its first retained product.
    # A movable item is emitted before the first fixed chunk whose label exceeds
    # its index, otherwise after all chunks.  Untouched characters therefore
    # keep exact bytes and relative source order, while an edit may relocate an
    # accent across them and canonical reordering restores the target view.
    movable: list[tuple[int, bytes]] = []
    for index, item in enumerate(target.occurrences):
        if item.old_position is None:
            movable.append((index, item.character.encode("utf-8")))
            continue
        evidence = sheet.occurrences[item.old_position]
        span = (evidence.byte_start, evidence.byte_end)
        if span in edited_spans:
            movable.append((index, evidence.character.encode("utf-8")))

    fixed_anchors: list[tuple[int, bytes]] = []
    for span in all_spans:
        if span in edited_spans or not retained_by_span.get(span):
            continue
        first_position = min(
            index for index, owner in enumerate(span_of_target) if owner == span
        )
        fixed_anchors.append((first_position, original[span[0]:span[1]]))

    parts: list[bytes] = []
    cursor = 0
    for first_position, chunk in fixed_anchors:
        while cursor < len(movable) and movable[cursor][0] < first_position:
            parts.append(movable[cursor][1])
            cursor += 1
        parts.append(chunk)
    while cursor < len(movable):
        parts.append(movable[cursor][1])
        cursor += 1

    rewritten = b"".join(parts)
    view = normalize_view(rewritten.decode("utf-8"))
    if view != target.view:
        raise UnwritableCorrection(
            'correction cannot keep intact original bytes while reproducing the target view'
        )
    return SourceRewrite(rewritten, view)
