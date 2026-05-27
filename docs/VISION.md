# Vision & API Sketch

## Vision

A Python library for producing executive-ready summary tables and categorical crosstabs from business data in a single, declarative call — and rendering them as polished Excel **and** HTML from the same table object.

Inspired by the ergonomics of SAS `PROC TABULATE` and `PROC FREQ`, designed for Python-native data scientists who currently spend more time on pandas pivot-table origami and Excel formatting than on the analysis itself.

## The Problem

A data scientist asked to produce a "simple" management table — say, *revenue by region and product line, with row-percent-of-total, subtotals at the region level, a weighted average margin, formatted nicely, exported to Excel with merged header cells and bolded totals* — today writes something like this (pandas shown; polars equivalent is shorter but no less manual):

```python
pivot = df.pivot_table(values='revenue', index=['region','product'],
                      columns='quarter', aggfunc='sum', margins=True)
pct = pivot.div(pivot.sum(axis=1), axis=0)
# ... 30+ more lines of pandas + openpyxl/xlsxwriter for formatting ...
```

Then they do it again, slightly differently, for the next report. And again. The output is never quite presentation-quality without manual Excel cleanup.

Existing tools each solve a slice:

| Tool | Strength | Gap |
|------|----------|-----|
| `pandas.pivot_table` / `crosstab` | Universal, flexible | Verbose; no polished output; no significance tests; subtotals awkward |
| `sidetable` | Quick `.stb.freq()` frequency tables | Single-purpose; no Excel; no multi-stat tables |
| `great_tables` (Posit) | Beautiful HTML/PDF rendering | Display-only — you bring your own aggregations |
| `tableone` | Polished biomedical "Table 1" | Narrow domain; not general crosstab |
| `pingouin` / `researchpy` | Statistical rigor | Stats-first, tables secondary |
| `gtsummary` (R) | The publication-table gold standard | **It's R.** Frequently cited as what Python is missing. |

**The wedge:** a single fluent API that produces multi-dimensional crosstabs with subtotals, weighted statistics, optional significance tests, and renders to *both* styled Excel and clean HTML from one object.

## Target User (v1)

A Python-native data scientist or analytics engineer who:

- Knows pandas well enough to be tired of it for this specific job.
- Is asked to produce recurring management reports, board decks, or stakeholder updates.
- Currently round-trips through Excel for formatting.
- Doesn't necessarily know SAS — the SAS lineage is inspiration, not API surface.

Secondary users (parked for now): SAS migrants who want syntactic familiarity, biostatisticians who want Table-1 conventions.

## Design Principles

These are the load-bearing decisions. If any of these slip, the library loses its identity.

