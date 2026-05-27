# `freq()` — API Design Memo (v0.1)

> Companion to [VISION.md](VISION.md) and [TABLE_MODEL.md](TABLE_MODEL.md). Goal: lock the user-facing argument shape and behavior of `freq()` before writing implementation code. Once locked, the proposed [Implementation Tickets](#implementation-tickets-proposed) migrate to [ROADMAP.md](../ROADMAP.md).

## Scope

What `freq()` does in v0.1:

- One-way frequency table from a single grouping column.
- Two-way crosstab from two grouping columns, with marginal totals on both axes.
- Returns a [`Table`](TABLE_MODEL.md).
- Accepts pandas or polars DataFrames as input (narwhals internally).

What it does NOT do in v0.1 (deferred per [ROADMAP.md](../ROADMAP.md)):

- Three-or-more-way tables — raise a clear error pointing to `tabulate()`.
- Statistical tests (chi-square, Fisher's, Cramér's V). The `test=` kwarg is reserved but raises `NotImplementedError`.
- Weighted frequencies. The `weight=` kwarg is reserved but raises `NotImplementedError`.
- Custom statistic selection (the default set is fixed in v0.1).
- Sort options (default sort is natural category order; biggest-first is v0.2).
- Cell suppression policies.

## Signature

```python
def freq(
    data,                                    # pandas | polars DataFrame
    *keys: str | Sequence[str],              # one or two grouping columns; see "Key forms" below
    totals: bool = True,                     # include marginal totals
    observed: bool = True,                   # see TABLE_MODEL.md#axis-completion-policy
    dropna: bool = False,                    # if True, drop grouping nulls; if False, treat as Missing category
    levels: dict[str, list] | None = None,   # override per-dim category domain (paired with observed=False)
    label: dict[str, str] | None = None,     # display-name overrides for dim columns
    weight: str | None = None,               # RESERVED (v0.2) — raises NotImplementedError
    test: str | None = None,                 # RESERVED (v0.2) — raises NotImplementedError
) -> Table:
```

The `*keys: str | Sequence[str]` annotation is approximate — what matters is the runtime validation, which normalizes any accepted form to an internal `tuple[str, ...]`.

### Key forms (all accepted)

```python
pt.freq(df, "region")                              # one-way, single positional
pt.freq(df, ["region"])                            # one-way, list
pt.freq(df, "region", "product_line")              # two-way, positional
pt.freq(df, ["region", "product_line"])            # two-way, list
```

**Rejected** (mixed forms — raise `TypeError`):

```python
pt.freq(df, ["region"], "product_line")            # error: mix list and positional
pt.freq(df, "region", ["product_line"])            # error: mix list and positional
```

### What it returns

A `Table` whose:
- `row_axis` has one dim — the first key.
- `col_axis` has one dim (`_stat`) for one-way, two dims (second key + `_stat`) for two-way.
- `body` holds counts and percentages as floats.
- `value_kinds` / `formats` set per-col-leaf (N → count, percent stats → percent).

The exact shape is identical to the hand-built fixtures in [`examples.py`](../src/proctab/examples.py) — see [Worked Examples](#worked-examples) below.

## Default Statistic Set

**One-way:** four columns under the `_stat` dim — `N`, `Pct`, `CumN`, `CumPct`.

**Two-way:** four columns under the `_stat` dim per (row × col) cell — `N`, `Row%`, `Col%`, `Tot%`. Marginal Total column and Total row show the same four stats for consistency (some values will be tautological 100%; see [Open Questions](#open-questions)).

Customization of the stat set is parked to v0.2.

## Defaults and Overrides

| Behavior | Default | Override | Notes |
|----------|---------|----------|-------|
| Marginal totals | included | `totals=False` | One-way: drop Total row. Two-way: drop Total row AND Total col. |
| Observed categories only | yes | `observed=False` | Global in v0.1; per-dim override deferred to v0.2 |
| Null grouping values | "Missing" category | `dropna=True` | Per [TABLE_MODEL.md null policy](TABLE_MODEL.md#null-handling-policy-v01) |
| Category domain | inferred from data | `levels={"region": ["W","E","S","N"]}` | Required when `observed=False` and no Categorical/Enum dtype |
| Display labels for dims | column name | `label={"region": "Sales Region"}` | Used by HTML/Excel renderers |

## Null Handling

Direct application of the policy in [TABLE_MODEL.md#null-handling-policy-v01](TABLE_MODEL.md#null-handling-policy-v01):

- Null in a grouping column → synthetic `Category(value=None, label="Missing")` appended to the dim.
- The "Missing" category sorts last among data categories, before any `TotalMarker`.
- `dropna=True` removes the Missing category and its records entirely.
- Cells in `(region, product_line)` combinations with zero source rows still get `MissingReason.EMPTY` (separate concept from null grouping values).

## `observed=True/False`

Per-dim flag on [`Dimension`](../src/proctab/model.py); in v0.1, the function kwarg applies it globally to all dims.

- `observed=True` (default) — only categories that appear in source data become leaves.
- `observed=False` — full domain from `levels=` argument (if provided) or from a pandas `Categorical` / polars `Enum` dtype's defined values. Categories with no source rows produce leaves with `MissingReason.EMPTY` cells.

Per-dim override (e.g., `observed=False` on the column key only) is parked to v0.2 — it needs a richer API surface (per-key options mapping).

## Worked Examples

### Example 1 — one-way

```python
df = pd.DataFrame({"region": ["W","W","E","E","E","S","N"]})
pt.freq(df, "region")
```

Returns the structure of [`examples.example_1_one_way_freq`](../src/proctab/examples.py):

- `row_axis`: `region` with 4 data categories + Total row (5 row leaves)
- `col_axis`: `_stat` with N / Pct / CumN / CumPct (4 col leaves)
- `body` shape `(5, 4)`

### Example 1b — two-way crosstab

```python
df = pd.DataFrame({"region": [...], "product_line": [...]})
pt.freq(df, "region", "product_line")
```

Returns the structure of [`examples.example_1b_two_way_freq`](../src/proctab/examples.py):

- `row_axis`: `region` with 3 data categories + Total row (4 row leaves)
- `col_axis`: `product_line` (2 cats + TotalMarker) × `_stat` (N / Row% / Col% / Tot%) → 12 col leaves
- `body` shape `(4, 12)`

These two cases plus their `totals=False`, `observed=False`, and `dropna=True` variants are the v0.1 acceptance test surface.

## Edge-Case Behavior (v0.1)

- **Three-or-more keys** → `ValueError("freq() supports one- or two-way tables only in v0.1; use tabulate() for higher-dimensional aggregations.")`
- **Empty DataFrame** → empty `Table` (zero leaves, empty body), not an error.
- **Single-row DataFrame** → works normally.
- **Grouping column doesn't exist** → `KeyError` with the column name.
- **Grouping column is all-null + `dropna=True`** → empty `Table`.
- **Grouping column is all-null + `dropna=False`** → `Table` with a single "Missing" category row (and Total row if `totals=True`).
- **`observed=False` without `levels=` and dtype is not Categorical/Enum** → `ValueError` asking for `levels=` to be provided.
- **`weight=` provided** → `NotImplementedError("weight= is reserved for weighted frequencies in v0.2 and is not implemented in v0.1.")`
- **`test=` provided** → `NotImplementedError("test= is reserved for statistical tests (chi-square, Fisher's, Cramér's V) in v0.2 and is not implemented in v0.1.")`

## Recommended Decisions

1. **Positional `*keys` over `by=` keyword.** Matches the VISION sketch; reads naturally for the common case (`freq(df, "region")` vs. `freq(df, by="region")`). **Confidence: high.**
2. **Reject 3+ keys with a clear error pointing to `tabulate()`.** Avoids unclear semantics for what a 3D crosstab even renders as. **Confidence: high.**
3. **Default stats are fixed in v0.1.** Stat customization adds real design surface (aliases? user-defined stat functions? validity per dim type?). Park to v0.2. **Confidence: high.**
4. **`totals=True` default.** Matches SAS, matches user expectation for executive tables. **Confidence: high.**
5. **`dropna=False` default — nulls become "Missing" category.** Surfaces data quality issues instead of silently hiding them. **Confidence: high.**
6. **Reserve `weight=` and `test=` kwargs now, raise NotImplementedError.** v0.2 signature becomes a strict addition. Avoids users discovering kwarg surprises when v0.2 ships. **Confidence: high.**
7. **`observed=True` default with global kwarg in v0.1; per-dim override to v0.2.** Per-dim needs a key-to-options mapping API that's not worth solving now. The v0.2 shape will likely be `observed={"region": True, "quarter": False}` — a dict mirroring `levels=` / `label=`. **Confidence: medium — flag. Compromise noted:** the common business pattern (per [TABLE_MODEL.md#axis-completion-policy](TABLE_MODEL.md#axis-completion-policy)) is `observed=False` on columns + `observed=True` on rows; users who need that combination in v0.1 will have to drop to `tabulate()` or accept the global setting.

## Open Questions

1. **Accept a list as the keys form** (`pt.freq(df, ["region", "product_line"])`)? The VISION.md sketch showed this; the positional form is cleaner. Allowing both adds branching to input parsing but matches user intuition (people pass lists). **Recommend: allow both** — single-element list → one-way; two-element list → two-way; reject mixed positional+list as a `TypeError`.
2. **Two-way Total column stats — all four or just N + Tot%?** Including all four produces tautological 100% values in Col% and Row% for the Total column (and in Row%/Tot% for the Total row). SAS includes them all and that's what the hand-built example does. **Recommend: all four for consistency**, with documented note that some are trivially 100%.
3. **`label` dict — dim renames only, or also category renames?** Dim renames (`label={"region": "Sales Region"}`) are the common case. Category renames (`label={"region.West": "Western Region"}`) are useful but increase the dict's surface area. **Recommend: dim-only in v0.1**, category renames in v0.2 via a richer `formats=` / `categories=` API.
4. **narwhals public type for `data` annotation.** Need to confirm — likely `nw.typing.IntoFrame`. Verify when implementing.
5. **What does `freq(df)` with no keys do?** Probably `ValueError`. Could plausibly mean "frequency of every column" but that's a multi-table output we don't have a return type for. **Recommend: ValueError requiring at least one key.**

## Implementation Tickets (proposed)

These migrate to [ROADMAP.md](../ROADMAP.md#freq--one--and-two-way-frequency-tables) once this memo is locked. Each is one well-bounded coding session.

1. **`FreqSpec` dataclass.** Internal representation of parsed user args (keys, totals, observed, dropna, levels, label, weight, test). All validation lives here.
2. **`_parse_freq_args()`.** Function-args-to-`FreqSpec` parser with edge-case validation (key count, reserved kwargs, missing `levels=` when needed).
3. **narwhals integration boilerplate.** Wrapping pandas/polars input into a uniform interface; testing both engines with the same fixture data.
4. **Aggregation kernel.** Given a `FreqSpec` and a wrapped DataFrame, produce the numeric body + missing matrix. The meat of the implementation — kept as one ticket because the sub-parts share state, but conceptually two pieces, in this order:
    - **4a.** Count matrix construction + marginal totals (raw integer counts per cell, marginal sums).
    - **4b.** Percentage derivation + `MissingReason` assignment (turn counts into percent stats per cell; flag EMPTY for zero-record combinations).

    Most of the subtle bugs in this feature will live in 4b — percent-of-which-base disagreements, divide-by-zero on empty rows/cols, etc.
5. **Axis construction.** Given the spec + observed categories, build row and col `Axis`es (with categories, trees, markers, subtotal/total nodes per the [positional path invariant](TABLE_MODEL.md#node-the-axis-tree)).
6. **Public `freq()`.** Wire spec parsing → DataFrame wrapping → aggregation → axis construction → `Table` assembly.
7. **Tests against `examples.py` fixtures.** Pandas and polars inputs both produce the same Table shape; numeric values match within float tolerance.
8. **Edge-case tests.** Empty df, all-null column, 3-key error, `dropna=True/False`, `observed=False` with `levels=`, reserved-kwarg errors.

The order matters: tickets 1–2 are pure-Python and testable without engines; 3 is engine plumbing; 4–6 are the implementation core; 7–8 validate against the locked reference.

## Out of Scope (this memo)

- `tabulate()` design — its own memo.
- Renderer changes — none needed; freq() returns a `Table` that the existing renderers handle.
- DataFrame export changes — Table-level concern, not freq-specific.
