from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecodedLabel:
    original: bytes
    text: str


def decode_label(original: bytes) -> DecodedLabel:
    if not isinstance(original, bytes):
        raise ValueError('each label must provide its original UTF-8 bytes')
    return DecodedLabel(original, original.decode('utf-8', errors='strict'))
