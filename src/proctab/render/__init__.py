"""Renderer subpackage. v0.0.1 ships the plain-text renderer; the HTML
renderer is in progress (H1 skeleton landed; H2-H7 build out the full
output)."""

from proctab.render.html import render_html
from proctab.render.text import render_text

__all__ = ["render_html", "render_text"]
