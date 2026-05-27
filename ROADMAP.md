# proctab Roadmap

Living document. Items get checked off as they ship; tickets get refined inline as design memos lock decisions.

## v0.0.x — Foundations

The bare data model and a renderer that proves it works. No aggregation yet.

- [x] Data containers: `Table`, `Axis`, `Dimension`, `Node`, `Category`, `Marker`, `MissingReason`, `ValueKind`
- [x] Hand-built tables for the four worked examples in [VISION.md](docs/VISION.md) (`src/proctab/examples.py`)
- [x] Plain-text renderer (`src/proctab/render/text.py`)
- [x] Initial test suite (733 passing — pandas/polars exercised from F3 onward)
- [x] Hardened `Axis.validate()`: full-tree walk; span correctness; `len(path) == depth` consistency; malformed-branch-path detection
- [ ] CI: GitHub Actions running lint + test on Python 3.10–3.14
- [x] Choose final project name — locked: `proctab`

## v0.1 — Minimum Lovable Release

First release someone might actually try. Each feature gets a design memo before implementation tickets land here.

### `freq()` — one- and two-way frequency tables

- [x] Lock design memo: [FREQ_API.md](docs/FREQ_API.md)
- [x] **F1.** `FreqSpec` dataclass — internal parsed-args representation
- [x] **F2.** `_parse_freq_args()` — function-args → `FreqSpec` with edge-case validation (key count, mixed-form rejection, reserved kwargs, missing `levels=` when needed)
- [x] **F3.** narwhals integration boilerplate — uniform wrapper around pandas/polars input
- [x] **F4a.** Aggregation kernel: count matrix construction + marginal totals (raw integer counts per cell, marginal sums)
- [x] **F4b.** Aggregation kernel: percentage derivation + `MissingReason` assignment (counts → percent stats; EMPTY for zero-record combinations; divide-by-zero handling)
- [x] **F5.** Axis construction — given the spec + observed categories, build row/col `Axis`es per the [positional path invariant](docs/TABLE_MODEL.md#node-the-axis-tree)
- [x] **F6.** Public `freq()` — wire spec parsing → DataFrame wrapping → aggregation → axis construction → `Table` assembly
- [x] **F7.** Tests against `examples.py` fixtures — pandas + polars inputs both produce the same `Table` shape; numeric values match within float tolerance
- [x] **F8.** Edge-case tests — empty df, all-null column, 3-key error, `dropna=True/False`, `observed=False` with `levels=`, reserved-kwarg errors

### `tabulate()` — multi-dimensional summary tables

- [x] Lock design memo: [TABULATE_API.md](docs/TABULATE_API.md)
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
- [x] **T9.** Guard against synthetic-dim name collisions: `_parse_tabulate_args` must reject any user column named `_metric` or `_stat` with a clear error (these are reserved as internal col-axis dim names per [TABULATE_API.md](docs/TABULATE_API.md)). Add unit tests in `tests/test_tabulate_spec.py`.

### HTML renderer

- [x] Lock design memo: [HTML_RENDERER.md](docs/HTML_RENDERER.md)
- [x] **H1.** Module skeleton + format-resolution helper. Create `src/proctab/render/html.py` with `render_html(table, *, standalone=False) -> str` (stub `<table></table>` for now) and the per-cell format resolver (explicit `formats[j]` → value_kind default → `{:g}` fallback per [Format resolution](docs/HTML_RENDERER.md#format-resolution)).
- [x] **H2.** Column header rendering. One `<tr>` per col-axis dim depth; interior nodes → `<th colspan="node.span" scope="colgroup">`; innermost leaves → `<th scope="col">`; top-left corner → `<th rowspan="n_header_rows" class="proctab-corner" aria-hidden="true">` (no `scope=`). All `proctab-` prefixed classes per role.
- [x] **H3.** Body rendering — single ticket combining row-tree pre-order traversal and per-cell emission. Interior nodes emit a two-cell group-header `<tr>` (label `<th scope="rowgroup">` + colspan-padding `<td>`); leaves emit the full data `<tr>` with row-label `<th scope="row">` plus one `<td>` per col leaf. Cells dispatch on `MissingReason`, apply the format resolver, escape via `html.escape`, and emit `data-value="{format(float(v), '.17g')}"` for finite-PRESENT numerics. Skip `data-value` for non-finite PRESENT or missing cells.
- [x] **H4.** Caption + tfoot. Emit `<caption class="proctab-caption">` from `table.meta.get("title")`; emit `<tfoot>` with one `<tr class="proctab-source">` per `source` and one `<tr class="proctab-footnote">` per `footnote`. Omit `<caption>` and `<tfoot>` entirely when those keys are absent. HTML-escape all values.
- [x] **H5.** Default styling. Embedded `<style>` block for standalone mode (font, alignment, borders, total/subtotal emphasis, prefix-scoped selectors like `.proctab-cell`, `.proctab-total`). Inline equivalents (mirroring the same rules) for fragment mode.
- [x] **H6.** Standalone wrapper: `<!DOCTYPE>` + `<head>` (charset, `<title>` from `table.meta.get("title")`, embedded style) + `<body>` containing the fragment.
- [x] **H7.** Wire `Table._repr_html_()` (always fragment) and `Table.to_html(path=None)` (always standalone) to `render_html`. Lazy-import to avoid circular deps. Confirm the `to_html(path=None) → str` / `to_html(path="…") → None` contract; accept `str | os.PathLike[str]` for `path`.
- [x] **H8.** Tests. Parse output with `html.parser` or `xml.etree` rather than substring-matching. Assertions: `<table>` root; expected `<thead>`/`<tbody>`/`<tfoot>` shape; correct `colspan`/`rowspan`/`scope` per header; `proctab-` class hierarchy per role; `data-value` present on finite-PRESENT and absent on missing-or-non-finite; MissingReason display text matches the table. Integration tests render `examples.py` fixtures and parse the result. Edge cases: empty Table, HTML-sensitive content (`<`, `&`, `"`, `'` in labels/titles/footnotes), missing-reason variants, non-finite PRESENT.

### Excel renderer

- [x] Lock design memo: [EXCEL_RENDERER.md](docs/EXCEL_RENDERER.md)
- [x] **E1.** Module skeleton + format-resolution helper. Create `src/proctab/render/excel.py` with `render_excel(table, path, *, sheet="Sheet1") -> None` stub and the per-cell format resolver `_resolve_excel_format(fmt, value_kind)` implementing the full priority chain (translate known `formats[j]` patterns → per-`value_kind` default → `"General"`). Add `_validate_sheet_name(name)`. Add `[project.optional-dependencies] excel = ["openpyxl>=3.1"]` to `pyproject.toml`.
- [x] **E2.** Column header rendering. Compute the row-position variables (`header_start`, `body_start`, `last_body_col`) once and emit rows `header_start..header_start + H - 1`, with merged cells for interior nodes spanning multiple leaves. Top-left corner blank. Per-role classes drive per-cell styling later.
- [x] **E3.** Body rendering — single ticket combining row-tree pre-order and per-cell emission. Interior nodes emit group-header rows (label only, body cols blank); leaves emit row-label + body cells. Cells dispatch on `MissingReason` and apply the format resolver from E1.
- [ ] **E4.** Title + source + footnotes. Title at row 1 merged `A1:{last_body_col}1` (bold, font +2); spacer row 2. Source row at `body_end + 2` merged `A..{last_body_col}` with thin top border and wrap enabled; footnote rows from `body_end + 3` same merging + wrap, smaller font, no top border (only the first carries the separator). All optional based on `meta.get(...)`. Uses the row-position variables from E2.
- [ ] **E5.** Default styling — openpyxl `Font` / `Border` / `Alignment` objects per the role/missing rules; single source-of-truth dict mapping role → style, analogous to HTML's `_STYLE_BY_CLASS`.
- [ ] **E6.** Frozen pane + column widths + sheet name validation. Set `worksheet.freeze_panes = f"B{body_start}"`; col A width from longest label (capped at 40); body cols default 12. Validate `sheet=` per Excel's rules (1–31 chars, no `\ / ? * [ ] :`); raise `ValueError` on violation.
- [ ] **E7.** Wire `Table.to_excel(path, *, sheet="Sheet1")` to `render_excel`. Lazy-import inside the method; raise `ImportError("Excel export requires openpyxl. Install with `pip install proctab[excel]`.")` when openpyxl is absent.
- [ ] **E8.** Tests. Reopen the written `.xlsx` via openpyxl and walk cells: title + style; column header values + merged ranges + bottom border; per-cell number formats matching the kind / translation tables; total-row bold + medium top border; total-col medium left border; subtotal italic; freeze pane; sheet name; source/footnote cell positions, merged ranges, wrap; MissingReason text mapping; sheet-name validation errors; missing-openpyxl `ImportError` path. Integration tests render `examples.py` fixtures and reopen the workbooks. Edge cases: empty Table, no title, no source/footnotes, invalid sheet name.

### Engine-agnostic input

- [ ] narwhals integration in the aggregation pipeline
- [ ] Test matrix: pandas + polars × all aggregation features

### Project plumbing

- [ ] PyPI name reservation (after final name is chosen)
- [ ] User-facing `README.md`
- [ ] License decision (MIT vs Apache 2.0)
- [ ] Expand `pyproject.toml` metadata before first PyPI release: `readme = "README.md"`, `license`, `keywords`, `classifiers`, `urls` (Homepage, Repository, Issues). Some entries depend on the name + license decisions.
- [ ] Documentation site (mkdocs-material likely)
- [x] DataFrame export: `Table.to_pandas()` / `Table.to_polars()` (long format per [TABLE_MODEL.md#dataframe-export](docs/TABLE_MODEL.md#dataframe-export))

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
- [ ] `values=` ergonomic shorthands for `tabulate()`: accept `values="revenue"` (bare string → `{"revenue": ["sum"]}`), and consider tuple-list form `values=[("revenue", "sum"), ...]` (the latter is already a deferred Open Question in [TABULATE_API.md](docs/TABULATE_API.md#open-questions)).
- [ ] Optional groupby-result caching in `tabulate()` — multiple groupby passes (data + per-subtotal + grand total) can be expensive on very wide / very deep tables. Investigate reuse without losing the "compute from source" correctness guarantee for non-additive stats.

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
