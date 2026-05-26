"""`tabulate()` — multi-dimensional summary tables. See TABULATE_API.md for design.

Currently exposes (internal pipeline; public `tabulate()` arrives in T6):
- `SUPPORTED_STATS`: the v0.1 stat name set.
- `TabSpec` (T1): parsed-and-validated arg representation.
- `_parse_tabulate_args()` (T2): user args → TabSpec.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


SUPPORTED_STATS: frozenset[str] = frozenset({
    "sum", "mean", "count", "min", "max", "median",
})


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
