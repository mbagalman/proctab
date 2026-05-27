# Table Object — Data Model

> Working design memo. Goal: lock down the in-memory representation of the table object that `freq()` and `tabulate()` produce, before writing the prototype. Renderers, DataFrame export, and the public API all depend on getting this right.

## Goals

- Represent **any** table the worked examples in [VISION.md](VISION.md) require — including multi-level row/column nesting, multi-statistic cells, subtotals at arbitrary levels, and grand totals.
- Be **renderer-agnostic** — the same object must produce styled HTML and styled Excel without special-casing.
- Be **engine-agnostic** — no pandas `MultiIndex`, no polars `Expr`, no scipy types stored in the object. Pure Python + numpy for numerics.
- Be **inspectable and exportable** — `print(table)` is useful in a REPL, `_repr_html_` works in a notebook, and long-format DataFrame export preserves enough metadata for inspection, testing, and reconstruction *when the auxiliary metadata travels alongside*. Full lossless round-trip through a single flat DataFrame is **not** a goal — trees, spans, formats, and footnotes don't naturally fit in flat tabular form.

## Non-goals (for this memo)

- The user-facing argument shape of `freq()` / `tabulate()`. That's the next memo. This one is about what those functions *produce*.
- Renderer internals (HTML/Excel styling decisions).
- Performance tuning.

## The Core Insight

**Rows, columns, and statistics are all the same kind of thing: dimensions.**

This is what makes SAS `PROC TABULATE` so expressive. The user picks which dimensions go on the row axis and which on the column axis; the statistic-being-shown is itself a dimension that can be placed on either axis. Once you accept this, the data model simplifies dramatically.

A table is:
- An ordered list of **row dimensions** (nested left-to-right).
- An ordered list of **column dimensions** (nested top-to-bottom).
- A **body**: numeric values, one per (row-leaf × column-leaf) intersection.
- A bit of **metadata** (labels, formats, footnotes, titles).

Everything else — subtotals, totals, multi-stat columns, weighted statistics — is expressible as nodes in axis trees.

## The `Table` Object

```
Table
├── row_axis:      Axis             # ordered hierarchy of row dimensions + leaf tree
├── col_axis:      Axis             # ordered hierarchy of column dimensions + leaf tree
├── body:          np.ndarray       # 2D float, shape = (n_row_leaves, n_col_leaves)
├── missing:       np.ndarray       # 2D uint8, MissingReason code per cell (0 = present)
├── value_kinds:   list[ValueKind]  # one per column-leaf — currency/percent/count/etc.
├── formats:       list[str|None]   # per-column-leaf format string (overrides value_kind default)
├── labels:        dict             # display-name overrides for dim names & categories
├── meta:          dict             # title, subtitle, footnotes, source note, caption
└── _spec:         AggregationSpec  # retained for re-execution / drill-down / debugging
```

### `MissingReason` (v0.1 codes)

| Code | Name           | Meaning                                                              | Default render |
|------|----------------|----------------------------------------------------------------------|----------------|
| 0    | PRESENT        | Cell has a real value in `body[i, j]`                                | the value      |
| 1    | EMPTY          | No source records contributed to this cell                           | blank          |
| 2    | NOT_APPLICABLE | Statistic is undefined for this group (e.g. weighted mean with zero weight) | "—"     |
| 3    | SUPPRESSED     | Cell is hidden by policy (privacy threshold, etc.) — code reserved; suppression policies land in v0.2 | "***"          |
| 4    | NULL           | Explicit null encountered in source data                             | "·"            |

Renderers consult `missing` to choose the right output per their style.

### Null Handling Policy (v0.1)

The `NULL` missing code covers one specific case. Three related situations get different treatment:

| Situation | v0.1 behavior |
|-----------|---------------|
| Null in a **grouping column** | Treated as a real category. A synthetic `Category(value=None, label="Missing")` is added to the dimension; renderers display it in a distinct style. Label is user-overridable. |
| Null in a **measured value**, alongside non-nulls | Skipped by the stat (matches pandas / SQL default): `sum` ignores nulls, `mean` excludes them from numerator and denominator, `count` counts only non-null. The cell holds the stat over non-null values; `missing[i,j] = PRESENT`. |
| **All measured values null** within a group | The stat has no valid input; `missing[i,j] = NULL`. |
| Group has **no source rows at all** | `missing[i,j] = EMPTY`. |

This policy is deliberately simple in v0.1. Overrides (propagate-nulls-aggressively, treat grouping nulls as their own dim, suppress the "Missing" category, etc.) land in later versions.

### `ValueKind`

