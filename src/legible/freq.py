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

from legible.model import (
    Axis,
    Category,
    Dimension,
    MissingReason,
    Node,
    TotalMarker,
    ValueKind,
)


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


# === F4b: percentage derivation + MissingReason ============================


_ONE_WAY_STATS = (
    Category("N"),
    Category("Pct"),
    Category("CumN"),
    Category("CumPct", label="Cum%"),
)
_ONE_WAY_VALUE_KINDS: tuple[ValueKind, ...] = (
    "count", "percent", "count", "percent",
)
_ONE_WAY_FORMATS = ("{:.0f}", "{:.1f}%", "{:.0f}", "{:.1f}%")

_TWO_WAY_STATS = (
    Category("N"),
    Category("RowPct", label="Row%"),
    Category("ColPct", label="Col%"),
    Category("TotPct", label="Tot%"),
)
_TWO_WAY_VALUE_KINDS: tuple[ValueKind, ...] = (
    "count", "percent", "percent", "percent",
)
_TWO_WAY_FORMATS = ("{:.0f}", "{:.1f}%", "{:.1f}%", "{:.1f}%")


@dataclass(frozen=True)
class PercentResult:
    """Output of `derive_percentages()` — the final body matrix and
    `MissingReason` codes for the freq() Table, plus the metadata F5/F6
    need to build the Axis structure and populate Table attributes.

    `body.shape` is `(R + has_row_total, n_stats)` for one-way or
    `(R + has_row_total, (C + has_col_total) * n_stats)` for two-way,
    where Total rows/cols sit AFTER all data rows/cols.

    `MissingReason.NOT_APPLICABLE` is set on percentage cells whose
    denominator is zero (divide-by-zero protection). N cells are always
    PRESENT — a count of zero is meaningful, not missing.
    """

    row_categories: tuple[Category, ...]
    col_categories: tuple[Category, ...] | None
    stat_categories: tuple[Category, ...]
    stat_value_kinds: tuple[ValueKind, ...]
    stat_formats: tuple[str, ...]
    has_row_total: bool
    has_col_total: bool
    body: np.ndarray
    missing: np.ndarray


def derive_percentages(counts: CountResult, spec: FreqSpec) -> PercentResult:
    """Compute the final body matrix and MissingReason codes from raw counts.

    Honors `spec.totals` for marginal rows/columns. The Total row/col is
    suppressed when there's no data to total over (R == 0 or, for two-way,
    R == 0 or C == 0).
    """
    if counts.col_categories is None:
        return _derive_one_way(counts, spec)
    return _derive_two_way(counts, spec)


def _derive_one_way(counts: CountResult, spec: FreqSpec) -> PercentResult:
    raw = counts.counts
    n_categories = len(raw)
    n_stats = len(_ONE_WAY_STATS)
    grand_total = float(raw.sum())

    has_row_total = spec.totals and n_categories > 0
    n_rows = n_categories + (1 if has_row_total else 0)

    body = np.zeros((n_rows, n_stats), dtype=np.float64)
    missing = np.zeros((n_rows, n_stats), dtype=np.uint8)

    running = 0.0
    for i in range(n_categories):
        n = float(raw[i])
        running += n
        body[i, 0] = n                 # N
        body[i, 2] = running           # CumN
        _set_percent(body, missing, i, 1, n,       grand_total)
        _set_percent(body, missing, i, 3, running, grand_total)

    if has_row_total:
        t = n_categories
        body[t, 0] = grand_total       # N
        body[t, 2] = grand_total       # CumN (= grand)
        _set_percent(body, missing, t, 1, grand_total, grand_total)
        _set_percent(body, missing, t, 3, grand_total, grand_total)

    return PercentResult(
        row_categories=counts.row_categories,
        col_categories=None,
        stat_categories=_ONE_WAY_STATS,
        stat_value_kinds=_ONE_WAY_VALUE_KINDS,
        stat_formats=_ONE_WAY_FORMATS,
        has_row_total=has_row_total,
        has_col_total=False,
        body=body,
        missing=missing,
    )


