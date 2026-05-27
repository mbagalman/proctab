"""Tests for TabSpec (T1) and _parse_tabulate_args (T2)."""

from __future__ import annotations

import pytest

from legible.tabulate import (
    SUPPORTED_STATS,
    TabSpec,
    _parse_tabulate_args,
)


class TestTabSpec:
    def test_minimal_construction(self):
        spec = TabSpec(rows=("region",), values_spec=(("revenue", "sum"),))
        assert spec.rows == ("region",)
        assert spec.cols == ()
        assert spec.values_spec == (("revenue", "sum"),)
        assert spec.subtotals == ()
        assert spec.totals is True
        assert spec.observed is True
        assert spec.dropna is False
        assert spec.levels is None
        assert spec.label is None

    def test_full_construction(self):
        spec = TabSpec(
            rows=("region", "product"),
            cols=("quarter",),
            values_spec=(("revenue", "sum"), ("revenue", "mean")),
            subtotals=("region",),
            totals=False,
            observed=False,
            dropna=True,
            levels={"region": ["W", "E"]},
            label={"region": "Sales Region"},
        )
        assert spec.cols == ("quarter",)
        assert spec.subtotals == ("region",)
        assert spec.observed is False

    def test_frozen(self):
        spec = TabSpec(rows=("x",), values_spec=(("y", "sum"),))
        with pytest.raises(Exception):
            spec.totals = False  # type: ignore[misc]


class TestParseRowsCols:
    def test_rows_as_string(self):
        spec = _parse_tabulate_args(rows="region", values={"r": "sum"})
        assert spec.rows == ("region",)

    def test_rows_as_list(self):
        spec = _parse_tabulate_args(rows=["region", "product"],
                                     values={"r": "sum"})
        assert spec.rows == ("region", "product")

    def test_rows_as_tuple(self):
        spec = _parse_tabulate_args(rows=("region", "product"),
                                     values={"r": "sum"})
        assert spec.rows == ("region", "product")

    def test_cols_default_empty(self):
        spec = _parse_tabulate_args(rows="region", values={"r": "sum"})
        assert spec.cols == ()

    def test_cols_as_string(self):
        spec = _parse_tabulate_args(rows="region", cols="quarter",
                                     values={"r": "sum"})
        assert spec.cols == ("quarter",)

    def test_cols_as_list(self):
        spec = _parse_tabulate_args(rows="region", cols=["quarter"],
                                     values={"r": "sum"})
        assert spec.cols == ("quarter",)


class TestParseRowsColsErrors:
    def test_empty_rows_raises(self):
        with pytest.raises(ValueError, match="at least 1 rows"):
            _parse_tabulate_args(rows=[], values={"r": "sum"})

    def test_three_rows_raises_v01_cap(self):
        with pytest.raises(ValueError, match="at most 2 rows"):
            _parse_tabulate_args(rows=["a", "b", "c"], values={"r": "sum"})

    def test_two_cols_raises_v01_cap(self):
        with pytest.raises(ValueError, match="at most 1 cols"):
            _parse_tabulate_args(rows="region", cols=["a", "b"],
                                  values={"r": "sum"})

    def test_v01_cap_error_mentions_v02(self):
        with pytest.raises(ValueError, match="v0.2 will lift"):
            _parse_tabulate_args(rows=["a", "b", "c"], values={"r": "sum"})

    def test_duplicate_rows_raises(self):
        with pytest.raises(ValueError, match="unique"):
            _parse_tabulate_args(rows=["region", "region"],
                                  values={"r": "sum"})

    def test_empty_string_row_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            _parse_tabulate_args(rows="", values={"r": "sum"})

    def test_non_string_row_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(rows=["region", 42], values={"r": "sum"})

    def test_rows_as_dict_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(rows={"region": 1}, values={"r": "sum"})

    def test_rows_cols_overlap_raises(self):
        with pytest.raises(ValueError, match="cannot share dims"):
            _parse_tabulate_args(rows="region", cols="region",
                                  values={"r": "sum"})


