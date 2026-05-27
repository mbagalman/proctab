"""Tests for the HTML renderer module skeleton + format resolver (H1).

Contract source: docs/HTML_RENDERER.md#format-resolution.
"""

from __future__ import annotations

import numpy as np
import pytest

from proctab.examples import example_1_one_way_freq
from proctab.render.html import _resolve_format, render_html


class TestResolveFormatExplicit:
    """Explicit `formats[j]` always wins (priority 1)."""

    def test_explicit_wins_over_kind_default(self):
        # currency default would render "$42.00"; explicit "{:.0f}" wins.
        assert _resolve_format(42.0, "{:.0f}", "currency") == "42"

    def test_explicit_percent_format(self):
        assert _resolve_format(0.42, "{:.2%}", "raw") == "42.00%"

    def test_explicit_overrides_count_default(self):
        assert _resolve_format(1234.0, "{:.0f}", "count") == "1234"


class TestResolveFormatKindDefaults:
    """Each ValueKind has a renderer-local default (priority 2)."""

    def test_count_with_float_value_uses_comma_zero_f(self):
        # body is np.float64 in practice; count values arrive as floats.
        assert _resolve_format(1234.0, None, "count") == "1,234"

    def test_count_with_python_int_uses_d_spec(self):
        # Hand-built Tables may carry true ints.
        assert _resolve_format(1234, None, "count") == "1,234"

    def test_count_with_numpy_int(self):
        assert _resolve_format(np.int64(1234), None, "count") == "1,234"

    def test_count_with_numpy_float(self):
        assert _resolve_format(np.float64(1234.0), None, "count") == "1,234"

    def test_currency_default(self):
        assert _resolve_format(1234.5, None, "currency") == "$1,234.50"

    def test_percent_default_assumes_0_to_1_scale(self):
        # Memo: percent default assumes 0-1; 0.42 → "42.0%".
        assert _resolve_format(0.42, None, "percent") == "42.0%"

    def test_percent_default_at_one(self):
        assert _resolve_format(1.0, None, "percent") == "100.0%"

    def test_ratio_default(self):
        assert _resolve_format(0.12345, None, "ratio") == "0.123"

    def test_sum_default(self):
        assert _resolve_format(1234567.89, None, "sum") == "1,234,568"

    def test_mean_default(self):
        assert _resolve_format(42.567, None, "mean") == "42.57"

    def test_weighted_mean_default(self):
        assert _resolve_format(42.567, None, "weighted_mean") == "42.57"

    def test_median_default(self):
        assert _resolve_format(42.567, None, "median") == "42.57"

    def test_raw_default_uses_g_format(self):
        # {:g} drops trailing zeros, switches to scientific past 6 digits.
        assert _resolve_format(42.5, None, "raw") == "42.5"


class TestResolveFormatFallback:
    """Unknown / unexpected value_kind values fall back to '{:g}' (priority 3)."""

    def test_unknown_kind_falls_back_to_g(self):
        # The ValueKind Literal blocks this at type-check time; the
        # renderer is defensive about runtime values regardless.
        result = _resolve_format(42.5, None, "totally_made_up_kind")  # type: ignore[arg-type]
        assert result == "42.5"

    def test_unknown_kind_with_integer(self):
        result = _resolve_format(42, None, "totally_made_up_kind")  # type: ignore[arg-type]
        assert result == "42"


class TestRenderHtmlStub:
    """H1 stub returns a minimal table tag. Real content arrives in H2-H6."""

    def test_returns_string(self):
        out = render_html(example_1_one_way_freq())
        assert isinstance(out, str)

    def test_contains_proctab_root_class(self):
        out = render_html(example_1_one_way_freq())
        assert 'class="proctab"' in out

    def test_fragment_mode_default_has_no_doctype(self):
        out = render_html(example_1_one_way_freq())
        assert "<!DOCTYPE" not in out
        assert "<html" not in out

    def test_standalone_param_accepted_without_error(self):
        # Standalone wrapping is H6; for now it just must not raise.
        # We're not asserting on the standalone output shape yet.
        render_html(example_1_one_way_freq(), standalone=True)
        render_html(example_1_one_way_freq(), standalone=False)

    def test_render_html_importable_from_proctab_render(self):
        from proctab.render import render_html as r
        assert r is render_html

    def test_render_html_importable_from_top_level(self):
        import proctab
        assert hasattr(proctab, "render_html")