A semantic tag (`count`, `currency`, `percent`, `ratio`, `mean`, `weighted_mean`, `median`, `raw`, ...) that lets renderers pick a sensible default format if `formats[j]` is None, and attach a units/symbol when relevant. The user can override with an explicit format string per column-leaf.

### `Axis`

```
Axis
├── dims:        list[Dimension]
└── tree:        Node             # root of the (possibly sparse) leaf tree
```

The tree is built from each dimension's categories plus any subtotal/total nodes inserted at construction time. Which categories become leaves at each level is governed by a per-`Dimension` `observed` policy (see [Axis Completion Policy](#axis-completion-policy) below). Once leaf categories at each level are fixed, the cross-product becomes leaf nodes in the tree; combinations with no source records get `MissingReason.EMPTY` in `body`. (Combinations the user has explicitly excluded — e.g., via a filter — are pruned and don't appear at all.)

#### Axis Completion Policy

Each `Dimension` carries an `observed` flag that determines which of its categories become leaves at that level:

- **`observed=True`** (default) — only categories present in the source data become leaves. Categories the user knows exist but that have no rows are not in the tree at all.
- **`observed=False`** — the dimension's full known domain becomes leaves. The domain comes from either a user-supplied `levels=[...]` argument or, when reading from pandas/polars, a `Categorical`/`Enum` dtype's defined values. Categories with no source rows still get leaf nodes; their cells are EMPTY.

For business reporting, the common pattern is `observed=False` on the column axis (always show all 4 quarters even if Q4 had no data) and `observed=True` on the row axis. The default is `observed=True` because (a) the alternative requires a source of truth for the dim's domain that we can't always determine, and (b) for high-cardinality columns the Cartesian explosion can be large.

The exact API surface for setting `observed` (per-dim argument, per-axis shortcut, global default) is the next memo's problem; this memo reserves the field on `Dimension`.

### `Dimension`

```
Dimension
├── name:        str              # column name in source data, or "_metric" / "_stat"
├── kind:        Literal["category", "metric", "stat"]
├── categories:  list[Category]   # ordered values for this dim (data-sourced or synthetic)
├── observed:    bool             # see Axis Completion Policy; default True
└── label:       str|None         # display name (defaults to .name)
```

A `Dimension` is a clean semantic descriptor — *what this dim is*. It deliberately knows nothing about subtotal/total markers, which are presentation/structural decisions that live in the axis tree. This lets the same `Dimension` describe `region` whether the resulting table has subtotals or not.

`kind`:
- `category` — a real grouping variable from the source data (region, quarter, product_line)
- `metric` — which value column is being summarized (revenue, margin)
- `stat` — which aggregation function (sum, mean, weighted_mean, count)

The `_metric` and `_stat` dimensions are *synthesized*; they don't exist in the source DataFrame but are treated identically to user-supplied dimensions by the renderer.

### `Category`

```
Category
├── value:       Any              # the actual data value (e.g. "West", 2025, "Revenue")
└── label:       str|None         # display name override
```

A `Category` is a value belonging to a dimension. For `kind="category"` dimensions, the `value` is a real value from the source DataFrame (e.g., `"West"`, `2025`). For `kind="metric"` dimensions, `value` is a metric name (e.g., `"revenue"`). For `kind="stat"` dimensions, it's a stat identifier (e.g., `"sum"`, `"weighted_mean"`). Categories are *not* markers — subtotal and total positions are structural and live in the axis tree as `Marker` path elements.

### `Marker`

A sentinel type used in `Node.path` to represent subtotal/total positions where a real `Category` would otherwise live. Two flavors: `SubtotalMarker(at_dim=...)` and `TotalMarker()`. Renderers branch on `node.role`, not on path content, so they rarely need to inspect markers directly.

### `Node` (the axis tree)

A `Node` is a position in a row or column header tree. The tree is the place where presentation structure — including subtotal and total markers — lives.

```
Node
├── path:        tuple[Category|Marker, ...]   # path from root to this node
├── depth:       int                            # which dim level this node lives at
├── span:        int                            # leaf count beneath this node — for header cell-merging
├── role:        Literal["data", "subtotal", "total"]
├── label:       str|None                       # display name override (e.g. "West Subtotal")
└── children:    list[Node] | None              # None for leaves
```

`role`:
- `data` — represents a real category value (path element is a `Category`)
- `subtotal` — represents a roll-up at this dim level (path element is a `SubtotalMarker`)
- `total` — represents the grand total (path element is a `TotalMarker`)

**Invariant — leaf paths align positionally with `axis.dims`:** for any leaf node `n`, `len(n.path) == len(axis.dims)`. Position `i` is one of:

