"""Renderer subpackage. v0.0.1 ships plain-text and HTML; the Excel
renderer is in progress (E1 skeleton landed; E2-E7 build out the full
output). Excel requires the optional `proctab[excel]` extra (openpyxl)
— `render_excel` itself is importable here even without openpyxl, and
the import inside the function gives a friendly error at call time."""

from proctab.render.excel import render_excel
from proctab.render.html import render_html
from proctab.render.text import render_text

__all__ = ["render_excel", "render_html", "render_text"]
