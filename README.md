# proctab

> **Status: pre-alpha - not usable yet. Please do not install or
> depend on this code.** No public release, no PyPI package, no
> stable API. The repo is open so the design work can happen in
> public, not because the library is ready for users.

## What this aims to be

The go-to Python library for producing executive-ready summary
tables and categorical crosstabs from business data - the kind of
output an analyst hands to a leadership team without further
formatting. Built on the modern Python data stack (pandas +
polars via [narwhals](https://narwhals-dev.github.io/narwhals/)).

The two headline functions:

- **`freq(df, "region")`** - one-way frequencies; `freq(df,
  "region", "product")` for two-way crosstabs. Counts,
  percentages, marginal totals.
- **`tabulate(df, rows=..., cols=..., values=...)`** -
  multi-dimensional summary tables: any combination of group
  columns on rows and columns, multiple metrics with multiple
  statistics per metric, subtotals at arbitrary levels, grand
  totals. The output is structured, not a pile of nested
  `DataFrame.groupby()` calls.

Both produce a `Table` object that knows its own structure
(axes, subtotals, missing-value reasons, formatting hints) and
can render itself to plain text, HTML (for notebooks /
standalone pages), or Excel. See [docs/VISION.md](docs/VISION.md)
for the full positioning.

## Current status

The project is being built design-memo-first: every public
surface gets a locked spec before any code lands.

**Locked design memos** (in [docs/](docs/)):

- [VISION.md](docs/VISION.md) - positioning, target user, design
  principles, v0.1 scope.
- [TABLE_MODEL.md](docs/TABLE_MODEL.md) - the data model (`Table`,
  `Axis`, `Dimension`, `Node`, `MissingReason`, etc.) and the
  renderer contract every renderer must honor.
- [FREQ_API.md](docs/FREQ_API.md) - `freq()` v0.1 API.
- [TABULATE_API.md](docs/TABULATE_API.md) - `tabulate()` v0.1 API.
- [HTML_RENDERER.md](docs/HTML_RENDERER.md) - HTML renderer v0.1
  design.
- [EXCEL_RENDERER.md](docs/EXCEL_RENDERER.md) - Excel renderer v0.1
  design.

**Implemented**:

- Data containers + plain-text renderer.
- `freq()` end to end (one-way and two-way), pandas + polars.
- `tabulate()` end to end (multi-dim rows/cols, multi-metric,
  subtotals, grand totals), pandas + polars.
- HTML renderer, Excel renderer, and long-format DataFrame export.
- 1172 tests passing.

**Next**:

- Public-release packaging, docs polish, and the remaining v0.1
  roadmap items.

The living checklist of everything shipped and pending lives in
[ROADMAP.md](ROADMAP.md).

## How to follow along

Watch the repo. There are no release notifications to subscribe
to yet because there are no releases. Issues are not yet being
triaged from the public - this is still single-author design
work.

If you came across this looking for a Python summary-table or
crosstab library and want something usable *now*,
[pandas crosstab / pivot_table](https://pandas.pydata.org/docs/reference/api/pandas.crosstab.html),
[great_tables](https://posit-dev.github.io/great-tables/), and
[itables](https://mwouts.github.io/itables/) are all worth a look.

## License

MIT - see [LICENSE](LICENSE).