- a `Category` drawn from `axis.dims[i].categories`,
- a `SubtotalMarker(at_dim=axis.dims[i].name)` — represents a roll-up consolidating this dim level (and, conventionally, all inner positions), or
- a `TotalMarker()` — represents the grand-total roll-up.

For a 2-dim row axis `[region, product]`:

- Data row "West / Widget A": `path = (Category("West"), Category("Widget A"))`
- Region-level subtotal "West Subtotal": `path = (Category("West"), SubtotalMarker(at_dim="product"))`
- Grand Total: `path = (TotalMarker(), TotalMarker())`

This positional invariant makes DataFrame export trivial: each path position maps to its dimension's column without special-case logic — a `Category` becomes the value; a `Marker` becomes null in that column, with `_row_role` / `_col_role` indicating *why* it's null.

Interior (non-leaf) nodes have `len(n.path) == n.depth` — the path goes only as deep as the node lives.

**`depth` is semantic (dim level), not tree position.** A subtotal or total leaf may sit at a tree position shallower than its `depth`. For example, in a `[region, product]` row axis with subtotals at the region level, the `West Subtotal` leaf is a *sibling* of the `West` branch (both direct children of root, tree position 1) but has `depth=2` because its path is `(Category("West"), SubtotalMarker(at_dim="product"))`. The tree intentionally collapses intermediate levels for subtotal/total leaves; renderers walk the tree in pre-order and use `node.depth` for indentation regardless of tree shape.

Leaf nodes — `node.children is None` — define the rows of `body` (in left-to-right pre-order traversal of the row tree) and the columns of `body` (in pre-order of the col tree).

## How Each VISION Example Maps

### Example 1 — `pt.freq(df, "region")`

```
row_axis.dims:   [ Dimension(name="region", kind="category",
                             categories=[West, East, South, North]) ]
row_axis.tree:   Node(children=[
                     Node(role="data",  path=(West,)),
                     Node(role="data",  path=(East,)),
                     Node(role="data",  path=(South,)),
                     Node(role="data",  path=(North,)),
                     Node(role="total", path=(TotalMarker(),), label="Total"),
                 ])

col_axis.dims:   [ Dimension(name="_stat", kind="stat",
                             categories=[N, Pct, CumN, CumPct]) ]
col_axis.tree:   Node(children=[Node(role="data", path=(N,)), ...])

body:    shape (5, 4)
missing: shape (5, 4), all zeros (PRESENT)
```

Note: the `region` dimension's `categories` list does **not** contain "Total" — the Total node lives only in the axis tree.

### Example 1b — `pt.freq(df, ["region", "product_line"])`

Same shape, but the col axis now has two dimensions (`product_line`, then `_stat` with 4 entries: N / RowPct / ColPct / TotalPct). Each col leaf is at depth 2. Marginal total nodes appear in *both* trees; renderers emit merged "Product A" headers spanning four sub-columns.

> **Design choice:** stats as sub-columns rather than SAS-style stats-stacked-inside-cells. The default is sub-columns (modern convention, simpler renderers); stacked-in-cell is deferred indefinitely — it complicates Excel, accessibility, sorting, and export.

### Example 2 — the full tabulate

```python
pt.tabulate(
    df, rows=["region","product"], cols=["quarter"],
    values={"revenue":["sum","mean"], "margin":["weighted_mean(weight=units)"]},
    subtotals="region", totals=True,
)
```

```
row_axis.dims:
    Dimension(name="region",  kind="category", categories=[West, East])
    Dimension(name="product", kind="category", categories=[Widget_A, Widget_B])

row_axis.tree:
    West (data)
    ├── Widget A (data)         ← leaf row 0
    ├── Widget B (data)         ← leaf row 1
    West Subtotal (subtotal)    ← leaf row 2
    East (data)
    ├── Widget A (data)         ← leaf row 3
    ├── Widget B (data)         ← leaf row 4
    East Subtotal (subtotal)    ← leaf row 5
    Grand Total (total)         ← leaf row 6

col_axis.dims:
    Dimension(name="quarter", kind="category", categories=[Q1, Q2, Q3, Q4])
    Dimension(name="_metric", kind="metric",   categories=[Revenue, Margin])
    Dimension(name="_stat",   kind="stat",     categories=[Sum, Mean, WeightedMean])

col_axis.tree (SPARSE — only requested (metric,stat) combos become leaves):
    Q1
    ├── Revenue
    │   ├── Sum                 ← leaf col 0
    │   └── Mean                ← leaf col 1
    └── Margin
        └── WeightedMean        ← leaf col 2
    Q2  (same shape, leaf cols 3–5)
    Q3  (leaf cols 6–8)
    Q4  (leaf cols 9–11)

body:    shape (7, 12)
missing: shape (7, 12)
```