1. **The API is the product.** One call should produce a complete table. Two calls for table + render. Never more for the common case.
2. **One table object, many renderers.** The aggregation result is a first-class object with `.to_excel()`, `.to_html()`, `.to_string()`, `_repr_html_()`. Renderers are pluggable but the default output of each is publication-quality without further configuration.
3. **Sensible defaults, full overridability.** A new user writes 3 lines and gets a good table. A power user can override every cell format, label, footnote, statistical test.
4. **Subtotals and totals are first-class**, not a `margins=True` afterthought. Multi-level nested subtotals (e.g., region → state → city, with subtotals at any level) work without contortion.
5. **Statistics are integrated, not bolted on.** Counts, percentages (of row / column / total / subgroup), weighted means, chi-square, Fisher's exact, Cramér's V, etc. live in the same call — not in a separate `scipy.stats` round-trip the user assembles themselves.
6. **Excel output is genuinely good.** Merged header cells, frozen panes, conditional formatting for totals, number formats inferred from data. Not "pandas.to_excel() with a header." This is the highest-leverage differentiator.
7. **Engine-agnostic input from day one.** Accept both pandas and polars DataFrames natively, via [narwhals](https://narwhals-dev.github.io/narwhals/) as the internal compatibility layer. Aggregations execute in the user's chosen engine; results materialize into our own table model, so downstream code (subtotals, formats, renderers) is engine-free. No conversion required from the user; no engine lock-in for us.
8. **Compose with existing DataFrame workflows, don't fight them.** We are an *addition* to the user's pandas-or-polars pipeline, not a replacement. Output can be converted back to whichever DataFrame flavor the user started with.

## API Sketch — Worked Examples

> These are illustrative — names and exact shape are open for revision. The point is to make the *shape* of the API concrete enough to argue about.

### Example 1 — Frequency table (PROC FREQ analogue)

```python
import proctab as pt

pt.freq(df, "region")
```

Output (notebook): styled HTML table with `region`, `N`, `Percent`, `Cumulative N`, `Cumulative Percent`, and a total row.

```python
pt.freq(df, ["region", "product_line"])  # two-way crosstab
```

Output: regions as rows, product lines as columns, counts + row/column/total percent in each cell, marginal totals on both axes.

```python
pt.freq(df, ["region", "product_line"], test="chi2")
```

Same table, with a chi-square footer block: statistic, df, p-value, Cramér's V.

### Example 2 — Summary table (PROC TABULATE analogue)

```python
pt.tabulate(
    df,
    rows=["region", "product_line"],     # nested row dimensions
    cols=["quarter"],
    values={
        "revenue": ["sum", "mean"],
        "margin":  ["weighted_mean(weight=units)"],
    },
    subtotals="region",                  # subtotal at the region level
    totals=True,
)
```

Output: a multi-level row index (region → product line), quarter columns, three statistic columns per quarter (revenue sum, revenue mean, weighted margin), with subtotal rows at each region break and a grand total row.

### Example 3 — Render to Excel

```python
table = pt.tabulate(df, rows=["region", "product"], cols=["quarter"],
                   values={"revenue": "sum"}, totals=True)

table.to_excel("Q1_report.xlsx", sheet="Revenue")
```

Output xlsx has: merged header cells for the quarter band, bolded total row/column, currency formatting on numeric cells, frozen header pane, autofit column widths. No further configuration required.

### Example 4 — Same object, HTML

```python
table  # in a notebook, renders as styled HTML via _repr_html_
table.to_html("report.html")
```

### Example 5 — Power-user customization

```python
table = pt.tabulate(
    df, rows="region", cols="quarter", values={"revenue": "sum"},
    formats={"revenue": "${:,.0f}"},
    labels={"region": "Sales Region", "revenue": "Net Revenue"},
    style=pt.styles.executive_dark,
)
table.add_footnote("Source: internal CRM, 2026-Q1")
```

## v0.1 Scope (the minimum lovable release)

In:
- `freq()` — one-way and two-way frequency tables, with row/column/total percent.
- `tabulate()` — multi-dim rows/cols, multiple statistics (sum, mean, count, min, max, median).
- Subtotals at any row-dimension level; grand total.
- HTML rendering (notebook + standalone file) with one clean default style.
- Excel rendering with sensible defaults (merged headers, bold totals, number formats, frozen panes).
- Pandas **or** polars input via [narwhals](https://narwhals-dev.github.io/narwhals/); output convertible back to either.

Out (for v0.1, in for later versions):
- Weighted statistics.
- Statistical tests (chi-square, Fisher's, Cramér's V, etc.).
- Multiple style themes / custom styling API.
- Plain-text / Markdown / LaTeX rendering.
- PyArrow / Dask / other DataFrame engines (narwhals can extend here later).
- PDF rendering.
- SAS-syntax-faithful aliases for migrants.

## Parked / Out of Scope

- Becoming a chart library. Tables only.
- Becoming a stats library. We *integrate* common tests; we don't reimplement scipy.
- Interactive / live-update tables (great_tables territory).
- Replacing dashboards (Streamlit / Dash territory).

## Open Questions (decide before coding v0.1)

1. ~~**Name.**~~ Resolved: `proctab`. PyPI availability confirmed.
2. **Top-level API surface.** Two functions (`freq`, `tabulate`) or one (`summary`) with a mode argument? My instinct: two — they have meaningfully different default outputs.
3. **Table object class name.** `Table`? `SummaryTable`? `Tabulation`?
4. **How to specify weighted/multi-stat columns ergonomically.** The `"weighted_mean(weight=units)"` string in Example 2 is ugly. Alternatives: `pt.agg.weighted_mean("units")`, `("weighted_mean", {"weight": "units"})`, a dedicated `Weighted` class. Worth prototyping a few.
4. **Excel engine.** `openpyxl` (more flexible, slower) vs. `xlsxwriter` (faster, write-only). Probably `openpyxl` for round-tripping.
5. **License.** MIT? Apache 2.0? BSD-3?
6. **Versioning + release cadence.** Semver from v0.1, or stay 0.x until API stabilizes?

## Next Steps

1. Lock the name (resolve Open Question #1).
2. Resolve Open Questions #2–#4 with a one-page API design memo.
3. Build a throwaway prototype of `freq()` + `tabulate()` against the worked examples above. Don't worry about performance, styling polish, or test coverage yet — just prove the API feels right.
4. Show the prototype to 3–5 target users. Watch what they reach for. Revise.
5. Then start the real implementation.
