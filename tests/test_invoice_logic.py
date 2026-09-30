"""Unit tests for the invoice/receipt business math and formatting.

These target the real, importable logic in utils.invoice:
* fmt_money / _to_float / _clean (formatting + graceful empty handling)
* amount_in_words (Pakistani lakh/crore numbering)
* _build_context (discount, tax-after-discount, shipping, totals,
  balance due and payment-status derivation) -- the same math the app
  uses when producing a PDF.
"""

import pytest

from utils import invoice as inv


def _ctx(**overrides):
    """Call the private context builder with safe defaults for every arg."""
    args = dict(
        invoice_number="INV-1",
        lines=[],
        customer=None,
        subtotal=None,
        discount_amount=None,
        discount_type="Percentage",
        discount_value=None,
        tax_percent=None,
        tax_amount=None,
        username=None,
        payment_method="Cash",
        payment_account=None,
        invoice_date=None,
        due_date=None,
        due_days=0,
        shipping=0.0,
        amount_paid=None,
        status=None,
        notes=None,
    )
    args.update(overrides)
    return inv._build_context(**args)


@pytest.mark.unit
class TestMoney:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (1234.5, "1,234.50"),
            (0, "0.00"),
            (None, "0.00"),
            (1234567.891, "1,234,567.89"),
            (1000000, "1,000,000.00"),
        ],
    )
    def test_fmt_money(self, value, expected):
        assert inv.fmt_money(value) == expected


@pytest.mark.unit
class TestToFloat:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, 0.0), ("", 0.0), ("abc", 0.0), ("3.5", 3.5), (5, 5.0), (2.5, 2.5)],
    )
    def test_safe_conversion(self, value, expected):
        assert inv._to_float(value) == pytest.approx(expected)


@pytest.mark.unit
class TestClean:
    def test_none_becomes_empty(self):
        assert inv._clean(None) == ""

    def test_accented_latin_survives(self):
        assert inv._clean("café") == "caf\xe9"

    def test_non_latin_is_replaced_not_crashing(self):
        # fpdf core fonts are latin-1; emoji must degrade to a placeholder.
        out = inv._clean("rocket: 🔥")
        assert "rocket" in out
        assert "\U0001F525" not in out


@pytest.mark.unit
class TestAmountInWords:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (1, "One Rupees Only"),
            (15, "Fifteen Rupees Only"),
            (100, "One Hundred Rupees Only"),
            (1234, "One Thousand Two Hundred Thirty Four Rupees Only"),
            (100000, "One Lakh Rupees Only"),
            (1250000, "Twelve Lakh Fifty Thousand Rupees Only"),
            (10000000, "One Crore Rupees Only"),
        ],
    )
    def test_values(self, value, expected):
        assert inv.amount_in_words(value) == expected

    def test_paisa_included(self):
        assert inv.amount_in_words(0.50) == "Zero Rupees and Fifty Paisa Only"

    def test_negative_returns_empty(self):
        assert inv.amount_in_words(-5) == ""


@pytest.mark.unit
class TestTotalsContext:
    def test_percentage_discount(self):
        ctx = _ctx(
            lines=[{"name": "A", "qty": 2, "unit_price": 100, "total": 200}],
            discount_type="Percentage", discount_value=10,
        )
        assert ctx["subtotal"] == pytest.approx(200.0)
        assert ctx["discount_amount"] == pytest.approx(20.0)
        assert ctx["grand_total"] == pytest.approx(180.0)
        assert ctx["status"] == "Unpaid"

    def test_fixed_discount_capped_at_subtotal(self):
        ctx = _ctx(
            lines=[{"name": "A", "qty": 1, "unit_price": 50, "total": 50}],
            discount_type="Fixed", discount_value=100,
        )
        assert ctx["discount_amount"] == pytest.approx(50.0)
        assert ctx["grand_total"] == pytest.approx(0.0)

    def test_tax_applied_after_discount_plus_shipping(self):
        ctx = _ctx(
            subtotal=1000.0,
            discount_amount=100.0,
            tax_percent=5,
            shipping=50.0,
            amount_paid=500.0,
        )
        # 1000 - 100 = 900; tax 5% = 45; + shipping 50 => 995
        assert ctx["tax_amount"] == pytest.approx(45.0)
        assert ctx["grand_total"] == pytest.approx(995.0)
        assert ctx["balance_due"] == pytest.approx(495.0)
        assert ctx["status"] == "Partially Paid"

    def test_full_payment_marks_paid(self):
        ctx = _ctx(subtotal=100.0, amount_paid=100.0)
        assert ctx["grand_total"] == pytest.approx(100.0)
        assert ctx["status"] == "Paid"
        assert ctx["balance_due"] == pytest.approx(0.0)

    def test_empty_lines(self):
        ctx = _ctx(lines=[])
        assert ctx["subtotal"] == pytest.approx(0.0)
        assert ctx["rows"] == []
        assert ctx["grand_total"] == pytest.approx(0.0)

    def test_object_style_lines_are_supported(self):
        class Line:
            product_name = "Rice"
            quantity = 2
            unit_price = 250
            unit_type = "piece"

        ctx = _ctx(lines=[Line()])
        assert ctx["rows"][0]["name"] == "Rice"
        assert ctx["subtotal"] == pytest.approx(500.0)

    def test_no_none_leaks_in_rendered_strings(self):
        ctx = _ctx(
            lines=[{"name": None, "qty": None, "unit_price": None}],
            customer=None,
        )
        # A missing name must degrade to "Item", never the literal "None".
        assert ctx["rows"][0]["name"] != "None"
        assert ctx["username"] == ""
        assert ctx["payment_method"] == "Cash"
