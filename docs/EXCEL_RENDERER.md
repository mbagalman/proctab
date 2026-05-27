# Excel Renderer — Design Memo (v0.1)

> Companion to [TABLE_MODEL.md](TABLE_MODEL.md), [FREQ_API.md](FREQ_API.md),
> [TABULATE_API.md](TABULATE_API.md), and [HTML_RENDERER.md](HTML_RENDERER.md).
> Goal: lock the v0.1 Excel renderer's sheet layout, number-format mapping,
> styling, and API surface before implementation. Once locked, the
> proposed [Implementation Tickets](#implementation-tickets-proposed)
> migrate to [ROADMAP.md](../ROADMAP.md).

## Scope

What the v0.1 Excel renderer does:

- Write any `Table` from the data model to an `.xlsx` file via openpyxl.
- Single entry point: `Table.to_excel(path, *, sheet="Sheet1")` — always
  writes a file; no string or stream return.
- Honor the renderer contract from
  [TABLE_MODEL.md#renderer-contract](TABLE_MODEL.md): walk axis trees with
  span/depth metadata; consult `missing[i, j]` to render per-`MissingReason`;
  emit Excel number formats keyed off `value_kinds[j]`.
- Single, sensible default theme (executive-ready: clean borders, bold
  totals, italic subtotals, merged header cells, frozen panes).
- Match the text + HTML renderers' MissingReason display rules exactly so
  the three renderers stay consistent.
- openpyxl is an **optional extra** (`pip install proctab[excel]`). The
  `to_excel` method raises a clear `ImportError` if openpyxl is missing.

What it does NOT do in v0.1 (deferred per [ROADMAP.md](../ROADMAP.md)):

- Multiple style themes / styling customization API.
- Arbitrary Python-format-string translation — `Table.formats[j]`
  values that match the known-patterns table (see
  [Number format resolution](#number-format-resolution)) translate to
  Excel format codes today; that table covers every format `freq()`
  and `tabulate()` emit plus a handful of common hand-written patterns.
  Unrecognized user-supplied format strings fall through to the
  per-`value_kind` default. A general format-string translator (any
  Python format spec → equivalent Excel code) is a v0.2 concern.
- BytesIO / writable-stream output — `path` is `str | os.PathLike[str]` only.
- Multiple sheets per Table, multiple Tables per workbook.
- Custom column widths beyond a sensible default.
- Conditional formatting, color scales, sparklines, charts.
- xlsxwriter as an alternative engine.

## Output entry point

```python
# In src/proctab/render/excel.py
def render_excel(
    table: Table,
    path: str | os.PathLike[str],
    *,
    sheet: str = "Sheet1",
) -> None:
    """Write the Table to a .xlsx file at `path`.

    `sheet` becomes the worksheet name. Must be 1-31 characters and
    must not contain any of `\\ / ? * [ ] :` (Excel's reserved set);
    a violation raises ValueError (no silent sanitization).

    Raises ImportError if openpyxl is not installed. Install it via
    `pip install proctab[excel]`.
    """
```

```python
# Added to Table:
def to_excel(
    self,
    path: str | os.PathLike[str],
    *,
    sheet: str = "Sheet1",
) -> None:
    """Render to an .xlsx file at `path`.

    Always writes a single sheet (`sheet=` overrides the default
    name "Sheet1"). See docs/EXCEL_RENDERER.md for the layout
    contract. Requires openpyxl (optional extra).
    """
    from proctab.render.excel import render_excel
    render_excel(self, path, sheet=sheet)
```

Title (from `table.meta["title"]`) is rendered into the workbook **as a
cell**, not as the sheet name. The two are deliberately separate: sheet
names have stricter rules than display titles (`"Q1 Report: 2026"` is a
valid title but an invalid sheet name).

## Sheet layout

Layout schematic for a tabulate-style Table with title, two col-axis
dims (Quarter × _stat), two row-axis dims with subtotals, totals, and
both source + footnotes:

```
       A          B       C       D       E       F       G
  ┌──────────────────────────────────────────────────────────────────────┐
 1│ {title — merged A1:G1, bold, font size +2}                            │
 2│                                                                       │
 3│              ┌─Q1───┬─Q1───┬─Q2───┬─Q2───┬─Total┬─Total┐              │ ← outer col headers
 4│              │ rev  │ marg │ rev  │ marg │ rev  │ marg │              │ ← inner col headers
 5│              │ sum  │ mean │ sum  │ mean │ sum  │ mean │              │ ← stat headers
 6│ West         │      │      │      │      │      │      │              │ ← group header (italic)
 7│   Widget A   │ 100  │ 0.20 │ 120  │ 0.22 │ 220  │ 0.21 │              │ ← data leaf
 8│   Widget B   │  80  │ 0.15 │  90  │ 0.18 │ 170  │ 0.17 │              │ ← data leaf
 9│   West Subt  │ 180  │ 0.18 │ 210  │ 0.20 │ 390  │ 0.19 │              │ ← subtotal (italic)
10│ Grand Total  │ 320  │ 0.19 │ 360  │ 0.21 │ 680  │ 0.20 │              │ ← total (bold)
11│                                                                       │
12│ Source: internal CRM, 2026-Q1        (merged A12:G12, wrap, thin top) │
13│ All figures USD. Excludes returns.   (merged A13:G13, wrap)           │
  └──────────────────────────────────────────────────────────────────────┘
```

With this fixture: `H = 3`, `title_present = True`, so
`header_start = 3`, `body_start = 6`, `freeze_panes = "B6"`.

### Row-position variables

Layout rows are computed from a few values so the with-title and
no-title cases share one rule (and the freeze-pane formula and edge
cases stay in sync):

```
title_present = bool(meta.get("title"))
H             = len(col_axis.dims)                 # number of col header rows
N_body        = number of body rows emitted

header_start  = 3 if title_present else 1          # row 3 leaves a spacer; row 1 if no title
body_start    = header_start + H
body_end      = body_start + N_body - 1
last_body_col = openpyxl.utils.get_column_letter(max(1, 1 + n_col_leaves))
                                                   # "G" for 6 col leaves;
                                                   # "A" when n_col_leaves == 0
                                                   # (empty Table — title/footer
                                                   # merges collapse to single cell)
footer_block_present = bool(meta.get("source") or meta.get("footnotes"))

freeze_panes  = f"B{body_start}"                   # freezes title + headers + col A
```

Key positions:

| Region                       | Rows                                       | Cols |
|------------------------------|--------------------------------------------|------|
| Title (if title_present)     | `1`                                        | `A1:{last_body_col}1` merged |
| (blank spacer if title)      | `2`                                        | — |
| Column headers               | `header_start .. header_start + H - 1`     | `A` corner blank; `B..` are header cells |
| Body                         | `body_start .. body_end`                   | `A` row labels; `B..` body cells |
| (blank spacer if footer)     | `body_end + 1`                             | — |
| Source (if `meta.source`)    | `body_end + 2`                             | `A..{last_body_col}` merged |
| Footnotes (if any)           | `body_end + 3 .. body_end + 2 + len(footnotes)` | `A..{last_body_col}` merged |

The row-label column is always column A. Body data starts at column B.

### Header cell merging

For each col-axis dim depth `d` (rows `header_start..header_start + H - 1`,
per the [row-position variables](#row-position-variables)), interior
nodes that span multiple leaves get merged across `node.span` cells.
Leaves at the innermost depth occupy a single cell each. The top-left
corner (`A{header_start}:A{header_start + H - 1}`) is left blank —
analogous to the HTML renderer's `aria-hidden` corner.

### Body row layout

- **Interior row-tree nodes** (group headers): single cell at column A
  with the group label (e.g., "West"); body columns left blank. Mirrors
  the HTML renderer's two-cell group-header row, simplified for Excel
  (no `colspan` mechanic; left-blank achieves the same visual effect).
- **Leaf rows**: column A holds the indented row label; columns B..
  hold one numeric (or text-for-missing) cell each, one per col leaf.

### Source and footnotes

- `source` → cell at column A on row `body_end + 2`, prefixed
  `"Source: "`, **merged across `A..{last_body_col}`**, smaller font,
  thin top border, left-aligned, wrap enabled.
- `footnotes` → one row per footnote starting at row `body_end + 3`,
  **merged across `A..{last_body_col}`** with the same styling as
  source minus the top border (only the first row of the footer block
  carries the separator).

Merging is required so executive notes longer than column A's ~40-char
cap don't get visually clipped. Wrap is enabled so multi-line notes
flow within the merged block. openpyxl does not compute rendered row
heights (that's an Excel UI concern); v0.1 leaves row height at
Excel's default — Excel itself may expand the row when the file is
opened. A simple width-aware row-height estimate is a v0.2 polish item.

## Number format resolution

Priority chain — matches the HTML renderer's `_resolve_format` and the
`Table.formats[j]` contract in
[TABLE_MODEL.md](TABLE_MODEL.md#dataframe-export):

1. **Explicit `Table.formats[j]` is translated** to an Excel format
   code via the known-patterns table below. Successful translation wins.
2. **Otherwise, fall back** to the per-`value_kind` renderer default.
3. **Final fallback:** `"General"` for unknown value kinds.

This is essential, not optional: `freq()` stores percent columns on a
**0–100 scale** and supplies an explicit `"{:.1f}%"` format. Without
translation, treating a stored `66.7` with the percent kind default
`"0.0%"` would render `6670.0%` in Excel — visibly wrong on every
normal `freq()` call. The translation table below specifically covers
that pattern.

### Known format translations

Covers every format string `freq()` and `tabulate()` emit today, plus
the most common patterns users hand-write. Unknown `formats[j]` values
fall through to the per-kind default.

| Python format string | Excel format code | Notes |
|----------------------|-------------------|-------|
| `"{:,d}"`            | `"#,##0"`         | integer with thousands separator |
| `"{:,.0f}"`          | `"#,##0"`         | same display as `:,d` for whole numbers |
| `"{:,.1f}"`          | `"#,##0.0"`       | used by `examples.example_2_tabulate` |
| `"{:,.2f}"`          | `"#,##0.00"`      |       |
| `"{:,.4f}"`          | `"#,##0.0000"`    |       |
| `"${:,.0f}"`         | `"$#,##0"`        | currency, no decimals (used by `examples.example_5_customized`) |
| `"${:,.2f}"`         | `"$#,##0.00"`     | currency |
| `"{:.1%}"`           | `"0.0%"`          | percent stored on **0–1 scale** |
| `"{:.2%}"`           | `"0.00%"`         | percent stored on **0–1 scale** |
| `"{:.1f}%"`          | `"0.0\"%\""`      | percent stored on **0–100 scale** (literal `%` suffix; `freq()` flow) |
| `"{:.2f}%"`          | `"0.00\"%\""`     | percent stored on **0–100 scale** |
| `"{:.0f}"`           | `"0"`             |       |
| `"{:.1f}"`           | `"0.0"`           |       |
| `"{:.2f}"`           | `"0.00"`          |       |
| `"{:.3f}"`           | `"0.000"`         |       |
| `"{:g}"`             | `"General"`       |       |

### Per-`value_kind` defaults (used when `formats[j]` is `None` or unrecognized)

Parallel to the HTML renderer's `_KIND_DEFAULTS`. The percent default
assumes 0–1 scale; producers that store percents as 0–100 must supply
the explicit `"{:.1f}%"` format string so the translation step picks
the literal-percent Excel code.

| `value_kind`     | Excel format code | Example display |
|------------------|-------------------|-----------------|
| `count`          | `"#,##0"`         | `1,234`         |
| `currency`       | `"$#,##0.00"`     | `$1,234.50`     |
| `percent`        | `"0.0%"`          | `42.0%` (0.42 input — 0–1 scale only) |
| `ratio`          | `"0.000"`         | `0.123`         |
| `sum`            | `"#,##0"`         | `1,234,568`     |
| `mean`           | `"#,##0.00"`      | `42.57`         |
| `weighted_mean`  | `"#,##0.00"`      | `42.57`         |
| `median`         | `"#,##0.00"`      | `42.57`         |
| `raw`            | `"General"`       | Excel's default |
| unknown kind     | `"General"`       | fallback        |

Internal flows are covered: `freq()`'s 0–100 percents go through
`"{:.1f}%"` → `0.0"%"`; `tabulate()`'s `STAT_DEFAULTS` (`{:,.0f}`,
`{:,.2f}`) are in the translation table; everything else either hits
the per-kind default or `"General"`. v0.2 may extend the translation
table or add an explicit Excel-format-string passthrough on
`Table.formats[j]`.

## MissingReason rendering

Matches the text + HTML renderers exactly:

| MissingReason     | Cell content      | Cell type |
|-------------------|-------------------|-----------|
| `PRESENT`         | numeric value     | number, with format |
| `EMPTY`           | empty             | (no value written) |
| `NOT_APPLICABLE`  | `"—"` (em dash)   | text |
| `SUPPRESSED`      | `"***"`           | text |
| `NULL`            | `"·"` (middle dot)| text |

Text cells in numeric columns: Excel allows mixed content, the number
format just doesn't apply to the text. No special handling needed.

## Default styling

openpyxl `Font` / `Border` / `Alignment` / `PatternFill` objects keyed
off the same role/missing/group classifications the HTML renderer uses.
The two renderers share a logical model; only the underlying objects
differ.

- **Title (row 1):** bold, font size +2 over default, left-aligned,
  merged across body columns.
- **Column header cells:** bold, centered, bottom border (thin).
- **Body cells:**
  - default: right-aligned numeric.
  - subtotal row cells: italic.
  - total row cells: bold; top border (medium).
  - total column cells (any row): left border (medium).
  - grand-total cell (total row × total col): bold + top border (medium)
    + left border (medium).
- **Row labels (column A):** left-aligned; `indent = depth - 1`
  (openpyxl's `Alignment(indent=...)`). Subtotal rows: italic; total
  rows: bold.
- **Source/footnotes:** smaller font (default - 1), italic, left-aligned;
  thin top border on the first tfoot row.
- **No background colors** in v0.1 (parallel with HTML).
- **Tabular numerals:** Excel uses tabular numerals by default for the
  built-in font; no explicit setting needed.

The defaults are deliberately conservative — readable when opened in
Excel, sane when emailed to a stakeholder, no surprises.

## Frozen pane, column widths, sheet name

- **Frozen pane:** `worksheet.freeze_panes = f"B{body_start}"` per the
  [row-position variables](#row-position-variables). This freezes the
  title row + spacer + column-header rows (when title is present, or
  just the header rows when not) AND the row-label column, so scrolling
  right keeps row labels visible and scrolling down keeps headers visible.
- **Column widths:** column A (row labels) widened to fit the longest
  row label plus indent (cap at a sensible max, e.g., 40 chars). Body
  columns get a uniform default width of 12. Per-column custom widths
  are v0.2.
- **Sheet name:** defaults to `"Sheet1"`. User can override via
  `sheet=` kwarg. Validation rules:
  - 1–31 characters.
  - Must not contain any of `\ / ? * [ ] :` (Excel's reserved set).
  - Violations raise `ValueError` with a clear message. No silent
    sanitization (silent corruption is worse than a loud failure).
  - The title (from `meta.title`) is NOT auto-used as the sheet name;
    titles often contain colons or other reserved chars.

## Worked examples

### Example 1 — one-way frequency table

Input: `freq(df, "region")`.

Layout: no title in this fixture, 1 col-axis dim (`_stat`, H=1) × 4
stat leaves. So `header_start = 1`, `body_start = 2`,
`freeze_panes = "B2"`.

- Row 1 (header): A1 blank; B1..E1 = "N", "Pct", "CumN", "CumPct"
  (centered, bold, thin bottom border)
- Rows 2..5 (data leaves): A2..A5 = "West", "East", "South", "North"
  (left-aligned, indent 0); B2..E5 = numbers with formats. Percent
  columns use the literal-percent `0.0"%"` code (freq stores 0–100).
- Row 6 (total): A6 = "Total" (bold); B6..E6 = numbers (bold, medium
  top border).
- Frozen pane: `B2`.
- Sheet name: `"Sheet1"`.

### Example 2 — two-way crosstab with col total

Input: `freq(df, "region", "product_line")` (output includes a Total
product_line group).

Layout: no title, 2 col-axis dims (`product_line`, `_stat`; H=2) × 12
stat leaves. So `header_start = 1`, `body_start = 3`,
`freeze_panes = "B3"`.

- Row 1 (outer col header): B1:E1 merged = "Widget A"; F1:I1 merged =
  "Widget B"; J1:M1 merged = "Total" (last group's header cells get the
  medium left border on cell J1 — the col-total divider).
- Row 2 (inner col header): B2..M2 = "N", "Row%", "Col%", "Tot%" ×3.
- Frozen pane: `B3`.

### Example 3 — multi-row tabulate

Input: `tabulate(df, rows=["region", "product"], cols="quarter",
values={"revenue": ["sum", "mean"]}, subtotals="region", totals=True)`.

Layout per the schematic at the top of this memo: title row (if
`meta.title`), 3 header rows, 2 group-header rows (West, East) + 4 data
leaves + 2 subtotal rows + 1 grand-total row, then optional source +
footnotes.

## Edge cases

- **Empty Table** (zero leaves on either axis) → write a sheet with
  just the title (if any) and an empty header row. Don't raise. Mirrors
  the HTML renderer.
- **No title in meta** → handled by the
  [row-position variables](#row-position-variables): `header_start = 1`,
  so column headers start at row 1, body at row `1 + H`, and the
  freeze pane shifts accordingly. Not a special case; the same
  formulas apply.
- **No source and no footnotes** → omit the trailing blank-spacer row.
- **Header text with Excel-sensitive characters** → openpyxl handles
  any string in cell values; no escaping concern (Excel isn't markup).
- **Path with non-`.xlsx` extension** → don't validate the extension;
  openpyxl will still write a valid xlsx file. Document that the
  conventional extension is `.xlsx`.
- **Path doesn't exist / parent dir missing** → openpyxl raises
  `FileNotFoundError`; propagate as-is.
- **`sheet=` is the empty string or > 31 chars or has reserved chars**
  → `ValueError` with the exact rule violated.
- **openpyxl not installed** → `ImportError("Excel export requires
  openpyxl. Install it with `pip install proctab[excel]`.")`. Raised
  on import inside `render_excel`, so a user calling `Table.to_excel(...)`
  without openpyxl sees the message immediately.

## Recommended decisions

1. **openpyxl is the engine.** Read+write, mature, full styling API.
   xlsxwriter is faster for very large sheets but write-only; v0.1
   speed isn't a concern. **Confidence: high.**
2. **openpyxl is an optional extra** (`pip install proctab[excel]`).
   Keeps the baseline footprint lean for users who only want HTML or
   DataFrame export. `to_excel` raises a clear `ImportError` if missing.
   **Confidence: high.**
3. **`Table.to_excel(path)` accepts `str | os.PathLike[str]` only.**
   No BytesIO / stream support in v0.1. Adds later if a real use case
   shows up. **Confidence: high.**
4. **`Table.formats[j]` translates to Excel format codes for known
   patterns; per-`value_kind` defaults for unknown.** Matches the
   `formats[j]` contract in
   [TABLE_MODEL.md](TABLE_MODEL.md#dataframe-export) and HTML's
   explicit-format-wins priority. The known-patterns table covers
   every format `freq()` and `tabulate()` emit today (including
   `"{:.1f}%"` → `0.0"%"`, which is required for `freq()`'s 0–100
   percent storage to render correctly). Unknown user-supplied
   Python format strings fall through to the per-kind default —
   the harder "general Python format → Excel format" translation
   stays deferred to v0.2. **Confidence: high.**
5. **Title goes in cell A1; sheet name is separate.** Sheet names have
   stricter rules than titles (colons forbidden in sheets, common in
   titles). User explicitly overrides via `sheet=`. **Confidence: high.**
6. **Single row-label column, indented per leaf depth.** Matches text
   and HTML renderers; same renderer model. Multi-column row-label
   layouts (one column per row dim) deferred. **Confidence: high.**
7. **Frozen pane at `f"B{body_start}"`** (per the
   [row-position variables](#row-position-variables)) — freezes
   title + headers + row-label column. Matches analyst expectations
   for scrolling. **Confidence: high.**
8. **MissingReason display matches the text + HTML renderers.**
   Cross-renderer consistency. **Confidence: high.**

## Open questions

1. ~~Should the title cell merge across body columns or stay
   single-cell?~~ Resolved: **merge across `A1:{last_body_col}1`**
   per the [layout schematic](#sheet-layout). Override flag deferred.
2. **Column widths — fixed defaults or autofit estimate?** openpyxl
   doesn't natively autofit (it requires opening the file in Excel to
   compute widths from rendered text). v0.1 plan: **fixed default of
   12 for body columns, longest-label-fit for column A capped at 40**.
   A real autofit pass (estimate from longest text + average char
   width) lands in v0.2.
3. **Should we emit a default `Source: proctab v…` footer when meta
   has no source?** Probably not — silent identifiers in others'
   reports are surprising. Skip in v0.1.

## Implementation tickets (proposed)

Each is one well-bounded coding session. Migrate to ROADMAP after this
memo locks.

1. **E1.** Module skeleton + Excel-format resolution helper. Create
   `src/proctab/render/excel.py` with `render_excel(table, path, *,
   sheet="Sheet1") -> None` stub (just opens a workbook, writes nothing,
   saves) and the per-cell format resolver `_resolve_excel_format(fmt,
   value_kind)` implementing the full priority chain
   (translate known `formats[j]` patterns → per-kind default → `"General"`)
   per [Number format resolution](#number-format-resolution). Both the
   translation table and the per-kind defaults are module-level constants.
   Also add `_validate_sheet_name(name)`. Optional extra dependency:
   add to `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   excel = ["openpyxl>=3.1"]
   ```
2. **E2.** Column header rendering. Compute the
   [row-position variables](#row-position-variables) (`header_start`,
   `body_start`, `last_body_col`) once and emit rows
   `header_start..header_start + H - 1`, with merged cells for interior
   nodes spanning multiple leaves. Top-left corner blank. Per-role
   classes drive per-cell styling later (data / subtotal / total).
3. **E3.** Body rendering — single ticket combining row-tree pre-order
   AND per-cell emission. Interior nodes emit group-header rows (label
   only, body columns blank); leaves emit row-label + body cells.
   Cells dispatch on `MissingReason` and apply the format resolver
   from E1 (translate `formats[j]` if known, else per-kind default).
4. **E4.** Title + source + footnotes. Title at row 1 merged
   `A1:{last_body_col}1` (bold, font +2); blank spacer at row 2.
   Source row at `body_end + 2` merged `A..{last_body_col}` with thin
   top border and wrap enabled; footnote rows from `body_end + 3` with
   the same merging + wrap, smaller font, no top border (only the
   first footer row carries the separator). All optional based on
   `meta.get("title" / "source" / "footnotes")`. Uses the
   [row-position variables](#row-position-variables) from E2.
5. **E5.** Default styling — apply openpyxl `Font` / `Border` /
   `Alignment` objects per the role/missing rules in
   [Default styling](#default-styling). Single source-of-truth dict
   mapping role → style, analogous to HTML's `_STYLE_BY_CLASS`.
6. **E6.** Frozen pane + column widths + sheet name validation. Set
   `worksheet.freeze_panes = f"B{body_start}"`; set column A width
   from longest label (capped at 40); body columns to default 12.
   Validate `sheet=` per Excel's rules; raise `ValueError` on
   violation.
7. **E7.** Wire `Table.to_excel(path, *, sheet="Sheet1")` to
   `render_excel`. Lazy-import inside the method to avoid making
   openpyxl a hard dep. Raise `ImportError` with the
   `pip install proctab[excel]` message when openpyxl is absent.
8. **E8.** Tests. Open the written file via openpyxl, walk cells, and
   assert: title cell value + style; column header values + merged
   ranges + bottom border; per-cell number formats matching the
   `value_kind` table; total-row cells bold + medium top border;
   total-column cells medium left border; subtotal cells italic;
   frozen-pane reference; sheet name; source/footnote cell positions
   and styles; MissingReason text mapping; sheet-name validation
   errors; missing-openpyxl ImportError path (via `monkeypatch` of
   `sys.modules`). Integration tests render the existing
   `examples.py` fixtures and reopen the workbooks. Edge cases:
   empty Table, no title, no source/footnotes, invalid sheet name.

## Out of scope (this memo)

- HTML renderer — its own memo ([HTML_RENDERER.md](HTML_RENDERER.md))
  and complete.
- DataFrame export — landed; see
  [TABLE_MODEL.md#dataframe-export](TABLE_MODEL.md#dataframe-export).
- Plain-text renderer — already shipped.
- Renderer model changes — none needed; the existing
  [TABLE_MODEL.md#renderer-contract](TABLE_MODEL.md) contract is what
  this renderer consumes.
- Wide-format DataFrame export, custom column widths, autofit,
  general Python-format-string translation (beyond the
  [known-patterns table](#known-format-translations)), multiple
  sheets — all v0.2.