class TestParseValues:
    def test_string_stat_shorthand(self):
        spec = _parse_tabulate_args(rows="region",
                                     values={"revenue": "sum"})
        assert spec.values_spec == (("revenue", "sum"),)

    def test_single_stat_in_list(self):
        spec = _parse_tabulate_args(rows="region",
                                     values={"revenue": ["sum"]})
        assert spec.values_spec == (("revenue", "sum"),)

    def test_multiple_stats(self):
        spec = _parse_tabulate_args(rows="region",
                                     values={"revenue": ["sum", "mean"]})
        assert spec.values_spec == (("revenue", "sum"), ("revenue", "mean"))

    def test_stat_tuple_form(self):
        spec = _parse_tabulate_args(rows="region",
                                     values={"revenue": ("sum", "mean")})
        assert spec.values_spec == (("revenue", "sum"), ("revenue", "mean"))

    def test_multiple_metrics_preserves_insertion_order(self):
        # Dict insertion order = output metric order (Python 3.7+ contract)
        spec = _parse_tabulate_args(
            rows="region",
            values={"revenue": ["sum"], "margin": ["mean"]},
        )
        assert spec.values_spec == (
            ("revenue", "sum"),
            ("margin", "mean"),
        )

    def test_all_supported_stats(self):
        spec = _parse_tabulate_args(
            rows="region",
            values={"x": ["sum", "mean", "count", "min", "max", "median"]},
        )
        stats = [stat for _, stat in spec.values_spec]
        assert set(stats) == SUPPORTED_STATS


class TestParseValuesErrors:
    def test_empty_values_dict_raises(self):
        with pytest.raises(ValueError, match="at least one metric"):
            _parse_tabulate_args(rows="region", values={})

    def test_non_mapping_values_raises(self):
        with pytest.raises(TypeError, match="mapping"):
            _parse_tabulate_args(rows="region", values=["sum"])

    def test_empty_stat_list_for_metric_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            _parse_tabulate_args(rows="region", values={"revenue": []})

    def test_unknown_stat_raises(self):
        with pytest.raises(ValueError, match="unknown stat"):
            _parse_tabulate_args(rows="region",
                                  values={"revenue": "stddev"})

    def test_unknown_stat_error_lists_supported(self):
        with pytest.raises(ValueError, match="sum"):
            _parse_tabulate_args(rows="region",
                                  values={"revenue": "stddev"})

    def test_weighted_mean_raises_notimplemented(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_tabulate_args(rows="region",
                                  values={"revenue": "weighted_mean"})

    def test_weighted_mean_in_list_also_raises(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_tabulate_args(rows="region",
                                  values={"revenue": ["sum", "weighted_mean"]})

    def test_non_string_stat_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(rows="region", values={"revenue": [42]})

    def test_non_string_metric_key_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(rows="region", values={42: "sum"})

    def test_non_str_non_list_stat_value_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(rows="region", values={"revenue": 42})

    def test_duplicate_stat_within_metric_raises(self):
        # Two identical (metric, stat) pairs would produce two col leaves
        # with identical paths — violates the positional-path invariant
        # before T5's axis construction even runs.
        with pytest.raises(ValueError, match="duplicate"):
            _parse_tabulate_args(
                rows="region",
                values={"revenue": ["sum", "sum"]},
            )

    def test_duplicate_stat_error_mentions_path_collision(self):
        with pytest.raises(ValueError, match="same path"):
            _parse_tabulate_args(
                rows="region",
                values={"revenue": ["sum", "sum"]},
            )

    def test_duplicate_stat_among_others_raises(self):
        # mean appears twice in a longer list
        with pytest.raises(ValueError, match="duplicate"):
            _parse_tabulate_args(
                rows="region",
                values={"revenue": ["sum", "mean", "max", "mean"]},
            )


class TestParseSubtotals:
    def test_none_default(self):
        spec = _parse_tabulate_args(rows="region", values={"r": "sum"})
        assert spec.subtotals == ()

    def test_single_string(self):
        spec = _parse_tabulate_args(
            rows=["region", "product"], values={"r": "sum"},
            subtotals="region",
        )
        assert spec.subtotals == ("region",)

    def test_list_form(self):
        spec = _parse_tabulate_args(
            rows=["region", "product"], values={"r": "sum"},
            subtotals=["region"],
        )
        assert spec.subtotals == ("region",)

    def test_subtotal_not_in_rows_raises(self):
        with pytest.raises(ValueError, match="not in rows"):
            _parse_tabulate_args(
                rows=["region", "product"], values={"r": "sum"},
                subtotals="channel",
            )

    def test_innermost_row_dim_subtotal_raises(self):
        with pytest.raises(ValueError, match="innermost"):
            _parse_tabulate_args(
                rows=["region", "product"], values={"r": "sum"},
                subtotals="product",
            )

    def test_innermost_subtotal_error_suggests_alternative(self):
        with pytest.raises(ValueError, match="region"):
            _parse_tabulate_args(
                rows=["region", "product"], values={"r": "sum"},
                subtotals="product",
            )

    def test_single_row_dim_innermost_subtotal_raises(self):
        # With only 1 row dim, that dim IS innermost
        with pytest.raises(ValueError, match="innermost"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                subtotals="region",
            )

    def test_non_string_subtotal_raises(self):
        with pytest.raises(TypeError):
            _parse_tabulate_args(
                rows=["region", "product"], values={"r": "sum"},
                subtotals=[42],
            )

    def test_duplicate_subtotal_names_raise(self):
        with pytest.raises(ValueError, match="unique"):
            _parse_tabulate_args(
                rows=["region", "product"], values={"r": "sum"},
                subtotals=["region", "region"],
            )


class TestParseLevelsLabel:
    def test_levels_subset_of_rows_cols_ok(self):
        _parse_tabulate_args(
            rows=["region", "product"], cols="quarter",
            values={"r": "sum"},
            levels={"region": ["W", "E"], "quarter": ["Q1"]},
        )

    def test_levels_unknown_key_raises(self):
        with pytest.raises(ValueError, match="levels="):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                levels={"channel": ["online"]},
            )

    def test_levels_non_sequence_value_raises(self):
        with pytest.raises(TypeError, match="list or tuple"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                levels={"region": "W"},
            )

    def test_duplicate_level_values_raise(self):
        # Reviewer P2 regression: duplicate level values produced
        # duplicate leaves and silently misrouted data to the last index.
        with pytest.raises(ValueError, match="duplicate"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                levels={"region": ["E", "E"]},
            )

    def test_duplicate_level_values_error_mentions_misrouting(self):
        with pytest.raises(ValueError, match="silently misrouting"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                levels={"region": ["E", "W", "E"]},
            )

    def test_label_subset_ok(self):
        _parse_tabulate_args(
            rows="region", cols="quarter",
            values={"r": "sum"},
            label={"region": "Sales Region", "quarter": "Q"},
        )

    def test_label_unknown_key_raises(self):
        with pytest.raises(ValueError, match="label="):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                label={"channel": "Channel"},
            )


