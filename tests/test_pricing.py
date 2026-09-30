"""Unit tests for the shared pricing module (utils.pricing).

These are the canonical discount/tax/total/status rules now used by both the
receipt renderer and the billing UI. They mirror the cases the old inline
logic handled so the extraction is proven behavior-preserving.
"""

import pytest

from utils.pricing import compute_totals, derive_status, to_float


@pytest.mark.unit
class TestToFloat:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, 0.0), ("", 0.0), ("12.5", 12.5), ("1,200", 1200.0),
         (5, 5.0), ("bad", 0.0), (2.5, 2.5)],
    )
    def test_conversions(self, value, expected):
        assert to_float(value) == pytest.approx(expected)


@pytest.mark.unit
class TestComputeTotals:
    def test_plain_subtotal_no_adjustments(self):
        t = compute_totals(100)
        assert t["discount_amount"] == 0.0
        assert t["tax_amount"] == 0.0
        assert t["grand_total"] == pytest.approx(100.0)
        assert t["status"] == "Unpaid"

    def test_percentage_discount(self):
        t = compute_totals(200, discount_type="Percentage", discount_value=10)
        assert t["discount_amount"] == pytest.approx(20.0)
        assert t["grand_total"] == pytest.approx(180.0)

    def test_fixed_discount_capped_at_subtotal(self):
        t = compute_totals(50, discount_type="Fixed", discount_value=999)
        assert t["discount_amount"] == pytest.approx(50.0)
        assert t["grand_total"] == pytest.approx(0.0)

    def test_explicit_discount_amount_wins_over_type(self):
        t = compute_totals(
            100, discount_amount=15, discount_type="Percentage", discount_value=50
        )
        assert t["discount_amount"] == pytest.approx(15.0)

    def test_tax_applied_after_discount(self):
        t = compute_totals(
            100, discount_type="Fixed", discount_value=20, tax_percent=10
        )
        # 100 - 20 = 80; tax 10% of 80 = 8; grand = 88
        assert t["tax_amount"] == pytest.approx(8.0)
        assert t["grand_total"] == pytest.approx(88.0)

    def test_shipping_added_after_tax(self):
        t = compute_totals(100, tax_percent=10, shipping=5)
        assert t["grand_total"] == pytest.approx(115.0)

    def test_explicit_tax_amount_wins_over_percent(self):
        t = compute_totals(100, tax_amount=7.5, tax_percent=50)
        assert t["tax_amount"] == pytest.approx(7.5)

    def test_status_balance_due_partial(self):
        t = compute_totals(100, amount_paid=40)
        assert t["status"] == "Partially Paid"
        assert t["balance_due"] == pytest.approx(60.0)

    def test_status_paid_when_full(self):
        t = compute_totals(100, amount_paid=100)
        assert t["status"] == "Paid"
        assert t["balance_due"] == pytest.approx(0.0)

    def test_status_override_preserved(self):
        t = compute_totals(100, amount_paid=0, status="Refunded")
        assert t["status"] == "Refunded"

    def test_negative_discount_clamped_to_zero(self):
        t = compute_totals(100, discount_amount=-30)
        assert t["discount_amount"] == 0.0


@pytest.mark.unit
class TestDeriveStatus:
    def test_none_paid_is_unpaid(self):
        assert derive_status(100, None) == "Unpaid"

    def test_zero_paid_is_unpaid(self):
        assert derive_status(100, 0) == "Unpaid"

    def test_rounding_tolerance_marks_paid(self):
        # paid within 0.005 of total still counts as fully paid.
        assert derive_status(100, 99.997) == "Paid"
