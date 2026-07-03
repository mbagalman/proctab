"""`tabulate()` — multi-dimensional summary tables. See TABULATE_API.md for design.

Public entry point: `tabulate(data, *, rows, cols, values, ...)`.

Internal pipeline (also importable for testing):
- `SUPPORTED_STATS`, `STAT_EXPRS`, `STAT_DEFAULTS`: per-stat registries.
- `TabSpec` (T1) + `_parse_tabulate_args()` (T2): parsed args.
- `aggregate_data_cells()` (T4a): per-group stat values + companion signals.
- `aggregate_totals()` (T4b): subtotal + grand-total sections from source.
- `assemble_body()` (T4c): final body + missing matrices + leaf layouts.
- `build_tabulate_axes()` (T5): row + col Axes with metadata.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import narwhals.stable.v1 as nw
import numpy as np

from proctab._categories import (
    column_needs_nan_predicate,
    is_null,
    normalize,
    resolve_categories,
)
from proctab._engine import wrap
from proctab.model import (
    Axis,
    Category,
    Dimension,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
    ValueKind,
)


SUPPORTED_STATS: frozenset[str] = frozenset({
    "sum", "mean", "count", "min", "max", "median",
})


# === T3: stat-function registry ============================================


STAT_EXPRS: dict[str, Callable[[str], nw.Expr]] = {
    "sum":    lambda col: nw.col(col).sum(),
    "mean":   lambda col: nw.col(col).mean(),
    "count":  lambda col: nw.col(col).count(),   # non-null count (pandas .count() semantics)
    "min":    lambda col: nw.col(col).min(),
    "max":    lambda col: nw.col(col).max(),
    "median": lambda col: nw.col(col).median(),
}


STAT_DEFAULTS: dict[str, tuple[ValueKind, str]] = {
    "sum":    ("sum",    "{:,.0f}"),
    "mean":   ("mean",   "{:,.2f}"),
    "count":  ("count",  "{:,.0f}"),
    "min":    ("raw",    "{:,.0f}"),
    "max":    ("raw",    "{:,.0f}"),
    "median": ("median", "{:,.2f}"),
}
"""Per-stat default `(value_kind, format_string)` pairs from
TABULATE_API.md's stat table. T5 looks these up per col leaf to populate
`TabulateAxes.value_kinds` and `.formats`. Keys must stay in sync with
`SUPPORTED_STATS`."""
"""Maps a v0.1 stat name to a callable that, given a column name, returns
a narwhals expression suitable for use in `.agg(...)`. All entries are
NaN-aware by the engine's default semantics:

- `sum`, `mean`, `min`, `max`, `median`: nulls are skipped.
- `count`: returns the count of non-null values (NOT row count). Row
  count is computed separately via `nw.len()` in the aggregation kernel
  to drive the EMPTY/NULL distinction per TABULATE_API.md T4c.

