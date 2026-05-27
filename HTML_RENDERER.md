# HTML Renderer — Design Memo (v0.1)

> Companion to [TABLE_MODEL.md](TABLE_MODEL.md), [FREQ_API.md](FREQ_API.md),
> and [TABULATE_API.md](TABULATE_API.md). Goal: lock the v0.1 HTML
> renderer's structure, styling approach, and API surface before
> implementation. Once locked, the proposed
> [Implementation Tickets](#implementation-tickets-proposed) migrate to
> [ROADMAP.md](ROADMAP.md).

## Scope

What the v0.1 HTML renderer does:

- Render any `Table` from the data model to HTML.
- Two entry points:
  - `Table._repr_html_()` — auto-rendering in Jupyter notebooks
    (returns an HTML fragment).
  - `Table.to_html(path=None)` — programmatic export; **always**
    standalone HTML. Returns the HTML string if `path is None`;
    writes the standalone HTML file and returns `None` otherwise.
    Fragment-mode access is via `render_html(table, standalone=False)`
    for users who specifically want an embeddable fragment.
- Honor the renderer contract from
  [TABLE_MODEL.md#renderer-contract](TABLE_MODEL.md#renderer-contract):
  walk axis trees with span/depth metadata; consult `missing[i, j]`
  to render per-`MissingReason`; respect `formats[j]` and `value_kinds[j]`;
  emit numeric `data-value` attributes alongside formatted display text.
- Single, sensible default theme (executive-ready: clean borders, bold
  totals, indented subtotals).
- Match the text renderer's MissingReason display rules exactly so the
  two renderers stay consistent.

What it does NOT do in v0.1 (deferred per [ROADMAP.md](ROADMAP.md)):

- Multiple style themes / CSS customization API.
- Interactive features (sorting, filtering, drill-down).
- Responsive design / scrollable wrappers.
- External CSS file output.
- Accessibility audit (basic semantic HTML only; full ARIA pass is v0.2).
- Print-specific styling.

## Output modes

Two output shapes:

### Fragment mode

For `Table._repr_html_()` and direct `render_html(table, standalone=False)`
calls. Produces:

```html
<table class="legible" ...inline styles...>
  <thead>...</thead>
  <tbody>...</tbody>
</table>
```

No `<html>`, `<head>`, `<body>`, or `<!DOCTYPE>`. Styling is inline
per element (`style="..."` attributes) to avoid cross-cell CSS bleed in
notebooks and other embedding contexts.

Fragment mode **still emits the full `legible-*` class hierarchy**
alongside inline styles: classes carry structural and role semantics
(needed for tests, downstream parsers, and any consumer-page CSS that
wants to target the table), while inline styles provide the visual
defaults without depending on a stylesheet. Inline-style values
exactly mirror the standalone-mode CSS rules for the corresponding
class, so the two modes render identically.

### Standalone mode

For all calls to `Table.to_html(...)` (with or without `path`) and
direct `render_html(table, standalone=True)`. Wraps the fragment in:

```html
<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <title>{table title or "Legible table"}</title>
  <style>...embedded default theme...</style>
</head><body>
  <table class="legible">...</table>
</body></html>
```

In standalone mode, the same fragment uses class-based styling
(referencing the embedded `<style>` block) instead of inline styles.

## HTML structure

All class names use the `legible-` prefix to avoid collision with
consumer-page CSS in embedded contexts (notebooks, blog posts,
internal portals). All column / row / rowgroup headers carry an
appropriate `scope=` attribute for cheap semantic correctness (not a
full accessibility audit, but the easy win).

```html
<table class="legible">
  <caption class="legible-caption">{table.meta["title"]}</caption>
  <thead>
    <!-- One <tr> per col-axis dim (column header row) -->
    <!-- Top-left corner <th> spans all row-label cols × all header rows.
         No scope= — the corner is not a column or row header; it's a
         structural spacer until v0.2 puts row-dim labels there. -->
    <tr>
      <th rowspan="N_HEADER_ROWS" class="legible-corner" aria-hidden="true"></th>
      <th colspan="..." scope="colgroup" class="legible-col-data">...</th>
      ...
      <th colspan="..." scope="colgroup" class="legible-col-total">Total</th>
    </tr>
    <!-- Additional <tr> rows for nested col dims; innermost row uses
         scope="col" instead of scope="colgroup" -->
  </thead>
  <tbody>
    <!-- Group-header row for interior row-tree node (e.g., "West"
         above its product leaves). Two cells preserve column geometry: -->
    <tr class="legible-group-header">
      <th scope="rowgroup" class="legible-row-label">West</th>
      <td colspan="{n_body_cols}" class="legible-group-pad"></td>
    </tr>
    <tr class="legible-data">
      <th scope="row" class="legible-row-label legible-indent-{depth-1}">label</th>
      <td class="legible-cell legible-data" data-value="42.0">42</td>
      ...
    </tr>
    <tr class="legible-subtotal">
      <th scope="row" class="legible-row-label">West Subtotal</th>
      <td class="legible-cell legible-subtotal" data-value="...">...</td>
      ...
    </tr>
    <tr class="legible-total">
      <th scope="row" class="legible-row-label">Grand Total</th>
      <td class="legible-cell legible-total">...</td>
      ...
    </tr>
  </tbody>
  <tfoot>
    <!-- Source + footnotes, present iff table.meta has them -->
    <tr class="legible-source">
      <td colspan="{n_total_cols}">Source: {table.meta["source"]}</td>
    </tr>
    <tr class="legible-footnote">
      <td colspan="{n_total_cols}">{footnote}</td>
    </tr>
  </tfoot>
</table>
```

### Title, source, footnotes

`table.meta` may contain `title`, `source`, and `footnotes` (a list).
The HTML renderer surfaces all three to match the text renderer:

- `title` → `<caption class="legible-caption">…</caption>` immediately
  inside `<table>`. Omitted when `meta` has no title.
- `source` → `<tr class="legible-source"><td colspan=…>Source: …</td></tr>`
  in `<tfoot>`. Omitted when no source.
- `footnotes` → one `<tr class="legible-footnote">` per footnote, in
  `<tfoot>`. Each `<td>` spans the full table width
  (`colspan = 1 row-label + n_col_leaves`).

`<tfoot>` itself is omitted when there's nothing to put in it.
All text is HTML-escaped.

### Column headers

- One `<tr>` per col-axis dim depth (so for `col_axis.dims = (quarter,
  _metric, _stat)`, three header rows).
- Each interior node at depth `d` becomes `<th colspan="node.span"
  scope="colgroup">`.
- Leaf nodes at the innermost depth become `<th colspan="1" scope="col">`.
- The top-left corner gets
  `<th rowspan="N_HEADER_ROWS" class="legible-corner" aria-hidden="true">`
  to span all header rows above row labels. No `scope=` — an empty
  corner cell is neither a column nor a row header. `aria-hidden="true"`
  keeps assistive tech from announcing the spacer. (v0.2 may put
  row-dim labels there, at which point `scope="col"` becomes meaningful.)
- Headers carry a class per role: `legible-col-data`,
  `legible-col-subtotal`, or `legible-col-total`.

### Row labels and group-header rows

- Single column on the left, NOT one column per row dim.
- Indented per the leaf's `depth` (matching text renderer convention).
- `class="legible-indent-{depth-1}"` for CSS targeting.
- Interior row-tree nodes (group headers like "West" above its product
  leaves) emit a `<tr class="legible-group-header">` with TWO cells:
  - `<th scope="rowgroup">{label}</th>` for the group name (single
    row-label column), AND
  - `<td colspan="{n_body_cols}" class="legible-group-pad"></td>`
    spanning the body columns.

  Both cells together preserve full column geometry, which keeps the
  table parseable and visually aligned. (Earlier draft had only the
  `<th>` — rejected after review; bare-cell rows make alignment,
  testing, and downstream parsing messier.)

Alternative (rejected for v0.1): `<th rowspan="...">` for outer row
dims. More semantically correct HTML but adds complexity; indented
labels are simpler and the renderer model already supports them.

### Body cells

- `<td>` per leaf × leaf intersection.
- `class="legible-cell legible-{role}"` where role is `data` /
  `subtotal` / `total`. The role is determined by the column-leaf
  role when row and column leaf roles differ, per the convention "any
  total-leaf cell is a total cell."
- Numeric cells additionally carry `data-value="{value}"` for the raw
  numeric value (per the TABLE_MODEL HTML renderer obligation).
- **`data-value` serialization:** use `format(float(value), ".17g")`,
  which preserves IEEE 754 double precision (round-trip-safe) without
  scientific-notation surprises for typical magnitudes. The attribute
  value is then HTML-attribute-escaped (`"`, `&`, etc.) before insertion.
- **`data-value` for non-finite PRESENT cells:** if `body[i, j]` is
  NaN or ±inf despite `missing[i, j] == PRESENT`, omit `data-value`.
  Cell text is the formatted display per [Format resolution](#format-resolution)
  and [MissingReason rendering](#missingreason-rendering).
- Cell text is the formatted display per [Format resolution](#format-resolution)
  and `MissingReason` rules (below).

## Format resolution

A small helper resolves the display format for each cell with the
following priority (consistent with
[TABLE_MODEL.md#renderer-contract](TABLE_MODEL.md#renderer-contract)):

1. **Explicit `formats[j]` wins.** If `table.formats[j]` is a
   non-None string, use `formats[j].format(body[i, j])`.
2. **Otherwise, fall back to a renderer default keyed by
   `table.value_kinds[j]`.** Default per-kind formats (renderer-local;
   not the same as `STAT_DEFAULTS` from `tabulate.py`, which is the
   axis-build layer's source of formats):

   | `value_kind`    | renderer default |
   |-----------------|------------------|
   | `count`         | `"{:,d}"` if integer-typed, else `"{:,.0f}"` |
   | `currency`      | `"${:,.2f}"`     |
   | `percent`       | `"{:.1%}"` — assumes a 0–1 value |
   | `ratio`         | `"{:.3f}"`       |
   | `sum`           | `"{:,.0f}"`      |
   | `mean`          | `"{:,.2f}"`      |
   | `weighted_mean` | `"{:,.2f}"`      |
   | `median`        | `"{:,.2f}"`      |
   | `raw`           | `"{:g}"`         |
3. **Final fallback:** `"{:g}"` (sensible numeric default).

In practice, both `freq()` and `tabulate()` always populate
`formats[j]` (via `_ONE_WAY_FORMATS`, `_TWO_WAY_FORMATS`, and
`STAT_DEFAULTS`), so priority 1 always wins for those flows. The
priority chain matters for hand-built `Table`s and for v0.2+ flows
that may leave `formats[j]=None`.

**Percent storage convention:** the renderer fallback assumes percent
values are stored as 0–1 (so 0.42 displays as `42.0%`). If a producer
stores percents as 0–100 (so 42 should display as `42.0%`), it MUST
provide an explicit `formats[j]` such as `"{:.1f}%"`; the renderer
cannot reliably infer the scale per cell. Current `freq()` and
`tabulate()` flows already supply explicit formats, so this constraint
only applies to hand-built `Table`s.

## MissingReason rendering

Matches the text renderer exactly:

| MissingReason     | Display text                                              |
|-------------------|-----------------------------------------------------------|
| `PRESENT`         | resolved-format applied to `body[i, j]` (see above)       |
| `EMPTY`           | empty string                                              |
| `NOT_APPLICABLE`  | `—` (em dash)                                             |
| `SUPPRESSED`      | `***`                                                     |
| `NULL`            | `·`                                                       |

Non-PRESENT cells also get `class="legible-cell legible-missing-{reason}"`
(e.g., `legible-missing-empty`, `legible-missing-null`,
`legible-missing-not-applicable`, `legible-missing-suppressed`) for CSS
targeting in case a future theme wants to style them distinctively
(e.g., italicize NULL or color SUPPRESSED).

`data-value` attribute is emitted only for `PRESENT` cells. For
missing cells, no `data-value` — there's no meaningful number to
attach.

## Default styling

Embedded `<style>` in standalone mode; inline equivalents in fragment
mode. Minimum executive-ready defaults:

- Sans-serif font for headers and labels; tabular numerals for cell
  values (`font-variant-numeric: tabular-nums` if available).
- Right-align numeric cells; left-align labels.
- Borders: thin between rows, thicker above total rows and to the
  left of the Total column.
- Subtotal rows: italic.
- Total rows: bold + slightly heavier top border.
- Padding: 4px vertical, 8px horizontal.
- No background colors in v0.1 (color choices invite v0.2 theming).

The CSS is deliberately conservative — readable in a notebook, sane
when embedded in another page, no surprises. v0.2 themes can layer
on top.

## Renderer entry points

```python
# In src/legible/render/html.py
def render_html(
    table: Table,
    *,
    standalone: bool = False,
) -> str:
    """Render a Table to an HTML string.

    standalone=False (default): returns an HTML fragment with inline
    styling, suitable for embedding (notebooks, web pages, emails).

    standalone=True: returns a full HTML document with embedded
    <style>, DOCTYPE, head, and body.
    """
```

```python
# Added to legible.model.Table:
def _repr_html_(self) -> str:
    """Jupyter / IPython HTML auto-rendering hook."""
    from legible.render.html import render_html
    return render_html(self, standalone=False)


def to_html(
    self, path: str | os.PathLike[str] | None = None
) -> str | None:
    """Render to standalone HTML.

    Always produces a full HTML document (DOCTYPE + head + body +
    embedded styling). For an embeddable fragment, call
    `legible.render.html.render_html(table, standalone=False)` directly,
    or rely on `_repr_html_()` in notebooks.

    If `path` is None (default), returns the HTML string.
    If `path` is given (str or os.PathLike), writes the HTML to that
    file and returns None (matches the `pandas.DataFrame.to_csv()`
    convention).
    """
    from legible.render.html import render_html
    html = render_html(self, standalone=True)
    if path is None:
        return html
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return None
```

## Worked examples

### Example 1 — one-way frequency table

Input: `freq(df, "region")` from the existing examples.

HTML structure (fragment, abbreviated):

```html
<table class="legible">
  <thead>
    <tr>
      <th rowspan="1" class="legible-corner" aria-hidden="true"></th>
      <th scope="col" class="legible-col-data">N</th>
      <th scope="col" class="legible-col-data">Pct</th>
      <th scope="col" class="legible-col-data">CumN</th>
      <th scope="col" class="legible-col-data">Cum%</th>
    </tr>
  </thead>
  <tbody>
    <tr class="legible-data">
      <th scope="row" class="legible-row-label">West</th>
      <td class="legible-cell legible-data" data-value="45">45</td>
      <td class="legible-cell legible-data" data-value="30">30.0%</td>
      <td class="legible-cell legible-data" data-value="45">45</td>
      <td class="legible-cell legible-data" data-value="30">30.0%</td>
    </tr>
    <!-- East, South, North rows ... -->
    <tr class="legible-total">
      <th scope="row" class="legible-row-label">Total</th>
      <td class="legible-cell legible-total" data-value="150">150</td>
      ...
    </tr>
  </tbody>
</table>
```

### Example 2 — two-way crosstab

`freq(df, "region", "product_line")` produces a `<thead>` with TWO
rows (product_line headers spanning 4 columns each for the stat
sub-columns):

```html
<thead>
  <tr>
    <th rowspan="2" class="legible-corner" aria-hidden="true"></th>
    <th colspan="4" scope="colgroup" class="legible-col-data">Widget A</th>
    <th colspan="4" scope="colgroup" class="legible-col-data">Widget B</th>
    <th colspan="4" scope="colgroup" class="legible-col-total">Total</th>
  </tr>
  <tr>
    <th scope="col" class="legible-col-data">N</th>
    <th scope="col" class="legible-col-data">Row%</th>
    <th scope="col" class="legible-col-data">Col%</th>
    <th scope="col" class="legible-col-data">Tot%</th>
    <!-- same four under Widget B and Total -->
  </tr>
</thead>
```

### Example 3 — multi-row tabulate

For `tabulate(rows=["region", "product"], subtotals="region", ...)`,
the row label column gets indentation per leaf depth, with group
headers emitted as 2-cell `<tr>` rows that preserve column geometry:

```html
<tbody>
  <tr class="legible-group-header">
    <th scope="rowgroup" class="legible-row-label legible-indent-0">West</th>
    <td colspan="{n_body_cols}" class="legible-group-pad"></td>
  </tr>
  <tr class="legible-data">
    <th scope="row" class="legible-row-label legible-indent-1">Widget A</th>
    <td>...</td>...
  </tr>
  <tr class="legible-data">
    <th scope="row" class="legible-row-label legible-indent-1">Widget B</th>
    <td>...</td>...
  </tr>
  <tr class="legible-subtotal">
    <th scope="row" class="legible-row-label legible-indent-1">West Subtotal</th>
    <td>...</td>...
  </tr>
  <!-- East rows ... -->
  <tr class="legible-total">
    <th scope="row" class="legible-row-label">Grand Total</th>
    <td>...</td>...
  </tr>
</tbody>
```

## Edge cases

- **Empty Table** (zero leaves on either axis) → emit `<table>` with
  `<thead>` (just the corner cell) and an empty `<tbody>`. Don't
  raise. Matches text renderer behavior.
- **Single-row Table** → works naturally; no special case.
- **Column labels with HTML-sensitive characters** (`<`, `>`, `&`,
  `"`, `'`) → escape via `html.escape(s, quote=True)` before insertion.
- **Format strings producing HTML-sensitive characters in cell values**
  → same escaping.
- **Text vs attribute escaping** — use the right `html.escape` form
  per context:
  - **Text contexts** (`<caption>`, `<title>`, `<th>`/`<td>` body,
    cell display text, footnote/source text): `html.escape(s)` (or
    equivalently `html.escape(s, quote=False)`).
  - **Attribute contexts** (`data-value`, any future `title=`
    tooltip, `aria-*`): `html.escape(s, quote=True)`. The `quote=True`
    flag is the operative bit — without it, an embedded `"` is left
    unescaped and any user-supplied string can break attribute
    quoting.
- **`data-value` for NaN / inf** → only emit `data-value` for finite
  floats; skip the attribute for NaN/inf cells (semantically meaningless).
  Cells should already be flagged via `MissingReason` upstream.
- **Very wide tables (15+ cols)** → emit unmodified; document that
  users may wish to wrap in `<div style="overflow-x: auto">` themselves.
  No automatic wrapper in v0.1.
- **`to_html(path)` for very large output** → write directly to file,
  don't materialize a giant string in memory if avoidable. v0.1 uses
  a single string and writes it; large-output streaming is v0.2.

## Recommended decisions

1. **Fragment mode is the default**; standalone mode for `.to_html(path)`.
   Notebooks need fragments; file output needs standalone documents.
   **Confidence: high.**
2. **Inline styles in fragments, embedded `<style>` in standalone.**
   Inline avoids notebook CSS bleed; embedded keeps standalone files
   self-contained. No external CSS in v0.1. **Confidence: high.**
3. **Single column for row labels with indentation, not `rowspan`
   nesting.** Matches text renderer; renderer model is the same.
   `rowspan`-based nesting can ship in v0.2 if a real need surfaces.
   **Confidence: medium — open question.**
4. **MissingReason display matches the text renderer exactly.** Cross-
   renderer consistency. **Confidence: high.**
5. **Numeric cells carry `data-value` per the TABLE_MODEL HTML renderer
   obligation.** Cheap, future-proofs downstream consumers.
   **Confidence: high.**
6. **No background colors in v0.1.** Color decisions invite theming
   debates; borders + bold/italic emphasis are sufficient for
   executive-ready output. **Confidence: high.**
7. **HTML escaping via `html.escape(s, quote=True)` on all
   user-supplied text** (category values, labels, titles, footnotes,
   formatted cell text). Prevents content injection.
   **Confidence: high.**
8. **`Table.to_html()` always writes standalone**; the fragment is
   only via `_repr_html_` or `render_html(table, standalone=False)`.
   Simpler API surface for the user-facing method.
   **Confidence: medium — open question 2.**

## Open questions

1. **Row labels: indented single column vs. `rowspan` nested headers?**
   Indented matches text renderer and is simpler. `rowspan` is more
   semantically correct HTML. Recommend: **indented in v0.1; add
   `rowspan` mode in v0.2 as an option.**
2. ~~Should `Table.to_html()` support both modes?~~ Resolved:
   `to_html()` is **standalone-only** (single contract). Fragment
   access via `_repr_html_()` or `render_html(table, standalone=False)`.
   See [Output modes](#output-modes) and [Renderer entry points](#renderer-entry-points).
3. ~~CSS-class naming convention~~ Resolved: use `legible-` prefix
   uniformly (`legible-cell`, `legible-total`, etc.) in v0.1. Even with
   `class="legible"` on the table root, bare names like `data` or
   `total` are too collision-prone in embedded contexts. See
   [HTML structure](#html-structure).
4. ~~Group-header rows for interior row-tree nodes~~ Resolved: two
   explicit cells per group-header row — `<th scope="rowgroup">{label}</th>`
   plus `<td colspan="{n_body_cols}" class="legible-group-pad"></td>`.
   Preserves column geometry; better for alignment, testing, and
   downstream parsing than a bare-`<th>` row. See
   [Row labels and group-header rows](#row-labels-and-group-header-rows).
5. ~~What does `Table.to_html()` return when `path` is given?~~
   Resolved: `to_html(path=None) -> str`, `to_html(path=...) -> None`
   (matches `pandas.DataFrame.to_csv()` convention). See
   [Renderer entry points](#renderer-entry-points).

## Implementation tickets (proposed)

Each is one well-bounded coding session. Migrate to ROADMAP after
this memo locks.

1. **H1.** Module skeleton + format-resolution helper. Create
   `src/legible/render/html.py` with `render_html(table, *,
   standalone=False) -> str` returning a stub `<table></table>` for
   now. Also implement the per-cell format resolver (explicit
   `formats[j]` → value_kind default → `{:g}` fallback per
   [Format resolution](#format-resolution)) — needed by H2/H3 and
   easy to test independently.
2. **H2.** Column header rendering. One `<tr>` per col-axis dim
   depth. Each interior node becomes `<th colspan="node.span"
   scope="colgroup">`; innermost leaves use `scope="col"`. Top-left
   corner gets `<th rowspan="n_header_rows" class="legible-corner"
   aria-hidden="true">` (no `scope=`). All classes use the `legible-`
   prefix per role.
3. **H3.** Body rendering — single ticket combining row-tree
   pre-order traversal AND per-cell emission. Pre-orders the row
   tree; interior nodes emit a two-cell group-header `<tr>` (label
   `<th scope="rowgroup">` + colspan-padding `<td>`); leaves emit
   the full data `<tr>` with the row-label `<th scope="row">` plus
   one `<td>` per col leaf. Cells dispatch on `MissingReason`,
   apply the format resolver, escape via `html.escape`, and emit
   `data-value="{format(float(v), '.17g')}"` for finite-PRESENT
   numerics. Skip `data-value` for non-finite PRESENT or missing
   cells.
4. **H4.** Caption + tfoot. Emit `<caption class="legible-caption">`
   from `table.meta.get("title")`; emit `<tfoot>` with one
   `<tr class="legible-source">` per `source` and one
   `<tr class="legible-footnote">` per `footnote`. Omit `<caption>`
   and `<tfoot>` entirely when those keys are absent. HTML-escape
   all values.
5. **H5.** Default styling. Embedded `<style>` block for standalone
   mode (font, alignment, borders, total/subtotal emphasis, prefix-
   scoped selectors like `.legible-cell`, `.legible-total`, etc.).
   Inline equivalents for fragment mode (small inline-style
   dictionary applied per element).
6. **H6.** Standalone wrapper: `<!DOCTYPE>` + `<head>` (charset,
   `<title>` from `table.meta.get("title")`, embedded style) +
   `<body>` containing the fragment.
7. **H7.** Wire `Table._repr_html_()` (always fragment) and
   `Table.to_html(path=None)` (always standalone) to `render_html`.
   Lazy-import to avoid circular dependencies (same pattern as
   `Table.to_text`). Confirm the `to_html(path=None) → str` /
   `to_html(path="…") → None` contract.
8. **H8.** Tests. Parse output with `html.parser` or `xml.etree`
   rather than substring-matching, so structural errors (malformed
   row, bad span, missing escape, duplicate header) surface
   immediately. Assertions: `<table>` root, expected `<thead>` /
   `<tbody>` / `<tfoot>` shape, correct `colspan` / `rowspan` /
   `scope` per header, `legible-` class hierarchy per role,
   `data-value` present on finite-PRESENT and absent on missing-or-
   non-finite, MissingReason display text matching the table.
   Integration tests render the existing `examples.py` fixtures and
   parse the result. Edge cases: empty Table, HTML-sensitive
   content (`<`, `&`, `"`, `'` in category labels / titles /
   footnotes), missing-reason variants, non-finite PRESENT cell.

## Out of scope (this memo)

- Excel renderer — separate memo (`EXCEL_RENDERER.md`).
- DataFrame export — Table-level concern, separate.
- PDF rendering — v0.2+.
- Markdown / LaTeX renderers — v0.2+.
- Interactive HTML — v0.2+.
- Renderer model changes — none needed; the existing
  [TABLE_MODEL.md#renderer-contract](TABLE_MODEL.md#renderer-contract)
  contract is exactly what this renderer consumes.
