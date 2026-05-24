"""`freq()` — frequency tables and crosstabs. See FREQ_API.md for design.

This module currently contains the internal spec representation and argument
parser. The public `freq()` function arrives in a later ticket (F6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FreqSpec:
    """Parsed and validated `freq()` arguments. Internal — not part of the public API.

    `levels` and `label` are stored as Mappings; their immutability is by
    intent only (Python doesn't enforce dict immutability inside frozen
    dataclasses). Downstream code must not mutate them.
    """

    keys: tuple[str, ...]
    totals: bool = True
    observed: bool = True
    dropna: bool = False
    levels: Mapping[str, Sequence[Any]] | None = None
    label: Mapping[str, str] | None = None


def _parse_freq_args(
    *keys: str | Sequence[str],
    totals: bool = True,
    observed: bool = True,
    dropna: bool = False,
    levels: Mapping[str, Sequence[Any]] | None = None,
    label: Mapping[str, str] | None = None,
    weight: str | None = None,
    test: str | None = None,
) -> FreqSpec:
    """Normalize and validate `freq()` arguments into a `FreqSpec`.

    Raises on any structural problem (bad key forms, reserved kwargs, etc.).
    A successful return guarantees the spec is structurally valid; whether
    the named columns actually exist in a DataFrame is checked later, during
    aggregation.
    """
    if weight is not None:
        raise NotImplementedError(
            "weight= is reserved for weighted frequencies in v0.2 and is not "
            "implemented in v0.1."
        )
    if test is not None:
        raise NotImplementedError(
            "test= is reserved for statistical tests (chi-square, Fisher's, "
            "Cramér's V) in v0.2 and is not implemented in v0.1."
        )

    normalized = _normalize_keys(keys)

    if not 1 <= len(normalized) <= 2:
        raise ValueError(
            f"freq() supports one- or two-way tables only in v0.1; got "
            f"{len(normalized)} keys. Use tabulate() for higher-dimensional "
            f"aggregations."
        )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"freq() keys must be unique; got {list(normalized)}."
        )

    if levels is not None:
        extra = set(levels) - set(normalized)
        if extra:
            raise ValueError(
                f"freq() levels= contains keys not in grouping columns: "
                f"{sorted(extra)}. levels= keys must be a subset of "
                f"{sorted(normalized)}."
            )
        for k, v in levels.items():
            if isinstance(v, str) or not isinstance(v, (list, tuple)):
                raise TypeError(
                    f"freq() levels[{k!r}] must be a list or tuple; got "
                    f"{type(v).__name__}."
                )

    if label is not None:
        extra = set(label) - set(normalized)
        if extra:
            raise ValueError(
                f"freq() label= contains keys not in grouping columns: "
                f"{sorted(extra)}. label= keys must be a subset of "
                f"{sorted(normalized)}."
            )

    return FreqSpec(
        keys=normalized,
        totals=totals,
        observed=observed,
        dropna=dropna,
        levels=levels,
        label=label,
    )


def _normalize_keys(keys: tuple) -> tuple[str, ...]:
    """Turn `*keys` varargs into a flat tuple of column names.

    Accepts: single string, single list/tuple of strings, multiple strings.
    Rejects: empty, mixed positional+list, non-string items, empty strings.
    """
    if len(keys) == 0:
        raise ValueError("freq() requires at least one grouping column.")

    if len(keys) == 1:
        first = keys[0]
        if isinstance(first, str):
            if not first:
                raise ValueError("freq() keys must be non-empty strings.")
            return (first,)
        if isinstance(first, (list, tuple)):
            return _validate_key_sequence(first)
        raise TypeError(
            f"freq() key must be a string or list/tuple of strings; got "
            f"{type(first).__name__}."
        )

    if not all(isinstance(k, str) for k in keys):
        raise TypeError(
            "freq() doesn't accept mixed positional and list-of-keys forms. "
            "Pass either freq(df, 'a', 'b') or freq(df, ['a', 'b'])."
        )
    if any(not k for k in keys):
        raise ValueError("freq() keys must be non-empty strings.")
    return tuple(keys)


def _validate_key_sequence(seq: Sequence) -> tuple[str, ...]:
    items = tuple(seq)
    if not items:
        raise ValueError("freq() requires at least one grouping column.")
    if not all(isinstance(k, str) for k in items):
        raise TypeError(
            f"freq() keys in a list must all be strings; got types "
            f"{[type(k).__name__ for k in items]}."
        )
    if any(not k for k in items):
        raise ValueError("freq() keys must be non-empty strings.")
    return items