Keys must stay in sync with `SUPPORTED_STATS`; an invariant test guards
that pairing.
"""


_RESERVED_DIM_NAMES = frozenset({"_metric", "_stat"})
"""Synthetic col-axis dim names produced internally by `tabulate()`.
User columns with these exact names would collide with the synthetic
dims when the col tree is built (`(user cols, _metric, _stat)` per
TABULATE_API.md), so `_parse_tabulate_args` rejects them up front."""


def _reject_reserved_names(names, *, arg_name: str) -> None:
    """Raise if any user-supplied dim name in `names` is reserved.

    Reserved names are `_metric` and `_stat` — see TABULATE_API.md's
    col-axis structure. Caller passes the kwarg name (`"rows"`,
    `"cols"`, `"values"`) so the error points at the offending input.
    """
    offenders = sorted({n for n in names if n in _RESERVED_DIM_NAMES})
    if offenders:
        raise ValueError(
            f"tabulate() {arg_name}= contains reserved synthetic-dim "
            f"name(s): {offenders}. '_metric' and '_stat' are reserved "
            f"for tabulate()'s internal col-axis dim names. Rename the "
            f"source column(s) (e.g., "
            f"df = df.rename(columns={{'_metric': 'metric_id'}})) "
            f"before calling tabulate()."
        )


def _fresh_alias(used: set[str], base: str) -> str:
    """Return a unique internal aggregation alias and reserve it in ``used``."""
    alias = base
    i = 1
    while alias in used:
        alias = f"{base}{i}"
        i += 1
    used.add(alias)
    return alias


@dataclass(frozen=True)
class TabSpec:
    """Parsed and validated `tabulate()` arguments. Internal — not part
    of the public API.

    `values_spec` is the ordered list of `(metric, stat)` pairs after
    parsing the user's `values=` dict. Metric order = dict insertion
    order; stat order within a metric = the user's list order. This is
    the col-leaf order before user-col dim tiling.

    `levels` and `label` are stored as Mappings; their immutability is
    by intent only (Python doesn't enforce dict immutability inside
    frozen dataclasses). Downstream code must not mutate them.
    """

    rows: tuple[str, ...]
    cols: tuple[str, ...] = ()
    values_spec: tuple[tuple[str, str], ...] = ()
    subtotals: tuple[str, ...] = ()
    totals: bool = True
    observed: bool = True
    dropna: bool = False
    levels: Mapping[str, Sequence[Any]] | None = None
    label: Mapping[str, str] | None = None


def _parse_tabulate_args(
    *,
    rows: str | Sequence[str],
    cols: str | Sequence[str] = (),
    values: Mapping[str, str | Sequence[str]],
    subtotals: str | Sequence[str] | None = None,
    totals: bool = True,
    observed: bool = True,
    dropna: bool = False,
    levels: Mapping[str, Sequence[Any]] | None = None,
    label: Mapping[str, str] | None = None,
    weight: Mapping[str, str] | None = None,
    test: str | None = None,
) -> TabSpec:
    """Normalize and validate `tabulate()` arguments into a `TabSpec`.

    Reserved-kwarg checks (`weight=`, `test=`) run before any other
    validation, so a user who hits an unsupported feature learns about
    it before any other error fires.
    """
    if weight is not None:
        raise NotImplementedError(
            "weight= is reserved for weighted statistics in v0.2 and is "
            "not implemented in v0.1."
        )
    if test is not None:
        raise NotImplementedError(
            "test= is reserved for statistical tests (chi-square, Fisher's, "
            "Cramér's V) in v0.2 and is not implemented in v0.1."
        )

    rows_t = _normalize_dim_list(rows, arg_name="rows",
                                 min_count=1, max_count=2)
    _reject_reserved_names(rows_t, arg_name="rows")
    cols_t = _normalize_dim_list(cols, arg_name="cols",
                                 min_count=0, max_count=1)
    _reject_reserved_names(cols_t, arg_name="cols")

    overlap = set(rows_t) & set(cols_t)
    if overlap:
        raise ValueError(
            f"tabulate() rows and cols cannot share dims; got overlap: "
            f"{sorted(overlap)}."
        )

    values_spec = _normalize_values(values)
    _reject_reserved_names(
        {metric for metric, _stat in values_spec}, arg_name="values"
    )
    subtotals_t = _normalize_subtotals(subtotals, rows_t)

    grouping_keys = set(rows_t) | set(cols_t)
    if levels is not None:
        extra = set(levels) - grouping_keys
        if extra:
            raise ValueError(
                f"tabulate() levels= contains keys not in rows or cols: "
                f"{sorted(extra)}. levels= keys must be a subset of "
                f"{sorted(grouping_keys)}."
            )
        for k, v in levels.items():
            if isinstance(v, str) or not isinstance(v, (list, tuple)):
                raise TypeError(
                    f"tabulate() levels[{k!r}] must be a list or tuple; "
                    f"got {type(v).__name__}."
                )
            normalized_levels = [normalize(level) for level in v]
            if len(set(normalized_levels)) != len(normalized_levels):
                raise ValueError(
                    f"tabulate() levels[{k!r}] contains duplicate values; "
                    f"got {list(v)}. Each level value must appear at "
                    f"most once (otherwise leaves with identical paths "
                    f"would share an index, silently misrouting data)."
                )

    if label is not None:
        extra = set(label) - grouping_keys
        if extra:
            raise ValueError(
                f"tabulate() label= contains keys not in rows or cols: "
                f"{sorted(extra)}. label= keys must be a subset of "
                f"{sorted(grouping_keys)}."
            )

    return TabSpec(
        rows=rows_t,
        cols=cols_t,
        values_spec=values_spec,
        subtotals=subtotals_t,
        totals=totals,
        observed=observed,
        dropna=dropna,
        levels=levels,
        label=label,
    )


def _normalize_dim_list(
    arg: Any, *, arg_name: str, min_count: int, max_count: int,
) -> tuple[str, ...]:
    """Accept a string or list/tuple of strings; normalize to a tuple.

    Validates count range (min_count..max_count inclusive), uniqueness,
    and that every item is a non-empty string. Empty tuple/list is valid
    only if `min_count == 0`.
    """
    if isinstance(arg, str):
        if not arg:
            raise ValueError(
                f"tabulate() {arg_name} must contain non-empty strings."
            )
        items: tuple[str, ...] = (arg,)
    elif isinstance(arg, (list, tuple)):
        items = tuple(arg)
        if items and not all(isinstance(x, str) for x in items):
            raise TypeError(
                f"tabulate() {arg_name} items must be strings; got types "
                f"{[type(x).__name__ for x in items]}."
            )
        if any(not x for x in items):
            raise ValueError(
                f"tabulate() {arg_name} must contain non-empty strings."
            )
    else:
        raise TypeError(
            f"tabulate() {arg_name} must be a string or list/tuple of "
            f"strings; got {type(arg).__name__}."
        )

    if len(items) < min_count:
        raise ValueError(
            f"tabulate() requires at least {min_count} {arg_name} dim(s); "
            f"got {len(items)}."
        )
    if len(items) > max_count:
        raise ValueError(
            f"tabulate() supports at most {max_count} {arg_name} dim(s) "
            f"in v0.1; got {len(items)}. v0.2 will lift this cap."
        )
    if len(set(items)) != len(items):
        raise ValueError(
            f"tabulate() {arg_name} dims must be unique; got {list(items)}."
        )

    return items


def _normalize_values(
    values: Any,
) -> tuple[tuple[str, str], ...]:
    """Normalize `{metric: stat | [stat, ...]}` to ordered `((metric, stat), ...)`.

    Preserves metric order (dict insertion order) and stat order (user
    list order). Validates each stat name against `SUPPORTED_STATS`;
    raises `NotImplementedError` specifically for `"weighted_mean"`.
    """
    if not isinstance(values, Mapping):
        raise TypeError(
            f"tabulate() values= must be a mapping {{metric: stat | [stat, ...]}}; "
            f"got {type(values).__name__}."
        )
    if not values:
        raise ValueError(
            "tabulate() requires at least one metric in values=."
        )

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for metric, stat_spec in values.items():
        if not isinstance(metric, str) or not metric:
            raise TypeError(
                f"tabulate() values= metric keys must be non-empty strings; "
                f"got {metric!r}."
            )

        if isinstance(stat_spec, str):
            stats: tuple[str, ...] = (stat_spec,)
        elif isinstance(stat_spec, (list, tuple)):
            stats = tuple(stat_spec)
            if not all(isinstance(s, str) for s in stats):
                raise TypeError(
                    f"tabulate() values[{metric!r}] stat names must be "
                    f"strings; got types {[type(s).__name__ for s in stats]}."
                )
        else:
            raise TypeError(
                f"tabulate() values[{metric!r}] must be a string or "
                f"list/tuple of strings; got {type(stat_spec).__name__}."
            )

        if not stats:
            raise ValueError(
                f"tabulate() values[{metric!r}] is empty; at least one "
                f"stat is required per metric."
            )

        for stat in stats:
            if stat == "weighted_mean":
                raise NotImplementedError(
                    f"tabulate() values[{metric!r}]: 'weighted_mean' is a "
                    f"v0.2 feature. Use the reserved weight= kwarg in v0.2 "
                    f"when it lands."
                )
            if stat not in SUPPORTED_STATS:
                raise ValueError(
                    f"tabulate() values[{metric!r}] has unknown stat "
                    f"{stat!r}. v0.1 supports: {sorted(SUPPORTED_STATS)}."
                )
            if (metric, stat) in seen:
                raise ValueError(
                    f"tabulate() values[{metric!r}] has duplicate stat "
                    f"{stat!r}; each (metric, stat) pair must appear at "
                    f"most once (otherwise two col leaves would share the "
                    f"same path)."
                )
            seen.add((metric, stat))
            pairs.append((metric, stat))

    return tuple(pairs)


def _normalize_subtotals(
    subtotals: Any, rows: tuple[str, ...],
) -> tuple[str, ...]:
    """Normalize None/str/sequence-of-str to a tuple of row-dim names.

    Validates that every name is in `rows` AND is not the innermost row
    dim (which would tautologically duplicate leaf rows).
    """
    if subtotals is None:
        return ()

    if isinstance(subtotals, str):
        items: tuple[str, ...] = (subtotals,)
    elif isinstance(subtotals, (list, tuple)):
        items = tuple(subtotals)
        if not all(isinstance(x, str) for x in items):
            raise TypeError(
                f"tabulate() subtotals items must be strings; got types "
                f"{[type(x).__name__ for x in items]}."
            )
    else:
        raise TypeError(
            f"tabulate() subtotals must be a string, list, or None; got "
            f"{type(subtotals).__name__}."
        )

    if len(set(items)) != len(items):
        raise ValueError(
            f"tabulate() subtotals must be unique; got {list(items)}."
        )

    extra = set(items) - set(rows)
    if extra:
        raise ValueError(
            f"tabulate() subtotals contains names not in rows=: "
            f"{sorted(extra)}. subtotals must be a subset of rows={list(rows)}."
        )

    if rows:
        innermost = rows[-1]
        if innermost in items:
            raise ValueError(
                f"subtotals={innermost!r} is the innermost row dim and "
                f"would duplicate leaf rows. Use a non-innermost dim "
                f"(e.g., {rows[0]!r}) or omit subtotals."
            )

    return items


# === T4a: data-cell aggregation ============================================


@dataclass(frozen=True)
class AggregateResult:
    """Output of `aggregate_data_cells()` — per-group statistic values
    plus the companion signals T4c needs for `MissingReason` assignment.

    Shapes:
      stat_values:   (R, C, S)  one value per (group, stat-leaf)
      row_count:     (R, C)     `nw.len()` per group — drives EMPTY detection
      nonnull_count: (R, C, M)  `count()` per (group, metric) — drives NULL detection

    Where:
      R = product of row-dim category sizes (cross-product order)
      C = product of col-dim category sizes (or 1 if `spec.cols` is empty)
      S = len(spec.values_spec) — one entry per requested (metric, stat)
      M = number of unique metrics (in `metric_names` order)

    `row_categories` and `col_categories` are tuples-of-tuples (one tuple
    per dim). T5 consumes these to build the row/col `Axis` trees; the
    flat group ordering matches row-major flattening of those per-dim
    cat lengths. T4b consumes the spec to compute subtotals/grand
    totals; T4c consumes `row_count` + `nonnull_count` + `stat_values`
    to fill the final body + missing matrices.
    """

    row_categories: tuple[tuple[Category, ...], ...]
    col_categories: tuple[tuple[Category, ...], ...]
    metric_names: tuple[str, ...]
    stat_values: np.ndarray
    row_count: np.ndarray
    nonnull_count: np.ndarray


def aggregate_data_cells(nw_df: nw.DataFrame, spec: TabSpec) -> AggregateResult:
    """Compute per-group stat values from a narwhals-wrapped DataFrame.

    Data cells only — subtotals and the grand total are computed by T4b
    in separate groupby passes against source (required for non-additive
    stats like mean/median).

    Aggregations run via the shared `_aggregate_section_arrays()` helper:
    `nw.len()` per group (T4c's EMPTY signal), `nw.col(metric).count()`
    per unique metric (T4c's NULL signal), `STAT_EXPRS[stat](metric)`
    per `(metric, stat)` in `spec.values_spec`.
    """
    keys = list(spec.rows + spec.cols)

    if spec.dropna:
        nw_df = nw_df.drop_nulls(subset=keys)

    row_cats_per_dim = tuple(
        resolve_categories(nw_df, k, observed=spec.observed,
                           dropna=spec.dropna, levels=spec.levels)
        for k in spec.rows
    )
    col_cats_per_dim = tuple(
        resolve_categories(nw_df, k, observed=spec.observed,
                           dropna=spec.dropna, levels=spec.levels)
        for k in spec.cols
    )

    row_dim_sizes = [len(c) for c in row_cats_per_dim]
    col_dim_sizes = [len(c) for c in col_cats_per_dim]

    n_rows = _product(row_dim_sizes) if row_dim_sizes else 1
    n_cols = _product(col_dim_sizes) if col_dim_sizes else 1
    n_stats = len(spec.values_spec)

    if n_rows * n_cols * n_stats > 10_000_000:
        raise ValueError(
            f"tabulate() estimated dense matrix size ({n_rows} rows x "
            f"{n_cols} cols x {n_stats} stats) "
            "exceeds 10 million cells. This would require excessive memory. "
            "Reduce the cardinality of your grouping columns."
        )

    metric_names = tuple(dict.fromkeys(m for m, _ in spec.values_spec))

    row_idx_maps = [{cat.value: i for i, cat in enumerate(cats)}
                    for cats in row_cats_per_dim]
    col_idx_maps = [{cat.value: j for j, cat in enumerate(cats)}
                    for cats in col_cats_per_dim]

    stat_values, row_count, nonnull_count = _aggregate_section_arrays(
        nw_df,
        group_keys=keys,
        row_key_names=list(spec.rows),
        row_key_idx_maps=row_idx_maps,
        row_dim_sizes=row_dim_sizes,
        col_key_names=list(spec.cols),
        col_key_idx_maps=col_idx_maps,
        col_dim_sizes=col_dim_sizes,
        metric_names=metric_names,
        values_spec=spec.values_spec,
    )

    return AggregateResult(
        row_categories=row_cats_per_dim,
        col_categories=col_cats_per_dim,
        metric_names=metric_names,
        stat_values=stat_values,
        row_count=row_count,
        nonnull_count=nonnull_count,
    )


def _aggregate_section_arrays(
    nw_df: nw.DataFrame,
    *,
    group_keys: list[str],
    row_key_names: list[str],
    row_key_idx_maps: list[dict],
    row_dim_sizes: list[int],
    col_key_names: list[str],
    col_key_idx_maps: list[dict],
    col_dim_sizes: list[int],
    metric_names: tuple[str, ...],
    values_spec: tuple[tuple[str, str], ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run one groupby+agg pass and materialize the three companion arrays.

    Shared between T4a (data cells) and T4b (subtotals/grand totals).
    Each section selects different subsets of `row_key_names` /
    `col_key_names` from the full rows + cols, with the corresponding
    `*_idx_maps` and `*_dim_sizes` describing only those subsets.

    Empty `row_key_names` collapses the section's row axis to length 1
    (a single "total" row); same for `col_key_names`.

    Returns `(stat_values, row_count, nonnull_count)` shaped as:
    - `stat_values`: `(R, C, S)` where R/C are products of the
      corresponding `*_dim_sizes` (or 1 if empty), S = `len(values_spec)`
    - `row_count`: `(R, C)`
    - `nonnull_count`: `(R, C, M)` with M = `len(metric_names)`
    """
    n_rows = _product(row_dim_sizes) if row_dim_sizes else 1
    n_cols = _product(col_dim_sizes) if col_dim_sizes else 1
    n_metrics = len(metric_names)
    n_stats = len(values_spec)

    stat_values = np.zeros((n_rows, n_cols, n_stats), dtype=np.float64)
    row_count = np.zeros((n_rows, n_cols), dtype=np.int64)
    nonnull_count = np.zeros((n_rows, n_cols, n_metrics), dtype=np.int64)

    if n_rows == 0 or n_cols == 0:
        return stat_values, row_count, nonnull_count

    metric_idx_map = {m: i for i, m in enumerate(metric_names)}

    used_aliases = set(nw_df.columns)
    row_count_alias = _fresh_alias(used_aliases, "__rowcount__")
    metric_aliases: dict[str, str] = {}
    stat_aliases: list[str] = []

    aggs: list[nw.Expr] = [nw.len().alias(row_count_alias)]
    for metric_idx, metric in enumerate(metric_names):
        alias = _fresh_alias(used_aliases, f"__nnc__{metric_idx}__")
        metric_aliases[metric] = alias
        aggs.append(nw.col(metric).count().alias(alias))
    for idx, (metric, stat) in enumerate(values_spec):
        alias = _fresh_alias(used_aliases, f"__sv__{idx}__")
        stat_aliases.append(alias)
        aggs.append(STAT_EXPRS[stat](metric).alias(alias))

    if group_keys:
        grouped = nw_df.group_by(group_keys).agg(*aggs)
    else:
        # No group keys → single-row aggregate over the whole frame.
        grouped = nw_df.select(*aggs)

    for row in grouped.iter_rows(named=True):
        if row_key_names:
            r = _group_flat_index(row, row_key_names, row_key_idx_maps, row_dim_sizes)
            if r is None:
                continue
        else:
            r = 0

        if col_key_names:
            c = _group_flat_index(row, col_key_names, col_key_idx_maps, col_dim_sizes)
            if c is None:
                continue
        else:
            c = 0

        row_count[r, c] = row[row_count_alias]
        for metric in metric_names:
            nonnull_count[r, c, metric_idx_map[metric]] = row[metric_aliases[metric]]

        for idx, (metric, stat) in enumerate(values_spec):
            v = row[stat_aliases[idx]]
            stat_values[r, c, idx] = 0.0 if is_null(v) else float(v)

    return stat_values, row_count, nonnull_count


def _product(xs: list[int]) -> int:
    p = 1
    for x in xs:
        p *= x
    return p


def _filter_to_displayed_domain(
    nw_df: nw.DataFrame,
    keys: list[str],
    cats_per_dim: list[tuple[Category, ...]],
) -> nw.DataFrame:
    """Filter `nw_df` to rows whose values across each listed key are in
    that dim's displayed category domain.

    Used by `aggregate_totals` so total sections (which collapse one or
    both axes) still honor each dim's `levels=` filter. If a dim's
    displayed categories include the synthetic Missing category
    (`Category(value=None, label="Missing")`), source rows with null
    values for that key are kept; otherwise they're filtered out.
    """
    for key, cats in zip(keys, cats_per_dim):
        values = [c.value for c in cats]
        has_null = any(v is None for v in values)
        non_nulls = [v for v in values if v is not None]

        null_expr = nw.col(key).is_null()
        if has_null and column_needs_nan_predicate(nw_df, key):
            null_expr = null_expr | nw.col(key).is_nan()

        if non_nulls and has_null:
            expr = nw.col(key).is_in(non_nulls) | null_expr
        elif non_nulls:
            expr = nw.col(key).is_in(non_nulls)
        elif has_null:
            expr = null_expr
        else:
            # No displayed categories at all → no rows match.
            return nw_df.head(0)

        nw_df = nw_df.filter(expr)

    return nw_df


def _group_flat_index(
    row: dict,
    keys: tuple[str, ...],
    idx_maps: list[dict],
    dim_sizes: list[int],
) -> int | None:
    """Convert a grouped row's key values into a flat row-major index.
    Returns None if any value isn't in the corresponding idx_map (which
    would happen if a group's category was filtered out by levels=)."""
    flat = 0
    for dim_i, key in enumerate(keys):
        value = normalize(row[key])
        idx = idx_maps[dim_i].get(value)
        if idx is None:
            return None
        flat = flat * dim_sizes[dim_i] + idx
    return flat


# === T4b: subtotals + grand-total aggregation ==============================


@dataclass(frozen=True)
class SectionResult:
    """One aggregation pass result for a (subtotal/total) section of the
    final body. Same triple-array shape as `AggregateResult`'s data-cell
    arrays, with the dimensions sized to that section's scope."""
    stat_values: np.ndarray   # (R, C, S)
    row_count: np.ndarray     # (R, C)
    nonnull_count: np.ndarray  # (R, C, M)


@dataclass(frozen=True)
class TotalsResult:
    """Subtotal + grand-total aggregations computed FROM SOURCE.

    Per TABULATE_API.md T4b, subtotals/totals cannot be derived by summing
    leaf cells from T4a — non-additive stats (mean, median) require fresh
    groupby passes against the source. All entries here are independent
    aggregations.

    Keys / shape per entry:

    - `subtotals_data_cols[dim_name]`: one entry per `spec.subtotals` dim.
      Shape `(n_subtotal_cats, C, S/M)` — subtotal rows under the data
      col groups (where C = T4a's n_cols).
    - `subtotals_total_col[dim_name]`: same dim names; only present when
      `spec.totals AND spec.cols` (i.e., a Total col exists). Shape
      `(n_subtotal_cats, 1, S/M)` — subtotal rows under the Total col.
    - `grand_row`: shape `(1, C, S/M)` — the Total row under data cols.
      None when `spec.totals=False` or `n_rows == 0`.
    - `grand_col`: shape `(R, 1, S/M)` — the Total col under data rows.
      None when `spec.totals=False` or `spec.cols=()` or any dim is empty.
    - `grand_cell`: shape `(1, 1, S/M)` — the Total row × Total col
      intersection. None whenever `grand_col` is None.
    """
    subtotals_data_cols: dict[str, SectionResult]
    subtotals_total_col: dict[str, SectionResult]
    grand_row: SectionResult | None
    grand_col: SectionResult | None
    grand_cell: SectionResult | None


def aggregate_totals(
    nw_df: nw.DataFrame, spec: TabSpec, data_result: AggregateResult,
) -> TotalsResult:
    """Run the subtotal + grand-total aggregation passes from source data.

    Reuses `data_result.row_categories` / `col_categories` / `metric_names`
    to avoid re-resolving the categorical domains. Honors `spec.dropna`
    in the same way `aggregate_data_cells()` did.

    Pre-filters `nw_df` to the displayed category domain across ALL row
    and col dims before any section is computed. Total sections collapse
    one or both axes (no key in the groupby) and would otherwise pull
    in source rows whose values were excluded by `levels=`. Subtotal
    sections that DO include the dim in their groupby already filter
    via per-cell index lookup; the pre-filter is redundant there but
    harmless and uniform.

    Sections are computed per the TABULATE_API conditions:
    - `subtotals_data_cols[dim]` for each `dim in spec.subtotals` (and
      `n_rows > 0`)
    - `subtotals_total_col[dim]` additionally when a Total col exists
    - `grand_row` when `spec.totals` and `n_rows > 0`
    - `grand_col` and `grand_cell` when `spec.totals` and a Total col exists
    """
    if spec.dropna:
        nw_df = nw_df.drop_nulls(subset=list(spec.rows + spec.cols))

    # P1 fix: filter source to the displayed category domain so total
    # sections that collapse a dim still respect that dim's levels=.
    nw_df = _filter_to_displayed_domain(
        nw_df,
        keys=list(spec.rows) + list(spec.cols),
        cats_per_dim=list(data_result.row_categories)
                     + list(data_result.col_categories),
    )

    row_dim_sizes = [len(c) for c in data_result.row_categories]
    col_dim_sizes = [len(c) for c in data_result.col_categories]
    n_rows = _product(row_dim_sizes) if row_dim_sizes else 0
    n_cols = _product(col_dim_sizes) if col_dim_sizes else 1

    row_idx_maps = [{cat.value: i for i, cat in enumerate(cats)}
                    for cats in data_result.row_categories]
    col_idx_maps = [{cat.value: j for j, cat in enumerate(cats)}
                    for cats in data_result.col_categories]

    has_any_row = n_rows > 0
    has_total_col = bool(spec.totals and spec.cols and n_cols > 0 and has_any_row)
    has_total_row = bool(spec.totals and has_any_row)

    # --- subtotals --------------------------------------------------------
    subtotals_data_cols: dict[str, SectionResult] = {}
    subtotals_total_col: dict[str, SectionResult] = {}

    for st_dim in spec.subtotals:
        if not has_any_row:
            break  # no rows at all → no subtotals
        st_idx = list(spec.rows).index(st_dim)
        # Outer rows kept in the groupby; inner rows consolidated.
        outer_rows = list(spec.rows)[: st_idx + 1]
        outer_idx_maps = row_idx_maps[: st_idx + 1]
        outer_sizes = row_dim_sizes[: st_idx + 1]

        # Subtotal under DATA cols
        sv, rc, nnc = _aggregate_section_arrays(
            nw_df,
            group_keys=outer_rows + list(spec.cols),
            row_key_names=outer_rows,
            row_key_idx_maps=outer_idx_maps,
            row_dim_sizes=outer_sizes,
            col_key_names=list(spec.cols),
            col_key_idx_maps=col_idx_maps,
            col_dim_sizes=col_dim_sizes,
            metric_names=data_result.metric_names,
            values_spec=spec.values_spec,
        )
        subtotals_data_cols[st_dim] = SectionResult(sv, rc, nnc)

        # Subtotal under TOTAL col (if a Total col exists)
        if has_total_col:
            sv, rc, nnc = _aggregate_section_arrays(
                nw_df,
                group_keys=outer_rows,
                row_key_names=outer_rows,
                row_key_idx_maps=outer_idx_maps,
                row_dim_sizes=outer_sizes,
                col_key_names=[],
                col_key_idx_maps=[],
                col_dim_sizes=[],
                metric_names=data_result.metric_names,
                values_spec=spec.values_spec,
            )
            subtotals_total_col[st_dim] = SectionResult(sv, rc, nnc)

    # --- grand row (Total row under data cols) ----------------------------
    grand_row: SectionResult | None = None
    if has_total_row:
        sv, rc, nnc = _aggregate_section_arrays(
            nw_df,
            group_keys=list(spec.cols),
            row_key_names=[],
            row_key_idx_maps=[],
            row_dim_sizes=[],
            col_key_names=list(spec.cols),
            col_key_idx_maps=col_idx_maps,
            col_dim_sizes=col_dim_sizes,
            metric_names=data_result.metric_names,
            values_spec=spec.values_spec,
        )
        grand_row = SectionResult(sv, rc, nnc)

    # --- grand col (Total col under data rows) ----------------------------
    grand_col: SectionResult | None = None
    grand_cell: SectionResult | None = None
    if has_total_col:
        sv, rc, nnc = _aggregate_section_arrays(
            nw_df,
            group_keys=list(spec.rows),
            row_key_names=list(spec.rows),
            row_key_idx_maps=row_idx_maps,
            row_dim_sizes=row_dim_sizes,
            col_key_names=[],
            col_key_idx_maps=[],
            col_dim_sizes=[],
            metric_names=data_result.metric_names,
            values_spec=spec.values_spec,
        )
        grand_col = SectionResult(sv, rc, nnc)

        # --- grand cell (Total row × Total col) ---------------------------
        sv, rc, nnc = _aggregate_section_arrays(
            nw_df,
            group_keys=[],
            row_key_names=[],
            row_key_idx_maps=[],
            row_dim_sizes=[],
            col_key_names=[],
            col_key_idx_maps=[],
            col_dim_sizes=[],
            metric_names=data_result.metric_names,
            values_spec=spec.values_spec,
        )
        grand_cell = SectionResult(sv, rc, nnc)

    return TotalsResult(
        subtotals_data_cols=subtotals_data_cols,
        subtotals_total_col=subtotals_total_col,
        grand_row=grand_row,
        grand_col=grand_col,
        grand_cell=grand_cell,
    )


# === T4c: body assembly + MissingReason assignment =========================


@dataclass(frozen=True)
class RowLeafEntry:
    """Layout entry for one row leaf in the assembled body.

    `role` selects which fields are meaningful:
    - `"data"`: `data_row_idx` (into `AggregateResult.stat_values` axis 0)
    - `"subtotal"`: `subtotal_dim` + `subtotal_row_idx` (into
      `TotalsResult.subtotals_data_cols[dim].stat_values` axis 0)
    - `"total"`: no further fields
    """
    role: str
    data_row_idx: int | None = None
    subtotal_dim: str | None = None
    subtotal_row_idx: int | None = None


@dataclass(frozen=True)
class ColLeafEntry:
    """Layout entry for one col leaf in the assembled body.

    `role` selects which T4b section a (row.role, col.role) pair fetches
    from. `col_group_idx` is the col-dim cross-product position (0 when
    `spec.cols` is empty); `stat_idx` is the index into
    `spec.values_spec`.
    """
    role: str
    col_group_idx: int
    stat_idx: int


@dataclass(frozen=True)
class TabulateAssembled:
    """Final body + missing matrices for the Table, plus the layouts T5
    will consume to build the row / col `Axis` trees.

    `body[i, j]` and `missing[i, j]` correspond to the cell at
    `row_layout[i]` × `col_layout[j]`. T5 doesn't recompute layout from
    spec — it walks these tuples in order.
    """
    body: np.ndarray
    missing: np.ndarray
    row_layout: tuple[RowLeafEntry, ...]
    col_layout: tuple[ColLeafEntry, ...]


def assemble_body(
    data_result: AggregateResult,
    totals_result: TotalsResult,
    spec: TabSpec,
) -> TabulateAssembled:
    """Assemble the final body + missing matrices from T4a + T4b outputs.

    The (row.role, col.role) of each cell selects one of six source
    sections; the per-cell `MissingReason` is assigned per the
    TABULATE_API priority: row_count=0 → EMPTY, then non-null=0 (except
    for the `count` stat) → NULL, otherwise PRESENT with the stored
    value.
    """
    row_layout = _build_row_layout(spec, data_result)
    col_layout = _build_col_layout(spec, data_result)

    n_rows = len(row_layout)
    n_cols = len(col_layout)

    body = np.zeros((n_rows, n_cols), dtype=np.float64)
    missing = np.zeros((n_rows, n_cols), dtype=np.uint8)

    if n_rows == 0 or n_cols == 0:
        return TabulateAssembled(
            body=body, missing=missing,
            row_layout=row_layout, col_layout=col_layout,
        )

    metric_idx_by_name = {m: i for i, m in enumerate(data_result.metric_names)}

    for i, row_entry in enumerate(row_layout):
        for j, col_entry in enumerate(col_layout):
            _fill_cell(
                body, missing, i, j,
                row_entry, col_entry,
                data_result, totals_result, spec,
                metric_idx_by_name,
            )

    return TabulateAssembled(
        body=body, missing=missing,
        row_layout=row_layout, col_layout=col_layout,
    )


def _build_row_layout(
    spec: TabSpec, data_result: AggregateResult,
) -> tuple[RowLeafEntry, ...]:
    """Build the ordered row leaf layout per TABULATE_API conventions.

    1-row case: data leaves in row category order, then optional Total.
    2-row case with subtotal at outer dim: for each outer cat, all inner
    cats (data leaves), then a subtotal leaf for that outer cat. Grand
    total leaf appended last (when totals=True and ≥1 row leaf exists).
    """
    layout: list[RowLeafEntry] = []
    row_cats = data_result.row_categories
    if not row_cats:
        return tuple(layout)

    n_dims = len(row_cats)
    sizes = [len(c) for c in row_cats]
    has_data = _product(sizes) > 0

    if n_dims == 1:
        for r in range(sizes[0]):
            layout.append(RowLeafEntry(role="data", data_row_idx=r))
    else:
        # 2-dim row case (v0.1 cap). row-major flat order matches T4a.
        outer_size, inner_size = sizes
        has_subtotal = bool(spec.subtotals)
        # v0.1: only outer-dim subtotals are allowed (innermost is rejected
        # by T2). subtotal_dim is the outer dim name when present.
        subtotal_dim = spec.subtotals[0] if has_subtotal else None
        for outer_i in range(outer_size):
            for inner_i in range(inner_size):
                data_idx = outer_i * inner_size + inner_i
                layout.append(RowLeafEntry(role="data", data_row_idx=data_idx))
            if has_subtotal:
                layout.append(RowLeafEntry(
                    role="subtotal",
                    subtotal_dim=subtotal_dim,
                    subtotal_row_idx=outer_i,
                ))

    if spec.totals and has_data:
        layout.append(RowLeafEntry(role="total"))

    return tuple(layout)


def _build_col_layout(
    spec: TabSpec, data_result: AggregateResult,
) -> tuple[ColLeafEntry, ...]:
    """Build the ordered col leaf layout.

    Per the TABULATE_API ordering contract, the col hierarchy is
    `user_cols → _metric → _stat`. Each user col category expands into
    `len(spec.values_spec)` stat leaves. A Total-col block is appended
    when `spec.totals AND spec.cols AND data is non-empty on both axes`.
    """
    layout: list[ColLeafEntry] = []
    col_cats = data_result.col_categories
    n_stats = len(spec.values_spec)
    n_rows_data, n_cols_data, _ = data_result.stat_values.shape

    if col_cats:
        # cols= non-empty; v0.1 has at most 1 col dim
        n_col_cats = len(col_cats[0])
        for c_i in range(n_col_cats):
            for s in range(n_stats):
                layout.append(ColLeafEntry(
                    role="data", col_group_idx=c_i, stat_idx=s,
                ))
        # Total col only when totals + cols + non-empty on both axes
        if (spec.totals and n_cols_data > 0 and n_rows_data > 0):
            for s in range(n_stats):
                layout.append(ColLeafEntry(
                    role="total", col_group_idx=0, stat_idx=s,
                ))
    else:
        # cols=() → just one implicit col group, no Total col
        for s in range(n_stats):
            layout.append(ColLeafEntry(
                role="data", col_group_idx=0, stat_idx=s,
            ))

    return tuple(layout)


def _fill_cell(
    body: np.ndarray,
    missing: np.ndarray,
    i: int,
    j: int,
    row_entry: RowLeafEntry,
    col_entry: ColLeafEntry,
    data_result: AggregateResult,
    totals_result: TotalsResult,
    spec: TabSpec,
    metric_idx_by_name: dict[str, int],
) -> None:
    """Dispatch a single cell to its source section, then apply
    MissingReason priority."""
    section = _select_section(row_entry, col_entry, data_result, totals_result)
    r_idx, c_idx = _section_indices(row_entry, col_entry)
    s_idx = col_entry.stat_idx

    metric, stat = spec.values_spec[s_idx]
    metric_idx = metric_idx_by_name[metric]

    rc = section.row_count[r_idx, c_idx]
    if rc == 0:
        missing[i, j] = MissingReason.EMPTY
        return

    nnc = section.nonnull_count[r_idx, c_idx, metric_idx]
    if nnc == 0 and stat != "count":
        # All metric values null in a non-empty group. 'count' is the
        # exception: it correctly reports 0 in this case (a meaningful
        # answer, not missing data).
        missing[i, j] = MissingReason.NULL
        return

    body[i, j] = section.stat_values[r_idx, c_idx, s_idx]


def _select_section(
    row_entry: RowLeafEntry,
    col_entry: ColLeafEntry,
    data_result: AggregateResult,
    totals_result: TotalsResult,
) -> "_SectionLike":
    """Return the (stat_values, row_count, nonnull_count)-bearing object
    for this cell's (row.role, col.role) pair."""
    rr, cr = row_entry.role, col_entry.role
    if rr == "data" and cr == "data":
        return _SectionView(
            data_result.stat_values, data_result.row_count, data_result.nonnull_count,
        )
    if rr == "data" and cr == "total":
        return totals_result.grand_col  # type: ignore[return-value]
    if rr == "subtotal" and cr == "data":
        return totals_result.subtotals_data_cols[row_entry.subtotal_dim]
    if rr == "subtotal" and cr == "total":
        return totals_result.subtotals_total_col[row_entry.subtotal_dim]
    if rr == "total" and cr == "data":
        return totals_result.grand_row  # type: ignore[return-value]
    if rr == "total" and cr == "total":
        return totals_result.grand_cell  # type: ignore[return-value]
    raise RuntimeError(f"Unhandled (row, col) role pair: ({rr}, {cr})")


def _section_indices(
    row_entry: RowLeafEntry, col_entry: ColLeafEntry,
) -> tuple[int, int]:
    """Compute (r_idx, c_idx) into the selected section's arrays."""
    if row_entry.role == "data":
        r = row_entry.data_row_idx
    elif row_entry.role == "subtotal":
        r = row_entry.subtotal_row_idx
    else:  # total
        r = 0

    if col_entry.role == "data":
        c = col_entry.col_group_idx
    else:  # total
        c = 0

    return r, c


class _SectionView:
    """Adapter giving an `AggregateResult` the same attribute surface
    as `SectionResult`. Lets `_select_section()` return a uniform type
    regardless of whether the section comes from T4a or T4b."""
    __slots__ = ("stat_values", "row_count", "nonnull_count")

    def __init__(self, stat_values, row_count, nonnull_count):
        self.stat_values = stat_values
        self.row_count = row_count
        self.nonnull_count = nonnull_count


_SectionLike = Any  # SectionResult or _SectionView; same attribute surface


# === T5: axis construction =================================================


@dataclass(frozen=True)
class TabulateAxes:
    """Row + col Axes for the tabulate() Table, plus per-col-leaf
    `value_kinds` and `formats` (one entry per leaf, in pre-order).

    Calls `Axis.validate()` on both outputs internally, so T6 can trust
    the shapes without re-checking.
    """
    row_axis: Axis
    col_axis: Axis
    value_kinds: tuple[ValueKind, ...]
    formats: tuple[str | None, ...]


def build_tabulate_axes(
    data_result: AggregateResult, spec: TabSpec,
) -> TabulateAxes:
    """Build validated row + col Axes for a tabulate() Table.

    Tree shape per the design memo:

    - **Row axis**: 1-dim → flat data leaves + optional Total leaf.
      2-dim → for each outer cat, a branch containing inner-cat leaves;
      then a sibling Subtotal leaf if `spec.subtotals` includes the
      outer dim; finally a Grand Total leaf (path of all TotalMarkers).
    - **Col axis**: `user cols → _metric → _stat` hierarchy. Each user
      col cat becomes a branch containing metric-branches with stat
      leaves underneath. If `cols=()`, metric branches sit directly
      under root (no user col dim). A Total col branch (TotalMarker)
      is appended when `spec.totals AND spec.cols AND n_rows > 0
      AND n_cols > 0`.

    Leaf pre-order matches T4c's `row_layout` / `col_layout` ordering;
    body indexing relies on this structural invariant.
    """
    n_rows_data = data_result.stat_values.shape[0]
    n_cols_data = data_result.stat_values.shape[1]
    has_total_row = bool(spec.totals and n_rows_data > 0)
    has_total_col = bool(
        spec.totals and spec.cols
        and n_rows_data > 0 and n_cols_data > 0
    )

    row_axis = _build_row_axis(spec, data_result, has_total_row)
    col_axis = _build_col_axis(spec, data_result, has_total_col)

    row_axis.validate()
    col_axis.validate()

    value_kinds, formats = _per_col_leaf_metadata(col_axis)

    return TabulateAxes(
        row_axis=row_axis,
        col_axis=col_axis,
        value_kinds=value_kinds,
        formats=formats,
    )


def _build_row_axis(
    spec: TabSpec, data_result: AggregateResult, has_total_row: bool,
) -> Axis:
    """Multi-dim row tree with optional subtotal/total markers."""
    n_dims = len(spec.rows)

    dims = tuple(
        Dimension(
            name=k, kind="category", categories=cats,
            label=(spec.label or {}).get(k),
        )
        for k, cats in zip(spec.rows, data_result.row_categories)
    )

    top_children: list[Node] = []
    subtotal_dim = spec.subtotals[0] if spec.subtotals else None

    if n_dims == 1:
        for cat in data_result.row_categories[0]:
            top_children.append(
                Node(path=(cat,), depth=1, span=1, role="data")
            )
    else:
        # 2-dim row case (v0.1 cap). Outer-only subtotals.
        outer_cats = data_result.row_categories[0]
        inner_cats = data_result.row_categories[1]
        outer_dim_name = spec.rows[0]
        inner_dim_name = spec.rows[1]
        is_outer_subtotal = subtotal_dim == outer_dim_name

        for outer_cat in outer_cats:
            inner_leaves = tuple(
                Node(path=(outer_cat, inner_cat), depth=2, span=1, role="data")
                for inner_cat in inner_cats
            )
            top_children.append(Node(
                path=(outer_cat,), depth=1,
                span=len(inner_leaves),
                role="data",
                children=inner_leaves,
            ))
            if is_outer_subtotal:
                # Use the category's display label when present (e.g., the
                # synthetic Missing category has value=None, label="Missing";
                # rendering as "None Subtotal" would be wrong).
                outer_display = outer_cat.label or outer_cat.value
                top_children.append(Node(
                    path=(outer_cat, SubtotalMarker(at_dim=inner_dim_name)),
                    depth=2, span=1, role="subtotal",
                    label=f"{outer_display} Subtotal",
                ))

    if has_total_row:
        total_path = tuple(TotalMarker() for _ in range(n_dims))
        top_children.append(Node(
            path=total_path, depth=n_dims, span=1, role="total",
            label="Grand Total" if n_dims > 1 else "Total",
        ))

    root = Node(
        path=(), depth=0,
        span=sum(c.span for c in top_children),
        role="data",
        children=tuple(top_children),
    )
    return Axis(dims=dims, tree=root)


def _build_col_axis(
    spec: TabSpec, data_result: AggregateResult, has_total_col: bool,
) -> Axis:
    """Col tree: user_cols → _metric → _stat with optional Total branch."""
    # Dimensions
    user_dims = tuple(
        Dimension(
            name=k, kind="category", categories=cats,
            label=(spec.label or {}).get(k),
        )
        for k, cats in zip(spec.cols, data_result.col_categories)
    )

    metric_cats = tuple(Category(m) for m in data_result.metric_names)
    metric_dim = Dimension(name="_metric", kind="metric", categories=metric_cats)

    stat_names = tuple(dict.fromkeys(s for _, s in spec.values_spec))
    stat_cats = tuple(Category(s) for s in stat_names)
    stat_dim = Dimension(name="_stat", kind="stat", categories=stat_cats)

    dims = user_dims + (metric_dim, stat_dim)

    # Tree
    top_children: list[Node] = []
    if spec.cols:
        for cat in data_result.col_categories[0]:
            top_children.append(_col_outer_branch(
                outer_path=(cat,), outer_role="data", label=None,
                spec=spec, data_result=data_result,
            ))
        if has_total_col:
            top_children.append(_col_outer_branch(
                outer_path=(TotalMarker(),), outer_role="total",
                label="Total",
                spec=spec, data_result=data_result,
            ))
    else:
        # cols=() → metric branches directly under root
        top_children = _metric_branches(
            parent_path=(), parent_role="data",
            spec=spec, data_result=data_result,
        )

    root = Node(
        path=(), depth=0,
        span=sum(c.span for c in top_children),
        role="data",
        children=tuple(top_children),
    )
    return Axis(dims=dims, tree=root)


def _col_outer_branch(
    outer_path: tuple,
    outer_role: str,
    label: str | None,
    spec: TabSpec,
    data_result: AggregateResult,
) -> Node:
    """One user-col-cat (or Total) branch containing the metric subtree."""
    metric_branches = _metric_branches(
        parent_path=outer_path, parent_role=outer_role,
        spec=spec, data_result=data_result,
    )
    return Node(
        path=outer_path,
        depth=len(outer_path),
        span=sum(b.span for b in metric_branches),
        role=outer_role,
        label=label,
        children=tuple(metric_branches),
    )


def _metric_branches(
    parent_path: tuple,
    parent_role: str,
    spec: TabSpec,
    data_result: AggregateResult,
) -> list[Node]:
    """Per metric (in `data_result.metric_names` order), a branch containing
    that metric's stat leaves (in `spec.values_spec` order)."""
    by_metric: dict[str, list[str]] = {}
    for m, s in spec.values_spec:
        by_metric.setdefault(m, []).append(s)

    branches: list[Node] = []
    for metric_name in data_result.metric_names:
        if metric_name not in by_metric:
            continue
        metric_cat = Category(metric_name)
        stat_leaves = tuple(
            Node(
                path=parent_path + (metric_cat, Category(s)),
                depth=len(parent_path) + 2,
                span=1,
                role=parent_role,
            )
            for s in by_metric[metric_name]
        )
        branches.append(Node(
            path=parent_path + (metric_cat,),
            depth=len(parent_path) + 1,
            span=len(stat_leaves),
            role=parent_role,
            children=stat_leaves,
        ))
    return branches


def _per_col_leaf_metadata(
    col_axis: Axis,
) -> tuple[tuple[ValueKind, ...], tuple[str | None, ...]]:
    """Per col leaf, look up the (value_kind, format) for the stat name
    at the leaf's last path position."""
    value_kinds: list[ValueKind] = []
    formats: list[str | None] = []
    for leaf in col_axis.leaves():
        stat_name = leaf.path[-1].value
        vk, fmt = STAT_DEFAULTS[stat_name]
        value_kinds.append(vk)
        formats.append(fmt)
    return tuple(value_kinds), tuple(formats)


# === T6: public API ========================================================


def tabulate(
    data: Any,
    *,
    rows: str | Sequence[str],
    cols: str | Sequence[str] = (),
    values: Mapping[str, str | Sequence[str]],
    subtotals: str | Sequence[str] | None = None,
    totals: bool = True,
    observed: bool = True,
    dropna: bool = False,
    levels: Mapping[str, Sequence[Any]] | None = None,
    label: Mapping[str, str] | None = None,
    weight: Mapping[str, str] | None = None,
    test: str | None = None,
) -> Table:
    """Multi-dimensional summary table from a pandas or polars DataFrame.

    See TABULATE_API.md for the full v0.1 design. Composes the T1–T5
    internal pipeline; no business logic of its own.

    Args:
        data: A pandas or polars (eager) DataFrame.
        rows: Required. One or two row-dim column names. Single string or
            list/tuple. Mixing forms raises TypeError.
        cols: Zero or one column-dim name. Default `()` (no column dim;
            the col axis has just `_metric` + `_stat`).
        values: Required. `{metric_column: stat_name}` or
            `{metric_column: [stat_name, ...]}`. Stat names from the
            v0.1 set: sum, mean, count, min, max, median.
        subtotals: Optional row-dim name(s) at which to insert subtotal
            rows. Must be a subset of `rows`; the innermost row dim is
            rejected (would tautologically duplicate leaf rows).
        totals: If True (default), include grand total row when row
            leaves exist, and grand total column when `cols` is
            non-empty.
        observed: If True (default), only categories appearing in the
            data become leaves. If False, the full domain must come
            from `levels=`.
        dropna: If True, drop rows with null values in any grouping
            column. If False (default), nulls become a synthetic
            "Missing" category appended last.
        levels: Optional per-key override of category order or domain.
            Required for `observed=False`.
        label: Optional display-name overrides for dim columns.
        weight: RESERVED for weighted statistics in v0.2; raises
            NotImplementedError if non-None.
        test: RESERVED for statistical tests in v0.2; raises
            NotImplementedError if non-None.

    Returns:
        A `Table` with the row Axis built from `rows`, the column Axis
        carrying `_metric` and `_stat` synthetic dims (preceded by the
        user col dim if `cols` is non-empty), the computed body matrix,
        and per-col-leaf value_kinds + formats.

    Raises:
        ValueError: invalid argument combinations (no rows, too many
            row/col dims, duplicate keys, innermost-dim subtotal, etc.).
        TypeError: bad key forms or non-DataFrame input.
        KeyError: a named row/col/metric column is not present in `data`.
        NotImplementedError: `weight=` or `test=` supplied (v0.2).

    Example:
        >>> import pandas as pd
        >>> import proctab as pt
        >>> df = pd.DataFrame({
        ...     "region": ["W", "W", "E", "E"],
        ...     "revenue": [100.0, 80.0, 90.0, 70.0],
        ... })
        >>> table = pt.tabulate(df, rows="region", values={"revenue": "sum"})
        >>> print(table.to_text())  # doctest: +SKIP
    """
    spec = _parse_tabulate_args(
        rows=rows, cols=cols, values=values,
        subtotals=subtotals, totals=totals,
        observed=observed, dropna=dropna,
        levels=levels, label=label,
        weight=weight, test=test,
    )

    # Metrics must be present in the DataFrame too — pre-check via wrap()
    # so a missing metric column surfaces as a clear KeyError before
    # narwhals fails inside the aggregation expression.
    metric_names = tuple(dict.fromkeys(m for m, _ in spec.values_spec))
    required = tuple(spec.rows) + tuple(spec.cols) + metric_names

    nw_df = wrap(data, required_columns=required)

    data_result = aggregate_data_cells(nw_df, spec)
    totals_result = aggregate_totals(nw_df, spec, data_result)
    assembled = assemble_body(data_result, totals_result, spec)
    axes = build_tabulate_axes(data_result, spec)

    return Table(
        row_axis=axes.row_axis,
        col_axis=axes.col_axis,
        body=assembled.body,
        missing=assembled.missing,
        value_kinds=axes.value_kinds,
        formats=axes.formats,
    )
