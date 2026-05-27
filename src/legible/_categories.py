"""Shared category-resolution helpers used by `freq()` and `tabulate()`.

The same logic — resolve a grouping column's ordered category list from
a wrapped DataFrame, honoring observed/levels/dropna policies — is
needed by both `freq.aggregate_counts()` and `tabulate.aggregate_data_cells()`.
Extracted here so the implementations stay in sync.

Internal — not part of the public API.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import narwhals.stable.v1 as nw

from legible.model import Category


# Lazy pandas reference for pd.NA / pd.NaT singleton checks. Pandas is a
# dev dep, not a runtime dep, but if a caller is using a pandas-flavored
# DataFrame they have pandas installed by definition.
try:
    import pandas as _pd
except ImportError:
    _pd = None


def is_null(value: Any) -> bool:
    """Cross-engine null check.

    Recognizes every null form a narwhals-wrapped iter_rows can surface:

    - Python ``None`` (polars exposes nulls this way at the boundary)
    - float NaN (pandas exposes object-column nulls this way; also numpy.nan)
    - pandas ``pd.NA`` singleton (nullable dtypes: Int64, Float64, string,
      BooleanDtype, etc.)
    - pandas ``pd.NaT`` singleton (datetime / timedelta nulls)

    Identity checks against the pandas singletons avoid the
    array-broadcasting hazard of ``pd.isna()`` on non-scalar inputs.
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if _pd is not None and (value is _pd.NA or value is _pd.NaT):
        return True
    return False


def normalize(value: Any) -> Any:
    """Normalize all null forms (NaN, None) to None for consistent dict lookup."""
    return None if is_null(value) else value


def column_has_nulls(nw_df: nw.DataFrame, key: str) -> bool:
    """Engine-agnostic null check across the entire column."""
    return bool(nw_df[key].is_null().any())


def resolve_categories(
    nw_df: nw.DataFrame,
    key: str,
    *,
    observed: bool,
    dropna: bool,
    levels: Mapping[str, Sequence[Any]] | None,
) -> tuple[Category, ...]:
    """Build the ordered category list for one grouping key.

    Priority: ``levels[key]`` if provided (user-supplied exact order),
    else sorted observed unique values. In both cases, a
    ``Category(None, label="Missing")`` is appended (last) when the
    column has nulls and ``dropna=False`` — unless the user has already
    included ``None`` in their ``levels=`` list, in which case their
    ``Category(None)`` is used as-is (no label override).

    Raises ``ValueError`` when ``observed=False`` and no ``levels[key]``
    is provided (Categorical/Enum dtype detection is planned for v0.2).
    """
    if levels and key in levels:
        levels_seq = list(levels[key])
        cats = [Category(v) for v in levels_seq]
        if (
            not dropna
            and None not in levels_seq
            and column_has_nulls(nw_df, key)
        ):
            cats.append(Category(None, label="Missing"))
        return tuple(cats)

    if not observed:
        raise ValueError(
            f"observed=False on column {key!r} requires explicit "
            f"levels= to specify the domain; Categorical/Enum dtype "
            f"detection is planned for v0.2."
        )

    unique_values = nw_df[key].unique().to_list()

    non_nulls: list[Any] = []
    has_nulls = False
    for v in unique_values:
        if is_null(v):
            has_nulls = True
        else:
            non_nulls.append(v)

    try:
        non_nulls.sort()
    except TypeError:
        # Mixed types in the column — fall back to observed order
        pass

    cats = [Category(v) for v in non_nulls]
    if has_nulls and not dropna:
        cats.append(Category(None, label="Missing"))
    return tuple(cats)