Two things to note:

1. **The col tree is sparse.** Leaves exist only for explicitly-requested `(metric, stat)` combinations — `(Revenue, WeightedMean)` and `(Margin, Sum)` never appear. Span counts reflect actual leaves: under each quarter, `Revenue` spans 2 and `Margin` spans 1. The renderer naturally emits "Revenue" merged across two sub-columns and "Margin" as a single sub-column. No special-case conjoint dim.

2. **Subtotal/Total nodes carry `role`.** The `region` Dimension's `categories` is just `[West, East]` — subtotals and the grand total are *tree* concepts, not category values. Reusing the `region` Dimension in a different table with no subtotals would produce a different tree with the same Dimension instance.

## Subtotals & Totals: Tree Nodes, Materialized in `body`

Two independent decisions, both deliberate:

**Where they live (semantics):** subtotal and total positions live exclusively in `Axis.tree`, as `Node`s with `role="subtotal"` or `role="total"` and `Marker` path elements. They do **not** live in `Dimension.categories`. Dimensions remain clean semantic descriptors.

**How they're computed (representation):** they are eagerly materialized — real rows/columns in `body`, computed by a separate groupby pass against the source data, not by summing leaf cells.

The combination buys:
- Renderers don't need aggregation logic.
- Non-additive stats (median, weighted mean, percent-of-X) are correct by construction — subtotals are computed *from the source*, not from displayed cell values.
- DataFrame export emits subtotal/total cells with appropriate role flags.
- Cell-level formats apply uniformly regardless of role.
- The same `Dimension` is reusable across tables with different subtotal placements.

**Cost:** ~2× memory for tables with subtotals at every level. Acceptable — these tables are by definition small (executive-readable).

## Renderer Contract

A renderer receives a `Table` and must be able to do its job using only:

- `table.row_axis.tree` — walk to emit row headers with spans / indentation
- `table.col_axis.tree` — walk to emit column headers with spans
- `table.body[i, j]` — fetch numeric values, in row/column leaf order
- `table.missing[i, j]` — branch on MissingReason code to render blank / "—" / "***" / etc.
- `table.value_kinds[j]` — sensible default format when `formats[j]` is None; attach units/symbols
- `table.formats[j]` — explicit per-column-leaf format override
- `table.labels`, `table.meta` — display names, title, footnotes, source note
- `node.role` — role-specific styling (bold totals, indented subtotals)

No renderer ever touches the source DataFrame, the aggregation spec, or any DataFrame engine. This is what keeps HTML and Excel honest with each other.

**Renderer obligation — numeric cells stay numeric.** The Excel renderer MUST write each cell as a native numeric value with an Excel number format applied via cell style — never as a pre-formatted string. This keeps the workbook usable downstream (sort, re-aggregate, pivot, paste-special). The `formats[j]` string is translated into the equivalent Excel format code; the underlying cell value remains the float from `body[i, j]`. The HTML renderer follows the same principle (numeric `data-value` attribute alongside the formatted display text), though the cost of getting it wrong there is lower.

## DataFrame Export

```python
table.to_pandas()  # → long-format DataFrame
```

Columns:

