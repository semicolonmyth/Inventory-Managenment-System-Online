"""Unit tests for utils.units - the real pricing/stock math the app uses."""

import pytest

from utils import units


@pytest.mark.unit
class TestConversions:
    @pytest.mark.parametrize(
        "grams,expected", [(0, 0.0), (1000, 1.0), (250, 0.25), (1500, 1.5)]
    )
    def test_grams_to_kg(self, grams, expected):
        assert units.grams_to_kg(grams) == pytest.approx(expected)

    def test_kg_to_grams(self):
        assert units.kg_to_grams(1.5) == pytest.approx(1500.0)

    def test_roundtrip(self):
        assert units.kg_to_grams(units.grams_to_kg(321)) == pytest.approx(321.0)


@pytest.mark.unit
class TestNormalizeToKg:
    def test_grams_normalized(self):
        assert units.normalize_to_kg(500, "g") == pytest.approx(0.5)

    def test_kg_unchanged(self):
        assert units.normalize_to_kg(2.0, "kg") == pytest.approx(2.0)

    def test_piece_unchanged(self):
        # Pieces must NOT be converted
        assert units.normalize_to_kg(7, "piece") == pytest.approx(7.0)


@pytest.mark.unit
class TestCalculatePrice:
    def test_per_piece(self):
        assert units.calculate_price(3, "piece", 100) == pytest.approx(300.0)

    def test_per_kg(self):
        assert units.calculate_price(1.5, "kg", 200) == pytest.approx(300.0)

    def test_grams_priced_per_kg(self):
        # 500 g at 200/kg -> 0.5 * 200 = 100
        assert units.calculate_price(500, "g", 200) == pytest.approx(100.0)

    def test_zero_price(self):
        assert units.calculate_price(10, "piece", 0) == pytest.approx(0.0)

    def test_zero_quantity(self):
        assert units.calculate_price(0, "kg", 250) == pytest.approx(0.0)

    def test_negative_quantity_is_not_guarded(self):
        # Documents current behavior: negative qty yields negative price.
        # UI validation should prevent this; flagged in the audit.
        assert units.calculate_price(-2, "piece", 100) == pytest.approx(-200.0)


@pytest.mark.unit
class TestFormatQuantity:
    def test_single_piece_no_plural(self):
        assert units.format_quantity(1, "piece") == "1 piece"

    def test_multiple_pieces_plural(self):
        assert units.format_quantity(3, "piece") == "3 pieces"

    def test_fractional_pieces(self):
        assert units.format_quantity(2.5, "piece") == "2.50 pieces"

    def test_kg_three_decimals(self):
        assert units.format_quantity(1.5, "kg") == "1.500 kg"

    def test_grams_below_kilo(self):
        assert units.format_quantity(250, "g") == "250g"

    def test_grams_at_or_above_kilo_becomes_kg(self):
        assert units.format_quantity(1500, "g") == "1.500 kg"

    def test_unknown_unit_falls_back(self):
        assert units.format_quantity(2, "liter") == "2.000"
