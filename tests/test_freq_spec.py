"""Tests for FreqSpec (F1) and _parse_freq_args (F2)."""

from __future__ import annotations

import pytest

from legible.freq import FreqSpec, _parse_freq_args


class TestFreqSpec:
    def test_minimal_construction(self):
        spec = FreqSpec(keys=("region",))
        assert spec.keys == ("region",)
        assert spec.totals is True
        assert spec.observed is True
        assert spec.dropna is False
        assert spec.levels is None
        assert spec.label is None

    def test_full_construction(self):
        spec = FreqSpec(
            keys=("region", "product"),
            totals=False,
            observed=False,
            dropna=True,
            levels={"region": ["W", "E"]},
            label={"region": "Sales Region"},
        )
        assert spec.keys == ("region", "product")
        assert spec.totals is False
        assert spec.observed is False
        assert spec.dropna is True
        assert spec.levels == {"region": ["W", "E"]}
        assert spec.label == {"region": "Sales Region"}

    def test_frozen(self):
        spec = FreqSpec(keys=("region",))
        with pytest.raises(Exception):
            spec.totals = False  # type: ignore[misc]


class TestParseKeyForms:
    def test_single_positional_string(self):
        spec = _parse_freq_args("region")
        assert spec.keys == ("region",)

    def test_two_positional_strings(self):
        spec = _parse_freq_args("region", "product_line")
        assert spec.keys == ("region", "product_line")

    def test_single_string_in_list(self):
        spec = _parse_freq_args(["region"])
        assert spec.keys == ("region",)

    def test_two_strings_in_list(self):
        spec = _parse_freq_args(["region", "product_line"])
        assert spec.keys == ("region", "product_line")

    def test_two_strings_in_tuple(self):
        spec = _parse_freq_args(("region", "product_line"))
        assert spec.keys == ("region", "product_line")


class TestParseKeyErrors:
    def test_no_keys_raises(self):
        with pytest.raises(ValueError, match="at least one grouping column"):
            _parse_freq_args()

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="at least one grouping column"):
            _parse_freq_args([])

    def test_mixed_list_then_string_raises(self):
        with pytest.raises(TypeError, match="mixed positional and list"):
            _parse_freq_args(["region"], "product_line")

    def test_mixed_string_then_list_raises(self):
        with pytest.raises(TypeError, match="mixed positional and list"):
            _parse_freq_args("region", ["product_line"])

    def test_three_positional_keys_raises(self):
        with pytest.raises(ValueError, match="one- or two-way"):
            _parse_freq_args("a", "b", "c")

    def test_three_keys_in_list_raises(self):
        with pytest.raises(ValueError, match="one- or two-way"):
            _parse_freq_args(["a", "b", "c"])

    def test_duplicate_positional_keys_raises(self):
        with pytest.raises(ValueError, match="unique"):
            _parse_freq_args("region", "region")

    def test_duplicate_list_keys_raises(self):
        with pytest.raises(ValueError, match="unique"):
            _parse_freq_args(["region", "region"])

    def test_empty_string_positional_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            _parse_freq_args("")

    def test_empty_string_in_list_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            _parse_freq_args(["region", ""])

    def test_non_string_positional_raises(self):
        with pytest.raises(TypeError):
            _parse_freq_args(42)

    def test_non_string_in_list_raises(self):
        with pytest.raises(TypeError, match="strings"):
            _parse_freq_args(["region", 42])

    def test_non_string_among_positional_raises(self):
        with pytest.raises(TypeError, match="mixed positional and list"):
            _parse_freq_args("region", 42)


class TestParseKwargDefaults:
    def test_defaults_match_dataclass(self):
        spec = _parse_freq_args("region")
        assert spec.totals is True
        assert spec.observed is True
        assert spec.dropna is False
        assert spec.levels is None
        assert spec.label is None

    def test_explicit_kwargs_pass_through(self):
        spec = _parse_freq_args(
            "region", "product",
            totals=False, observed=False, dropna=True,
            levels={"region": ["W", "E"]},
            label={"product": "Product Line"},
        )
        assert spec.totals is False
        assert spec.observed is False
        assert spec.dropna is True
        assert spec.levels == {"region": ["W", "E"]}
        assert spec.label == {"product": "Product Line"}


class TestParseLevelsValidation:
    def test_levels_subset_of_keys_ok(self):
        _parse_freq_args("region", "product",
                         levels={"region": ["W", "E"]})

    def test_levels_full_overlap_ok(self):
        _parse_freq_args("region", "product",
                         levels={"region": ["W"], "product": ["A"]})

    def test_levels_with_unknown_key_raises(self):
        with pytest.raises(ValueError, match="levels="):
            _parse_freq_args("region",
                             levels={"channel": ["online", "offline"]})

    def test_levels_with_non_sequence_value_raises(self):
        with pytest.raises(TypeError, match="list or tuple"):
            _parse_freq_args("region", levels={"region": "W"})

    def test_levels_with_dict_value_raises(self):
        with pytest.raises(TypeError, match="list or tuple"):
            _parse_freq_args("region", levels={"region": {"W": 1}})

    def test_levels_with_tuple_value_ok(self):
        _parse_freq_args("region", levels={"region": ("W", "E")})

    def test_empty_levels_dict_ok(self):
        spec = _parse_freq_args("region", levels={})
        assert spec.levels == {}


class TestParseLabelValidation:
    def test_label_subset_of_keys_ok(self):
        _parse_freq_args("region", label={"region": "Sales Region"})

    def test_label_with_unknown_key_raises(self):
        with pytest.raises(ValueError, match="label="):
            _parse_freq_args("region", label={"channel": "Channel"})

    def test_empty_label_dict_ok(self):
        spec = _parse_freq_args("region", label={})
        assert spec.label == {}


class TestParseReservedKwargs:
    def test_weight_raises_notimplemented(self):
        with pytest.raises(NotImplementedError):
            _parse_freq_args("region", weight="population")

    def test_weight_error_mentions_v02(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_freq_args("region", weight="population")

    def test_test_raises_notimplemented(self):
        with pytest.raises(NotImplementedError):
            _parse_freq_args("region", "product", test="chi2")

    def test_test_error_mentions_v02(self):
        with pytest.raises(NotImplementedError, match="v0.2"):
            _parse_freq_args("region", "product", test="chi2")

    def test_reserved_kwargs_checked_before_keys(self):
        """Reserved kwargs should raise even if keys are also invalid."""
        with pytest.raises(NotImplementedError):
            _parse_freq_args("a", "b", "c", weight="w")
