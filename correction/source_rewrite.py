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

    parts = []
    copied_spans = set()
    for item in target.occurrences:
        if item.old_position is None:
            parts.append(item.character.encode("utf-8"))
            continue
        evidence = sheet.occurrences[item.old_position]
        span = (evidence.byte_start, evidence.byte_end)
        if span in edited_spans:
            parts.append(item.character.encode("utf-8"))
        elif span not in copied_spans:
            parts.append(original[evidence.byte_start:evidence.byte_end])
            copied_spans.add(span)

    rewritten = b"".join(parts)
    return SourceRewrite(rewritten, normalize_view(rewritten.decode("utf-8")))
