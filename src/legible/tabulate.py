"""`tabulate()` — multi-dimensional summary tables. See TABULATE_API.md for design.

Currently exposes (internal pipeline; public `tabulate()` arrives in T6):
- `SUPPORTED_STATS`: the v0.1 stat name set.
- `STAT_EXPRS` (T3): stat name → narwhals expression callable.
- `TabSpec` (T1): parsed-and-validated arg representation.
- `_parse_tabulate_args()` (T2): user args → TabSpec.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import narwhals.stable.v1 as nw
import numpy as np

from legible._categories import is_null, normalize, resolve_categories
from legible.model import Category


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
    cols_t = _normalize_dim_list(cols, arg_name="cols",
                                 min_count=0, max_count=1)

    overlap = set(rows_t) & set(cols_t)
    if overlap:
        raise ValueError(
            f"tabulate() rows and cols cannot share dims; got overlap: "
            f"{sorted(overlap)}."
        )

    values_spec = _normalize_values(values)
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

    aggs: list[nw.Expr] = [nw.len().alias("__rowcount__")]
    for metric in metric_names:
        aggs.append(nw.col(metric).count().alias(f"__nnc__{metric}"))
    for idx, (metric, stat) in enumerate(values_spec):
        aggs.append(STAT_EXPRS[stat](metric).alias(f"__sv__{idx}"))

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

        row_count[r, c] = row["__rowcount__"]
        for metric in metric_names:
            nonnull_count[r, c, metric_idx_map[metric]] = row[f"__nnc__{metric}"]

        for idx, (metric, stat) in enumerate(values_spec):
            v = row[f"__sv__{idx}"]
            stat_values[r, c, idx] = 0.0 if is_null(v) else float(v)

    return stat_values, row_count, nonnull_count


def _product(xs: list[int]) -> int:
    p = 1
    for x in xs:
        p *= x
    return p


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

    Sections are computed per the TABULATE_API conditions:
    - `subtotals_data_cols[dim]` for each `dim in spec.subtotals` (and
      `n_rows > 0`)
    - `subtotals_total_col[dim]` additionally when a Total col exists
    - `grand_row` when `spec.totals` and `n_rows > 0`
    - `grand_col` and `grand_cell` when `spec.totals` and a Total col exists
    """
    if spec.dropna:
        nw_df = nw_df.drop_nulls(subset=list(spec.rows + spec.cols))

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