def _derive_two_way(counts: CountResult, spec: FreqSpec) -> PercentResult:
    raw = counts.counts
    n_rows_data, n_cols_data = raw.shape
    n_stats = len(_TWO_WAY_STATS)

    nonempty = n_rows_data > 0 and n_cols_data > 0
    has_row_total = spec.totals and nonempty
    has_col_total = spec.totals and nonempty

    n_row_groups = n_rows_data + (1 if has_row_total else 0)
    n_col_groups = n_cols_data + (1 if has_col_total else 0)

    body = np.zeros((n_row_groups, n_col_groups * n_stats), dtype=np.float64)
    missing = np.zeros_like(body, dtype=np.uint8)

    if not nonempty:
        return PercentResult(
            row_categories=counts.row_categories,
            col_categories=counts.col_categories,
            stat_categories=_TWO_WAY_STATS,
            stat_value_kinds=_TWO_WAY_VALUE_KINDS,
            stat_formats=_TWO_WAY_FORMATS,
            has_row_total=False,
            has_col_total=False,
            body=body,
            missing=missing,
        )

    row_sums = raw.sum(axis=1)
    col_sums = raw.sum(axis=0)
    grand_total = float(raw.sum())

    # Data cells
    for i in range(n_rows_data):
        rs = float(row_sums[i])
        for j in range(n_cols_data):
            n = float(raw[i, j])
            cs = float(col_sums[j])
            base = j * n_stats
            body[i, base + 0] = n
            _set_percent(body, missing, i, base + 1, n, rs)            # Row%
            _set_percent(body, missing, i, base + 2, n, cs)            # Col%
            _set_percent(body, missing, i, base + 3, n, grand_total)   # Tot%

    # Total column (across cols of each data row)
    if has_col_total:
        tc_base = n_cols_data * n_stats
        for i in range(n_rows_data):
            rs = float(row_sums[i])
            body[i, tc_base + 0] = rs                                # N
            body[i, tc_base + 1] = 100.0 if rs > 0 else 0.0          # Row% (by def)
            if rs == 0:
                missing[i, tc_base + 1] = MissingReason.NOT_APPLICABLE
            _set_percent(body, missing, i, tc_base + 2, rs, grand_total)  # Col%
            _set_percent(body, missing, i, tc_base + 3, rs, grand_total)  # Tot%

    # Total row (across rows of each data col)
    if has_row_total:
        tr = n_rows_data
        for j in range(n_cols_data):
            cs = float(col_sums[j])
            base = j * n_stats
            body[tr, base + 0] = cs                                   # N
            _set_percent(body, missing, tr, base + 1, cs, grand_total)   # Row%
            body[tr, base + 2] = 100.0 if cs > 0 else 0.0             # Col% (by def)
            if cs == 0:
                missing[tr, base + 2] = MissingReason.NOT_APPLICABLE
            _set_percent(body, missing, tr, base + 3, cs, grand_total)   # Tot%

        # Grand Total cell (Total row × Total col)
        if has_col_total:
            tc_base = n_cols_data * n_stats
            body[tr, tc_base + 0] = grand_total
            for s in range(1, n_stats):
                if grand_total > 0:
                    body[tr, tc_base + s] = 100.0
                else:
                    missing[tr, tc_base + s] = MissingReason.NOT_APPLICABLE

    return PercentResult(
        row_categories=counts.row_categories,
        col_categories=counts.col_categories,
        stat_categories=_TWO_WAY_STATS,
        stat_value_kinds=_TWO_WAY_VALUE_KINDS,
        stat_formats=_TWO_WAY_FORMATS,
        has_row_total=has_row_total,
        has_col_total=has_col_total,
        body=body,
        missing=missing,
    )


def _set_percent(
    body: np.ndarray,
    missing: np.ndarray,
    i: int,
    j: int,
    numerator: float,
    denominator: float,
) -> None:
    """Write `numerator / denominator * 100` to body[i, j], or flag the
    cell as NOT_APPLICABLE if the denominator is zero. Centralizes the
    divide-by-zero contract for every percent-stat cell."""
    if denominator > 0:
        body[i, j] = numerator / denominator * 100.0
    else:
        missing[i, j] = MissingReason.NOT_APPLICABLE


# === F5: axis construction =================================================


@dataclass(frozen=True)
class AxisBuildResult:
    """Row + col Axes assembled from a `PercentResult`, plus per-col-leaf
    `value_kinds` and `formats` (expanded from per-stat metadata by tiling
    across column groups for two-way tables).

    F6 takes this plus the `body` / `missing` matrices from `PercentResult`
    and assembles the final `Table`.
    """

    row_axis: Axis
    col_axis: Axis
    value_kinds: tuple[ValueKind, ...]
    formats: tuple[str | None, ...]


