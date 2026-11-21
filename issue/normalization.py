from collections.abc import Callable, Iterable
from typing import TypeVar
from unicodedata import combining, normalize


VIEW_FORM = 'NFD'
Occurrence = TypeVar('Occurrence')


def normalize_view(text: str) -> str:
    return normalize(VIEW_FORM, text)


def canonical_order(
    products: Iterable[Occurrence], character: Callable[[Occurrence], str]
) -> tuple[Occurrence, ...]:
    ordered = []
    pending = []
    for product in products:
        rank = combining(character(product))
        if rank == 0:
            ordered.extend(item for _, item in sorted(pending, key=lambda pair: pair[0]))
            pending.clear()
            ordered.append(product)
        else:
            pending.append((rank, product))
    ordered.extend(item for _, item in sorted(pending, key=lambda pair: pair[0]))
    return tuple(ordered)