class TestReservedKwargs:
    def test_weight_raises_notimplemented(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                weight={"r": "units"},
            )

    def test_test_raises_notimplemented(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_tabulate_args(
                rows="region", values={"r": "sum"},
                test="chi2",
            )

    def test_reserved_kwargs_checked_before_keys(self):
        """Reserved kwargs should raise even if other args are also invalid."""
        with pytest.raises(NotImplementedError):
            _parse_tabulate_args(
                rows=[], values={}, weight={"r": "units"},
            )


class TestKwargDefaults:
    def test_defaults_match_dataclass_defaults(self):
        spec = _parse_tabulate_args(rows="region", values={"r": "sum"})
        assert spec.cols == ()
        assert spec.subtotals == ()
        assert spec.totals is True
        assert spec.observed is True
        assert spec.dropna is False
        assert spec.levels is None
        assert spec.label is None

    def test_explicit_kwargs_pass_through(self):
        spec = _parse_tabulate_args(
            rows=["region", "product"], cols="quarter",
            values={"revenue": ["sum"]},
            subtotals="region",
            totals=False, observed=False, dropna=True,
            levels={"quarter": ["Q1", "Q2"]},
            label={"quarter": "Q"},
        )
        assert spec.totals is False
        assert spec.observed is False
        assert spec.dropna is True
        assert spec.levels == {"quarter": ["Q1", "Q2"]}
        assert spec.label == {"quarter": "Q"}
        assert spec.subtotals == ("region",)
