"""`freq()` — frequency tables and crosstabs. See FREQ_API.md for design.

Currently exposes:
- `FreqSpec` (F1): parsed-and-validated arg representation.
- `_parse_freq_args()` (F2): user args → FreqSpec.
- `CountResult` + `aggregate_counts()` (F4a): raw count matrix from a
  narwhals-wrapped DataFrame.

The public `freq()` function arrives in F6.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import narwhals.stable.v1 as nw
import numpy as np

from legible.model import Category


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


# === F4a: raw count aggregation ============================================


@dataclass(frozen=True)
class CountResult:
    """Output of `aggregate_counts()` — raw integer counts per cell, with
    ordered category lists per grouping key.

    `counts` shape is `(R,)` for a one-way table and `(R, C)` for a two-way
    crosstab, where `R = len(row_categories)` and `C = len(col_categories)`.
    Marginals are NOT pre-stored; downstream code derives them as
    `counts.sum(axis=...)`. Total rows / columns are likewise NOT included
    here — they're added by F4b/F5 when assembling the final Table.

    A `Category(value=None, label="Missing")` may appear (always last) in
    a categories tuple if the corresponding source column had nulls and
    `dropna=False`.
    """

    row_categories: tuple[Category, ...]
    col_categories: tuple[Category, ...] | None
    counts: np.ndarray


def aggregate_counts(nw_df: nw.DataFrame, spec: FreqSpec) -> CountResult:
    """Compute raw counts per cell from a narwhals-wrapped DataFrame.

    Engine-agnostic: works on whatever native frame the user wrapped via
    `legible._engine.wrap()`. Honors `spec.dropna`, `spec.levels`, and
    `spec.observed` as defined in FREQ_API.md.

    Raises `ValueError` if `spec.observed=False` and no explicit
    `spec.levels[key]` was supplied (Categorical/Enum dtype detection is
    deferred to v0.2).
    """
    keys = list(spec.keys)

    if spec.dropna:
        nw_df = nw_df.drop_nulls(subset=keys)

    row_categories = _resolve_categories(nw_df, keys[0], spec)
    col_categories = (
        _resolve_categories(nw_df, keys[1], spec) if len(keys) == 2 else None
    )

    if col_categories is None:
        counts = _build_counts_1d(nw_df, keys, row_categories)
    else:
        counts = _build_counts_2d(nw_df, keys, row_categories, col_categories)

    return CountResult(
        row_categories=row_categories,
        col_categories=col_categories,
        counts=counts,
    )


def _resolve_categories(
    nw_df: nw.DataFrame, key: str, spec: FreqSpec,
) -> tuple[Category, ...]:
    """Build the ordered category list for one grouping key.

    Priority: `spec.levels[key]` if provided, else sorted observed unique
    values. A `Category(None, label="Missing")` is appended (last) when
    the column has nulls and `dropna=False`.
    """
    if spec.levels and key in spec.levels:
        return tuple(Category(v) for v in spec.levels[key])

    if not spec.observed:
        raise ValueError(
            f"observed=False on column {key!r} requires explicit "
            f"levels= to specify the domain; Categorical/Enum dtype "
            f"detection is planned for v0.2."
        )

    unique_values = nw_df[key].unique().to_list()

    non_nulls: list[Any] = []
    has_nulls = False
    for v in unique_values:
        if _is_null(v):
            has_nulls = True
        else:
            non_nulls.append(v)

    try:
        non_nulls.sort()
    except TypeError:
        # Mixed types in the column — fall back to observed order
        pass

    cats = [Category(v) for v in non_nulls]
    if has_nulls and not spec.dropna:
        cats.append(Category(None, label="Missing"))
    return tuple(cats)


def _build_counts_1d(
    nw_df: nw.DataFrame,
    keys: list[str],
    row_categories: tuple[Category, ...],
) -> np.ndarray:
    cat_to_idx = {cat.value: i for i, cat in enumerate(row_categories)}
    counts = np.zeros(len(row_categories), dtype=np.float64)
    grouped = nw_df.group_by(keys).agg(nw.len().alias("__n__"))
    for row in grouped.iter_rows(named=True):
        value = _normalize(row[keys[0]])
        idx = cat_to_idx.get(value)
        if idx is not None:
            counts[idx] = row["__n__"]
    return counts


def _build_counts_2d(
    nw_df: nw.DataFrame,
    keys: list[str],
    row_categories: tuple[Category, ...],
    col_categories: tuple[Category, ...],
) -> np.ndarray:
    row_idx = {cat.value: i for i, cat in enumerate(row_categories)}
    col_idx = {cat.value: i for i, cat in enumerate(col_categories)}
    counts = np.zeros(
        (len(row_categories), len(col_categories)), dtype=np.float64
    )
    grouped = nw_df.group_by(keys).agg(nw.len().alias("__n__"))
    for row in grouped.iter_rows(named=True):
        r = row_idx.get(_normalize(row[keys[0]]))
        c = col_idx.get(_normalize(row[keys[1]]))
        if r is not None and c is not None:
            counts[r, c] = row["__n__"]
    return counts


def _is_null(value: Any) -> bool:
    """Cross-engine null check: pandas exposes NaN, polars exposes None."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _normalize(value: Any) -> Any:
    """Normalize null forms (NaN, None) to None for consistent dict lookup."""
    return None if _is_null(value) else value