def build_axes(percents: PercentResult, spec: FreqSpec) -> AxisBuildResult:
    """Build validated row + col Axes from a `PercentResult` and spec.

    Calls `Axis.validate()` on both outputs, so a successful return means
    the axes satisfy every TABLE_MODEL.md invariant — including the
    positional-path / role-marker / span / depth checks. F6 can trust the
    Axis shapes without re-checking.
    """
    row_axis = _build_row_axis(percents, spec)
    if percents.col_categories is None:
        col_axis = _build_col_axis_one_way(percents)
    else:
        col_axis = _build_col_axis_two_way(percents, spec)

    row_axis.validate()
    col_axis.validate()

    value_kinds, formats = _expand_per_col_leaf(percents)

    return AxisBuildResult(
        row_axis=row_axis,
        col_axis=col_axis,
        value_kinds=value_kinds,
        formats=formats,
    )


def _build_row_axis(percents: PercentResult, spec: FreqSpec) -> Axis:
    key = spec.keys[0]
    label = (spec.label or {}).get(key)
    row_dim = Dimension(
        name=key,
        kind="category",
        categories=percents.row_categories,
        label=label,
    )

    leaves: list[Node] = [
        Node(path=(cat,), depth=1, span=1, role="data")
        for cat in percents.row_categories
    ]
    if percents.has_row_total:
        leaves.append(
            Node(path=(TotalMarker(),), depth=1, span=1,
                 role="total", label="Total")
        )

    tree = Node(
        path=(),
        depth=0,
        span=sum(leaf.span for leaf in leaves),
        role="data",
        children=tuple(leaves),
    )
    return Axis(dims=(row_dim,), tree=tree)


def _build_col_axis_one_way(percents: PercentResult) -> Axis:
    stat_dim = Dimension(
        name="_stat",
        kind="stat",
        categories=percents.stat_categories,
    )
    leaves = tuple(
        Node(path=(stat,), depth=1, span=1, role="data")
        for stat in percents.stat_categories
    )
    tree = Node(
        path=(),
        depth=0,
        span=sum(leaf.span for leaf in leaves),
        role="data",
        children=leaves,
    )
    return Axis(dims=(stat_dim,), tree=tree)


def _build_col_axis_two_way(percents: PercentResult, spec: FreqSpec) -> Axis:
    col_key = spec.keys[1]
    col_label = (spec.label or {}).get(col_key)
    col_dim = Dimension(
        name=col_key,
        kind="category",
        categories=percents.col_categories,
        label=col_label,
    )
    stat_dim = Dimension(
        name="_stat",
        kind="stat",
        categories=percents.stat_categories,
    )

    branches: list[Node] = []
    for cat in percents.col_categories:
        stat_leaves = tuple(
            Node(path=(cat, stat), depth=2, span=1, role="data")
            for stat in percents.stat_categories
        )
        branches.append(Node(
            path=(cat,),
            depth=1,
            span=sum(leaf.span for leaf in stat_leaves),
            role="data",
            children=stat_leaves,
        ))

    if percents.has_col_total:
        total_marker = TotalMarker()
        stat_leaves = tuple(
            Node(path=(total_marker, stat), depth=2, span=1, role="total")
            for stat in percents.stat_categories
        )
        branches.append(Node(
            path=(total_marker,),
            depth=1,
            span=sum(leaf.span for leaf in stat_leaves),
            role="total",
            label="Total",
            children=stat_leaves,
        ))

    tree = Node(
        path=(),
        depth=0,
        span=sum(b.span for b in branches),
        role="data",
        children=tuple(branches),
    )
    return Axis(dims=(col_dim, stat_dim), tree=tree)


def _expand_per_col_leaf(
    percents: PercentResult,
) -> tuple[tuple[ValueKind, ...], tuple[str | None, ...]]:
    """Expand per-stat value_kinds/formats to per-col-leaf.

    One-way: same as per-stat (col leaves = stat leaves).
    Two-way: tiled across (n col cats + optional Total col) groups.
    """
    if percents.col_categories is None:
        return percents.stat_value_kinds, tuple(percents.stat_formats)

    n_col_groups = len(percents.col_categories) + (
        1 if percents.has_col_total else 0
    )
    value_kinds = percents.stat_value_kinds * n_col_groups
    formats: tuple[str | None, ...] = percents.stat_formats * n_col_groups
    return value_kinds, formats