| Column                     | Contents                                                       |
|----------------------------|----------------------------------------------------------------|
| one per row dimension      | category value, or null if this row is a subtotal/total at that dim |
| one per column dimension   | category value, or null if this column is a subtotal/total at that dim |
| `value`                    | numeric cell value (null if missing)                           |
| `missing_reason`           | `None \| "empty" \| "not_applicable" \| "suppressed" \| "null"` |
| `_row_role`                | `"data" \| "subtotal" \| "total"` (role of this row's leaf node) |
| `_col_role`                | `"data" \| "subtotal" \| "total"` (role of this column's leaf node) |
| `_row_leaf_id`             | stable integer id from row tree's leaf ordering                |
| `_col_leaf_id`             | stable integer id from col tree's leaf ordering                |

**Two role columns are required.** A cell at the intersection of a subtotal row and a total column has `_row_role="subtotal"` and `_col_role="total"` — collapsing them would lose information.

The leaf ids exist primarily for test fixtures and renderer debugging; normal users will ignore them.

This is intentionally long-format. Wide-format export adds complexity around column naming for nested headers; deferred to v0.2.

`to_polars()` produces the same shape via narwhals.

## Aggregation Pipeline

```
user DataFrame  ─┐
                 ├─→ narwhals wrap → groupby/agg per requested leaf → numpy block → Table(...)
spec from API ──┘
```

Subtotals and totals are computed as additional groupby passes against the source data (not by summing leaf cells), so they're correct for non-additive statistics. Cells with no source records get a `missing` code of `EMPTY`; cells where the requested stat is undefined for the available data get `NOT_APPLICABLE`.

## Recommended Decisions

1. **Subtotal/total semantics live on `Node`, not in `Dimension.categories`.** Keeps Dimension a clean semantic descriptor; same Dimension is reusable across tables with different subtotal layouts. **Confidence: high.**
2. **Subtotals/totals materialized in `body` as real cells, computed eagerly from source data.** Buys renderer simplicity and correctness for non-additive stats. **Confidence: high.**
3. **Axis trees are sparse — only requested (metric × stat) combinations become leaves.** Avoids the conjoint `_metric_stat` hack; renderers get nice nested headers for free. **Confidence: high.**
4. **Custom dimension/node tree, not pandas `MultiIndex`.** Required for engine-agnosticism; enables stats-as-dimension. **Confidence: high.**
5. **Eager aggregation — `Table` is a snapshot, not a query.** Retain the spec for debugging. Reconsider for v1.0 if drill-down becomes a headline feature. **Confidence: medium.**
6. **Body stored as a single 2D numpy float array; per-column-leaf `value_kinds` and `formats` handle presentation diversity.** Cheap, fast. **Confidence: high.**
7. **Missing-reason model (5 codes) over a single bool mask.** Marginal cost, large interpretive payoff. Suppression code is reserved now; suppression policies arrive in v0.2. **Confidence: high.**
8. **Two role columns (`_row_role`, `_col_role`) in DataFrame export, with stable leaf ids.** No ambiguity at subtotal × total intersections. **Confidence: high.**
9. **Default: stats as sub-columns; stacked-in-cell deferred indefinitely.** Complicates Excel, accessibility, sorting, and export. **Confidence: high.**
10. **Immutable-ish `Table`: `.with_footnote(...)` returns a new instance, but internal arrays are shared (copy-on-write for the body).** Avoids paying O(cells) memory cost for tiny metadata edits. **Confidence: high.**
11. **Per-`Dimension` `observed` policy (default `True`) controls which categories become leaves.** Cross-product over leaf categories produces cell positions; absent combinations become `EMPTY`. Lets users opt into "always show all 4 quarters" without forcing it everywhere. **Confidence: high.**
12. **`Node.path` is positionally aligned with `axis.dims` for every leaf.** Subtotal/total positions are filled by `Marker` sentinels. Makes export logic trivial and removes special-cases from renderers. **Confidence: high.**
13. **v0.1 null policy:** grouping nulls become a real `Category(value=None, label="Missing")`; measured-value nulls are skipped per stat default; only all-null-after-skipping groups get `MissingReason.NULL`. **Confidence: high.**
14. **Excel renderer obligation — numeric cells stay numeric, formatting via cell style.** Pre-formatted strings break downstream reuse; this is a hard requirement, not a preference. **Confidence: high.**

## Open Questions

1. **Default `value_kind` inference.** When the user calls `pt.tabulate(values={"revenue": "sum"})`, what `ValueKind` attaches to the resulting column? `currency` heuristic from column name? `raw` by default with optional user override? Probably **`raw` by default**, with a user-supplied dtype/kind dict and (later) optional heuristics.
2. **Significance test surface.** When v0.2 adds chi-square etc., we agreed on a separate `.tests` attribute. Open: do tests get their own renderer-contract entry (footnote block, side panel) or do they render via `meta.footnotes`? Probably their own entry — they have structure (statistic, df, p-value, effect size) that footnotes don't.
3. **`__repr__` vs `_repr_html_`.** Both, no real conflict — noting that the model already supports both.

## Next Step

If the above holds up, the work order is:

1. Lock the design or revise based on further pushback.
2. Implement `Table` / `Axis` / `Dimension` / `Node` / `Category` / `Marker` / `MissingReason` / `ValueKind` as pure data containers — no aggregation, no rendering yet. ~1 day.
3. Hand-construct a `Table` for each of the 5 VISION examples (no `freq()` / `tabulate()` yet) + a plain-text renderer. This proves the model works before we wire up aggregation. **If hand-building Example 2 is annoying, the model is wrong — listen to that and revise before continuing.**
4. Minimal `freq()` (one-way and two-way only) producing a real `Table` from a DataFrame. Iterate against the VISION examples.
5. Minimal `tabulate()`. Same loop.
6. HTML renderer.
7. Excel renderer.

Steps 2–3 are the cheapest way to discover whether the data model is actually right.
