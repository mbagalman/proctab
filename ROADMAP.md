# Legible Roadmap

Living document. Items get checked off as they ship; tickets get refined inline as design memos lock decisions.

## v0.0.x — Foundations

The bare data model and a renderer that proves it works. No aggregation yet.

- [x] Data containers: `Table`, `Axis`, `Dimension`, `Node`, `Category`, `Marker`, `MissingReason`, `ValueKind`
- [x] Hand-built tables for the four worked examples in [VISION.md](VISION.md) (`src/legible/examples.py`)
- [x] Plain-text renderer (`src/legible/render/text.py`)
- [x] Initial test suite (173 passing — pandas/polars exercised from F3 onward)
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
- [ ] **F5.** Axis construction — given the spec + observed categories, build row/col `Axis`es per the [positional path invariant](TABLE_MODEL.md#node-the-axis-tree)
- [ ] **F6.** Public `freq()` — wire spec parsing → DataFrame wrapping → aggregation → axis construction → `Table` assembly
- [ ] **F7.** Tests against `examples.py` fixtures — pandas + polars inputs both produce the same `Table` shape; numeric values match within float tolerance
- [ ] **F8.** Edge-case tests — empty df, all-null column, 3-key error, `dropna=True/False`, `observed=False` with `levels=`, reserved-kwarg errors

### `tabulate()` — multi-dimensional summary tables

- [ ] Draft design memo: `TABULATE_API.md`
- [ ] Implementation tickets

### HTML renderer

- [ ] Draft design memo: `HTML_RENDERER.md` (single default theme for v0.1)
- [ ] Notebook `_repr_html_` wiring
- [ ] Standalone `.to_html(path)` output

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
