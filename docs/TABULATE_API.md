# `tabulate()` — API Design Memo (v0.1)

> Companion to [VISION.md](VISION.md), [TABLE_MODEL.md](TABLE_MODEL.md),
> and [FREQ_API.md](FREQ_API.md). Goal: lock the user-facing argument
> shape and behavior of `tabulate()` before writing implementation
> code. Once locked, the proposed [Implementation Tickets](#implementation-tickets-proposed)
> migrate to [ROADMAP.md](../ROADMAP.md).

## Scope

What `tabulate()` does in v0.1:

- Multi-dimensional summary tables with nested row and column dimensions.
- 1–2 row dims, 0–1 column dim (cap for v0.1; lifted in v0.2).
- Multiple statistics per value column (`sum`, `mean`, `count`, `min`,
  `max`, `median`).
- Subtotals at user-specified row-dim levels.
- Grand total row and column.
- Sparse column-axis leaves: only requested `(metric, stat)` combinations
  produce leaves; the col tree is not a full Cartesian product.
- Returns a [`Table`](TABLE_MODEL.md).
- Accepts pandas or polars (eager) DataFrames as input.

What it does NOT do in v0.1 (deferred per [ROADMAP.md](../ROADMAP.md)):

- Three-or-more row or column dims — raises `ValueError` pointing to v0.2.
- Weighted statistics — `weight=` reserved, raises `NotImplementedError`.
- Statistical tests — `test=` reserved, raises `NotImplementedError`.
- Custom statistic functions or aliases — the v0.1 stat name set is fixed.
- Column-axis subtotals — wide-table layout decisions deserve their own
  design pass.
- Per-dim `observed` override — v0.1 is a single global flag, like `freq()`.
- Stacked-stats-in-cell layout — sub-columns only, per
  [TABLE_MODEL.md](TABLE_MODEL.md).

## Signature

```python
def tabulate(
    data,                                         # pandas | polars DataFrame
    *,
    rows: str | Sequence[str],                    # required, 1–2 dim names
    cols: str | Sequence[str] = (),               # 0–1 dim names
    values: Mapping[str, str | Sequence[str]],    # required, {metric: stat | [stat, ...]}
    subtotals: str | Sequence[str] | None = None, # row dim(s) to subtotal at
    totals: bool = True,                          # grand total row always; total col only when cols is non-empty
    observed: bool = True,                        # see TABLE_MODEL axis policy
    dropna: bool = False,                         # drop nulls in grouping cols
    levels: Mapping[str, Sequence[Any]] | None = None,
    label: Mapping[str, str] | None = None,
    weight: Mapping[str, str] | None = None,      # RESERVED (v0.2)
    test: str | None = None,                      # RESERVED (v0.2)
) -> Table:
```

All arguments after `data` are keyword-only. `rows` and `values` are
required; the rest have defaults.

### Argument shapes

```python
# One row dim, one col dim, one metric, one stat
pt.tabulate(df, rows="region", cols="quarter", values={"revenue": "sum"})

# Equivalent — list form for the stat
pt.tabulate(df, rows="region", cols="quarter", values={"revenue": ["sum"]})

# Two row dims, no col dim — pure row-grouped sums
pt.tabulate(df, rows=["region", "product"], values={"revenue": ["sum", "mean"]})

# Two row dims, one col dim, multiple stats per metric, subtotals + totals
pt.tabulate(
    df,
    rows=["region", "product"],
    cols="quarter",
    values={"revenue": ["sum", "mean"], "margin": ["mean"]},
    subtotals="region",
    totals=True,
)
```

`rows` and `cols` accept either a single string or a list/tuple. Mixing
forms in one argument raises `TypeError` (matching `freq()`'s convention).

### What it returns

A `Table` whose:
- `row_axis.dims` is the row-dim list (length 1 or 2).
- `col_axis.dims` is `cols` followed by `_metric` and `_stat` synthetic
  dims (so 2–3 dims for v0.1: at most 1 user col + 2 synthetic).
- `body` holds the computed statistic values.
- `value_kinds` / `formats` set per-col-leaf based on the requested
  `(metric, stat)` combination.

### Ordering contract for `values=`

Output column order is part of the v0.1 product, not an implementation
detail. The mapping `values={metric: [stat, ...]}` defines the order
as follows:

- **Metric order** = the mapping's insertion order (Python 3.7+
  dicts preserve insertion order; this is the user-visible contract).
- **Stat order within a metric** = the user's list order.
- **Column hierarchy is `user cols → _metric → _stat`; `_stat` is
  the innermost dimension.** So the flat leaf sequence under each
  user-col category is:
  `(metric₀, stat₀,₀), (metric₀, stat₀,₁), …, (metric₁, stat₁,₀), …`

This rules out interleaved metric-stat layouts (e.g., revenue-sum,
margin-mean, revenue-mean) — see Open Question 5.

## Stat Set (v0.1)

`values` accepts the following stat names (case-sensitive):

| Stat       | Computation                                       | NaN handling           | Default format |
|------------|---------------------------------------------------|------------------------|----------------|
| `sum`      | Sum of values                                     | Nulls skipped          | `"{:,.0f}"`    |
| `mean`     | Arithmetic mean                                   | Nulls skipped (num + denom) | `"{:,.2f}"` |
| `count`    | Count of non-null values                          | Counts non-null only   | `"{:,.0f}"`    |
| `min`      | Minimum                                           | Nulls skipped          | `"{:,.0f}"`    |
| `max`      | Maximum                                           | Nulls skipped          | `"{:,.0f}"`    |
| `median`   | Median (50th percentile)                          | Nulls skipped          | `"{:,.2f}"`    |

Default formats are starting points; the user can override per-cell-leaf
in a later API enhancement (v0.2).

Unrecognized stat names raise `ValueError` listing the v0.1 set.
`"weighted_mean"` specifically raises `NotImplementedError` referencing
the `weight=` kwarg planned for v0.2.

## Subtotals

`subtotals` names the row dim(s) at whose level breaks a subtotal row is
inserted.

```python
rows=["region", "product"]

subtotals=None              # no subtotals (only grand total if totals=True)
subtotals="region"          # subtotal row at each region break — consolidates
                            # all products within that region
subtotals=["region"]        # same as above (single-element list)
```

Mechanics: a subtotal at dim `i` collapses dims `i+1..n`. So for
`rows=["region", "product"]`, `subtotals="region"` produces a "West
Subtotal" row that aggregates across all products within West. Path:
`(Category("West"), SubtotalMarker(at_dim="product"))` — matches
[TABLE_MODEL.md](TABLE_MODEL.md#node-the-axis-tree)'s positional invariant.

Validation:
- `subtotals` names must all appear in `rows`. Otherwise `ValueError`.
- Subtotals at the innermost row dim are tautological (each leaf row
  IS already that dim's value); v0.1 raises `ValueError`. Warnings would
  silently no-op in notebooks and batch reports, which is a poor way to
  teach the API.

Col-axis subtotals are not supported in v0.1.

## Defaults and Overrides

| Behavior                       | Default          | Override                              | Notes                                                  |
|--------------------------------|------------------|---------------------------------------|--------------------------------------------------------|
| Grand total row                | included         | `totals=False`                        | Added when `totals=True` AND there is at least one row leaf (data-driven or via `levels=`); suppressed for fully-empty row axis |
| Grand total column             | included iff `cols` non-empty | `totals=False`           | Suppressed when `cols=()` (no synthetic "All" col); also suppressed when no col leaves exist |
| Row-dim subtotals              | none             | `subtotals="region"` (etc.)           | Per-axis; col subtotals are v0.2                       |
| Observed categories only       | yes              | `observed=False`                      | Global; per-dim is v0.2                                |
| Null grouping values           | "Missing" category | `dropna=True`                       | Per [TABLE_MODEL null policy](TABLE_MODEL.md#null-handling-policy-v01) |
| Null measured values           | skipped per stat | n/a in v0.1                           | Numeric nulls handled by NaN-aware stat impls          |
| Category domain                | inferred         | `levels={"region": [...]}`            | Required for `observed=False`                          |
| Display labels for dims        | column name      | `label={"region": "Sales Region"}`    | Used by HTML / Excel renderers                         |

## Null Handling

Same policy as [FREQ_API.md null handling](FREQ_API.md#null-handling) for
grouping columns:

- Null in a row/col grouping column → synthetic `Category(value=None,
  label="Missing")` appended to that dim (unless `dropna=True`).
- The same logic applies whether categories come from observed data or
  from `levels=`.

For VALUE columns (the metrics being aggregated):

- Numeric nulls are skipped by the stat (matches pandas / SQL default).
- A cell whose stat receives only null values gets
  `MissingReason.NULL`.
- A cell where no source records contributed (zero-row group) gets
  `MissingReason.EMPTY` — same convention as `freq()`.

## `observed=True/False`

Same as [FREQ_API observed](FREQ_API.md#observedtruefalse): global flag in
v0.1, applies to all grouping dims. `observed=False` requires `levels=`
for every key without a Categorical/Enum dtype (which v0.1 doesn't yet
auto-detect).

## Worked Examples

### Example A — pure row-grouped sums (no col dim)

```python
pt.tabulate(
    df, rows="region",
    values={"revenue": ["sum", "mean"]},
)
```

- `row_axis.dims = (region,)`
- `col_axis.dims = (_metric, _stat)`
- Col leaves: `(revenue, sum)`, `(revenue, mean)`
- Body shape: `(n_regions + 1, 2)` with `totals=True`

### Example B — single row dim, single col dim, single stat

```python
pt.tabulate(
    df, rows="region", cols="quarter",
    values={"revenue": ["sum"]},
)
```

- `row_axis.dims = (region,)`
- `col_axis.dims = (quarter, _metric, _stat)`
- Col leaves: 1 per quarter × 1 metric × 1 stat = n_quarters
- Body shape: `(n_regions + 1, (n_quarters + 1) * 1)` with `totals=True`

### Example C — the full Example 2 from VISION

The hand-built [example_2_tabulate](src/proctab/examples.py) fixture
shows the target structure for:

```python
pt.tabulate(
    df,
    rows=["region", "product"],
    cols="quarter",
    values={"revenue": ["sum", "mean"], "margin": ["mean"]},  # was "weighted_mean" in VISION; weighted is v0.2
    subtotals="region",
    totals=True,
)
```

- `row_axis.dims = (region, product)` with nested West/East branches +
  per-region subtotal leaves + Grand Total leaf.
- `col_axis.dims = (quarter, _metric, _stat)` with **sparse** leaves:
  under each quarter, Revenue spans 2 stats (Sum, Mean) and Margin
  spans 1 (Mean). No `(Revenue, …other)` or `(Margin, …other)` slots.
- Body shape: `(2 regions × 2 products + 2 subtotals + 1 grand total,
  4 quarters × 3 stat-leaves + 1 Total col × 3) = (7, 15)`.

**On the fixture:** the existing [example_2_tabulate](src/proctab/examples.py)
uses `weighted_mean`, which v0.1 doesn't support. Don't mutate that
fixture — keep it as the "future target" the VISION promised. The
tabulate integration tests (T7) will use a separate v0.1-clean
fixture (e.g., `example_2_tabulate_v01()`) that's structurally the
same but substitutes `mean` for the margin stat.

## Edge-Case Behavior (v0.1)

- **Three-or-more row dims** → `ValueError("tabulate() supports 1–2 row
  dims in v0.1; got N. v0.2 will lift this cap.")`
- **Two-or-more col dims** → similar `ValueError`.
- **No rows** (`rows=()`) → `ValueError("tabulate() requires at least one
  row dim.")`.
- **No values** (`values={}` or omitted) → `ValueError("tabulate()
  requires at least one metric in values=.")`.
- **Empty stat list for a metric** (`{"revenue": []}`) → `ValueError`.
- **Unknown stat name** → `ValueError` listing supported stats.
- **`"weighted_mean"` requested** → `NotImplementedError` referencing
  v0.2 `weight=` kwarg.
- **`subtotals` names a dim not in `rows`** → `ValueError`.
- **`subtotals` names the innermost row dim** → `ValueError`:

      subtotals='product' is the innermost row dim and would duplicate
      leaf rows. Use a non-innermost dim (e.g., 'region') or omit
      subtotals.
- **Value column doesn't exist** → `KeyError`.
- **Value column is non-numeric and a numeric stat is requested** →
  engine-level error surfaces (we don't pre-validate dtype in v0.1).
- **Empty DataFrame** → empty `Table` (no leaves, body shape with
  appropriate zero dims). Grand total row / col are suppressed because
  there's nothing to total.
- **Empty data + `observed=False` + `levels=`** → row axis has the
  user-supplied category leaves (each with all-`EMPTY` cells); grand
  total row is included because row leaves exist (the leaves came from
  `levels=`, not from observed data).
- **`weight=` or `test=` supplied** → `NotImplementedError` with v0.2
  references (mirroring `freq()`).

## Recommended Decisions

1. **Keyword-only args after `data`.** `tabulate()` has more args than
   `freq()`; keyword forces clarity at the call site. Matches the VISION
   sketch. **Confidence: high.**
2. **`rows` and `values` are required (no defaults).** Anything else has
   defaults. Pythonic required-keyword-only signature. **Confidence: high.**
3. **v0.1 dim caps: 1–2 rows, 0–1 cols.** Matches Example 2's shape.
   Lifting to N requires renderer / Excel-cell-merging design that's
   bigger than v0.1 scope. **Confidence: high — explicit v0.2 promise.**
4. **v0.1 stat set: sum / mean / count / min / max / median.** Covers
   ~90% of executive-table needs. NaN-aware semantics match pandas / SQL
   defaults. **Confidence: high.**
5. **`subtotals=None` default.** Subtotals are useful but visually heavy;
   require explicit opt-in. **Confidence: high.**
6. **Subtotals named at the innermost row dim → `ValueError`.** Silent
   no-ops get lost in notebooks / batch reports; a clear error teaches
   the API faster. (Reviewer call; I initially leaned lenient — the
   warning-driven alternative has the wrong failure mode for a library
   that aims to produce trustworthy executive output.) **Confidence: high.**
7. **Col-axis subtotals deferred to v0.2.** Wide tables with col
   subtotals get visually messy; deserves its own design pass.
   **Confidence: high.**
8. **Col-axis layout fixed for v0.1: `user_cols → _metric → _stat`.**
   Layout customization (e.g., stat outermost) is v0.2. **Confidence: high.**
9. **Reserve `weight=` and `test=` kwargs now; raise NotImplementedError.**
   Same pattern as `freq()`. **Confidence: high.**
10. **`"weighted_mean"` as a stat NAME raises NotImplementedError.** The
    VISION's `"weighted_mean(weight=units)"` string-spec is not the v0.1
    API; users requesting weighted stats are told to wait for v0.2's
    `weight=` kwarg. **Confidence: high.**

## Open Questions

1. **Per-cell format override API.** Should v0.1 accept
   `formats={("revenue", "sum"): "${:,.0f}"}` for per-(metric, stat)
   formatting? Or keep v0.1 with built-in defaults only and add
   customization in v0.2? **Recommend: defaults only in v0.1.**
2. ~~**Inner-dim subtotal: warn or raise?**~~ Resolved: raise. See
   Recommended Decision 6.
3. **`count` semantics — count of non-null in the value column, or
   count of rows in the group?** Pandas `.count()` is non-null-only;
   `.size()` is row count. For tabulate, count of non-null values is
   more useful (it's a per-stat count, not a per-group count).
   **Recommend: non-null only — matches pandas `.count()`.**
4. ~~**Empty `cols=()` behavior — synthesize an "All" col group?**~~
   Resolved: no synthesis. See the [Defaults and Overrides](#defaults-and-overrides)
   table — when `cols=()`, the grand total column is suppressed too.
5. **Should `values=` accept a list of `(metric, stat)` tuples** as an
   alternative to the dict form, for more explicit ordering when the
   user wants metrics interleaved? E.g.,
   `values=[("revenue", "sum"), ("margin", "mean"), ("revenue", "mean")]`.
   **Recommend: dict form only in v0.1; tuple-list form deferred.**

## Implementation Tickets (proposed)

These migrate to [ROADMAP.md](../ROADMAP.md) once this memo is locked.

1. **`TabSpec` dataclass.** Internal parsed-args representation (rows,
   cols, values_spec [as ordered list of (metric, stat) pairs after
   parsing], subtotals, totals, observed, dropna, levels, label).
2. **`_parse_tabulate_args()`.** Validate rows/cols/values shape and
   stat names; normalize key forms; check subtotals subset; reject
   reserved kwargs; surface a clear error for `"weighted_mean"`.
   Also normalize each `values[metric]` entry: accept a bare string
   (`{"revenue": "sum"}`) or a list/tuple of strings
   (`{"revenue": ["sum", "mean"]}`); store internally as a tuple of
   stat names. Reject any other type with `TypeError`. Note that
   `isinstance(stat, Sequence)` would match a string — same str-first
   check pattern as `freq()`'s key parser.
3. **Stat-function registry.** Module-level dict mapping
   `{"sum": <impl>, "mean": <impl>, ...}` to narwhals expressions. v0.1
   uses NaN-aware variants.
4. **Aggregation kernel.**
   - **T4a.** Data-cell aggregation: build the narwhals `group_by(rows + cols)`
     + `.agg(...)` expression for every requested `(metric, stat)`;
     materialize into a `(n_row_groups × n_col_groups, n_stat_leaves)`
     numpy block; then permute into the final body shape.
   - **T4b.** Subtotals + grand total: additional groupby passes (one
     per subtotal level + one for grand total) computed FROM SOURCE
     (not by summing leaf cells — required for correctness on
     non-additive stats like mean/median).
   - **T4c.** MissingReason assignment per the [TABLE_MODEL null
     policy](TABLE_MODEL.md#null-handling-policy-v01). Crucially, to
     distinguish `EMPTY` from `NULL` per cell, the kernel needs TWO
     companion signals from the aggregation pass, computed for every
     group regardless of which stats were requested:
     - **row count per group** (`nw.len()` in the agg) — if 0, the cell
       gets `EMPTY` (no source records contributed).
     - **non-null count per `(group, metric)`** (`nw.col(metric).count()`
       for each metric in `values`) — if 0 but row count > 0, the cell
       gets `NULL` (records existed but the metric was all-null).

     Without both signals, `sum` on an all-null group looks like a real
     zero (pandas / polars return 0 by default with `skipna=True`), and
     we cannot tell EMPTY from NULL from a legitimate-but-zero result.
     This is the most subtle implementation risk in tabulate's kernel.

     Per-cell priority (after both signals are computed):
     1. row_count == 0 → `EMPTY`
     2. nonnull_count[metric] == 0 → `NULL`
     3. stat-specific div-by-zero (e.g., mean with effective n == 0) →
        `NOT_APPLICABLE`
     4. otherwise → `PRESENT`
5. **Axis construction (`build_tabulate_axes`).** Multi-dim row tree
   with subtotal/total marker leaves; multi-dim col tree with sparse
   `(metric, stat)` leaves under each user col category; honors
   `spec.label` for Dimension display names. Calls `Axis.validate()`
   on output.
6. **Public `tabulate()`.** Wire spec → wrap → aggregate → axes → Table.
7. **Integration tests against a v0.1-clean fixture.** Add a new
   `example_2_tabulate_v01()` to `examples.py` (structurally identical
   to `example_2_tabulate` but with `mean` substituted for
   `weighted_mean` on margin). The original fixture stays as the
   "future target." Tests run on pandas + polars.
8. **Edge-case tests.** Cap violations (3+ rows, 2+ cols), unknown
   stat name, empty values, subtotals-not-in-rows, reserved kwargs,
   empty df, null grouping cols + dropna both ways, observed=False +
   levels=, all-null value column.

The order matters: T1–T2 are pure Python + testable in isolation; T3 is
shared infrastructure; T4 is the math (split into 4a/4b/4c because most
subtle bugs will live in T4b's subtotal computation — non-additive
stats require fresh source aggregations); T5–T6 wire the structure;
T7–T8 validate against the locked references.

## Out of Scope (this memo)

- `freq()` — its own memo ([FREQ_API.md](FREQ_API.md)) and complete.
- Renderer **model** changes — none needed; `tabulate()` returns a
  `Table` that satisfies the existing renderer contract. (Renderer
  *polish* — e.g., the text renderer's column-width behavior on 15+
  cols — is a separate renderer-side concern and not blocked by
  tabulate.)
- DataFrame export — Table-level concern, not tabulate-specific.
- Custom stat function registration — v0.2.
- Multi-stat layout customization (stat-outermost, etc.) — v0.2.
