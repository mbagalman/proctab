# Legible Roadmap

Living document. Items get checked off as they ship; tickets get refined inline as design memos lock decisions.

## v0.0.x — Foundations

The bare data model and a renderer that proves it works. No aggregation yet.

- [x] Data containers: `Table`, `Axis`, `Dimension`, `Node`, `Category`, `Marker`, `MissingReason`, `ValueKind`
- [x] Hand-built tables for the four worked examples in [VISION.md](VISION.md) (`src/legible/examples.py`)
- [x] Plain-text renderer (`src/legible/render/text.py`)
- [x] Initial test suite (733 passing — pandas/polars exercised from F3 onward)
- [x] Hardened `Axis.validate()`: full-tree walk; span correctness; `len(path) == depth` consistency; malformed-branch-path detection
- [ ] CI: GitHub Actions running lint + test on Python 3.10–3.14
- [ ] Choose final project name (currently using `legible` as a working name)

## v0.1 — Minimum Lovable Release

First release someone might actually try. Each feature gets a design memo before implementation tickets land here.

### `freq()` — one- and two-way frequency tables

- [x] Lock design memo: [FREQ_API.md](FREQ_API.md)
- [x] **F1.** `FreqSpec` dataclass — internal parsed-args representation
- [x] **F2.** `_parse_freq_args()` — function-args → `FreqSpec` with edge-case validation (key count, mixed-form rejection, reserved kwargs, missing `levels=` when needed)
- [x] **F3.** narwhals integration boilerplate — uniform wrapper around pandas/polars input
- [x] **F4a.** Aggregation kernel: count matrix construction + marginal totals (raw integer counts per cell, marginal sums)
- [x] **F4b.** Aggregation kernel: percentage derivation + `MissingReason` assignment (counts → percent stats; EMPTY for zero-record combinations; divide-by-zero handling)
- [x] **F5.** Axis construction — given the spec + observed categories, build row/col `Axis`es per the [positional path invariant](TABLE_MODEL.md#node-the-axis-tree)
- [x] **F6.** Public `freq()` — wire spec parsing → DataFrame wrapping → aggregation → axis construction → `Table` assembly
- [x] **F7.** Tests against `examples.py` fixtures — pandas + polars inputs both produce the same `Table` shape; numeric values match within float tolerance
- [x] **F8.** Edge-case tests — empty df, all-null column, 3-key error, `dropna=True/False`, `observed=False` with `levels=`, reserved-kwarg errors

### `tabulate()` — multi-dimensional summary tables

- [x] Lock design memo: [TABULATE_API.md](TABULATE_API.md)
- [x] **T1.** `TabSpec` dataclass — internal parsed-args representation (rows, cols, values_spec as ordered `(metric, stat)` tuples, subtotals, totals, observed, dropna, levels, label)
- [x] **T2.** `_parse_tabulate_args()` — validate rows/cols/values shape; normalize `values={"revenue": "sum"}` shorthand to tuple; check stat names against the v0.1 set; check subtotals subset (and reject innermost-dim subtotal); reject reserved kwargs; surface a clear error for `"weighted_mean"`
- [x] **T3.** Stat-function registry — module-level mapping of `{"sum", "mean", "count", "min", "max", "median"}` to NaN-aware narwhals expressions
- [x] **T4a.** Aggregation kernel — data-cell aggregation: `nw_df.group_by(rows + cols).agg(...)` over every requested `(metric, stat)`; materialize into numpy and permute into the final body shape
- [x] **T4b.** Aggregation kernel — subtotals + grand total: additional groupby passes (one per subtotal level + one for grand total) computed FROM SOURCE (not by summing leaf cells; required for non-additive stats like mean/median)
- [x] **T4c.** Aggregation kernel — `MissingReason` assignment using BOTH companion signals (row count per group + non-null count per `(group, metric)`) so `EMPTY` (no source records) is distinguished from `NULL` (records exist but metric all-null). Without this, `sum` on an all-null group looks like a real zero.
- [x] **T5.** Axis construction — multi-dim row tree with subtotal/total marker leaves; multi-dim col tree with sparse `(metric, stat)` leaves under each user col category; calls `Axis.validate()` on output
- [x] **T6.** Public `tabulate()` — wire spec → wrap → aggregate → axes → Table
- [x] **T7.** Integration tests against a new `example_2_tabulate_v01()` fixture (structurally identical to existing `example_2_tabulate` but substituting `mean` for `weighted_mean` on margin; original stays as "future target"); pandas + polars
- [x] **T8.** Edge-case tests — dim caps (3+ rows, 2+ cols), unknown stat name, empty `values`, innermost-dim subtotal, reserved kwargs, empty df, null grouping cols + dropna both ways, `observed=False` + `levels=`, all-null value column (verifies the `NULL` vs `EMPTY` distinction)

### HTML renderer

- [x] Lock design memo: [HTML_RENDERER.md](HTML_RENDERER.md)
- [ ] **H1.** Module skeleton + format-resolution helper. Create `src/legible/render/html.py` with `render_html(table, *, standalone=False) -> str` (stub `<table></table>` for now) and the per-cell format resolver (explicit `formats[j]` → value_kind default → `{:g}` fallback per [Format resolution](HTML_RENDERER.md#format-resolution)).
- [ ] **H2.** Column header rendering. One `<tr>` per col-axis dim depth; interior nodes → `<th colspan="node.span" scope="colgroup">`; innermost leaves → `<th scope="col">`; top-left corner → `<th rowspan="n_header_rows" class="legible-corner" aria-hidden="true">` (no `scope=`). All `legible-` prefixed classes per role.
- [ ] **H3.** Body rendering — single ticket combining row-tree pre-order traversal and per-cell emission. Interior nodes emit a two-cell group-header `<tr>` (label `<th scope="rowgroup">` + colspan-padding `<td>`); leaves emit the full data `<tr>` with row-label `<th scope="row">` plus one `<td>` per col leaf. Cells dispatch on `MissingReason`, apply the format resolver, escape via `html.escape`, and emit `data-value="{format(float(v), '.17g')}"` for finite-PRESENT numerics. Skip `data-value` for non-finite PRESENT or missing cells.
- [ ] **H4.** Caption + tfoot. Emit `<caption class="legible-caption">` from `table.meta.get("title")`; emit `<tfoot>` with one `<tr class="legible-source">` per `source` and one `<tr class="legible-footnote">` per `footnote`. Omit `<caption>` and `<tfoot>` entirely when those keys are absent. HTML-escape all values.
- [ ] **H5.** Default styling. Embedded `<style>` block for standalone mode (font, alignment, borders, total/subtotal emphasis, prefix-scoped selectors like `.legible-cell`, `.legible-total`). Inline equivalents (mirroring the same rules) for fragment mode.
- [ ] **H6.** Standalone wrapper: `<!DOCTYPE>` + `<head>` (charset, `<title>` from `table.meta.get("title")`, embedded style) + `<body>` containing the fragment.
- [ ] **H7.** Wire `Table._repr_html_()` (always fragment) and `Table.to_html(path=None)` (always standalone) to `render_html`. Lazy-import to avoid circular deps. Confirm the `to_html(path=None) → str` / `to_html(path="…") → None` contract; accept `str | os.PathLike[str]` for `path`.
- [ ] **H8.** Tests. Parse output with `html.parser` or `xml.etree` rather than substring-matching. Assertions: `<table>` root; expected `<thead>`/`<tbody>`/`<tfoot>` shape; correct `colspan`/`rowspan`/`scope` per header; `legible-` class hierarchy per role; `data-value` present on finite-PRESENT and absent on missing-or-non-finite; MissingReason display text matches the table. Integration tests render `examples.py` fixtures and parse the result. Edge cases: empty Table, HTML-sensitive content (`<`, `&`, `"`, `'` in labels/titles/footnotes), missing-reason variants, non-finite PRESENT.

### Excel renderer

- [ ] Draft design memo: `EXCEL_RENDERER.md`
- [ ] openpyxl integration
- [ ] Merged header cells, frozen panes, bold totals
- [ ] Numeric cells with Excel format codes (per [TABLE_MODEL.md](TABLE_MODEL.md) renderer obligation)

### Engine-agnostic input

- [ ] narwhals integration in the aggregation pipeline
- [ ] Test matrix: pandas + polars × all aggregation features

### Project plumbing

- [ ] PyPI name reservation (after final name is chosen)
- [ ] User-facing `README.md`
- [ ] License decision (MIT vs Apache 2.0)
- [ ] Documentation site (mkdocs-material likely)
- [ ] DataFrame export: `Table.to_pandas()` / `Table.to_polars()` (long format per [TABLE_MODEL.md#dataframe-export](TABLE_MODEL.md#dataframe-export))

## v0.2 — Statistics and Polish

- [ ] Weighted statistics (`weight=` kwarg on `freq()` and `tabulate()`)
- [ ] Statistical tests: chi-square, Fisher's exact, Cramér's V — landing in `Table.tests` (separate from body)
- [ ] Configurable stat sets (override the v0.1 fixed defaults)
- [ ] Multiple HTML style themes
- [ ] Markdown / LaTeX renderers
- [ ] Sort options (e.g., `sort="n_desc"` for biggest-first)
- [ ] Per-dimension `observed` override
- [ ] Wide-format DataFrame export
- [ ] Cell suppression policies (privacy thresholds; `MissingReason.SUPPRESSED` code is already reserved)
- [ ] Copy-on-write `.with_footnote()` / `.with_title()` etc.

## Parked / Maybe Later

- PDF rendering
- PyArrow / Dask / DuckDB engine support (extends narwhals coverage)
- SAS-syntax-faithful aliases for SAS migrants
- Stacked-stats-in-cell layout (currently sub-columns only)
- Cell-level drill-down (`Table.rows_behind(cell)`)
- Multi-table reports (PROC TABULATE-style)
- Interactive / live tables

## Out of Scope (decided)

- Charts/plots — tables only
- General statistics library — we integrate, never reimplement
- Dashboards — Streamlit / Dash territory
