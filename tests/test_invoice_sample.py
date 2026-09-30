"""Manual sample generator for the 80mm thermal receipt PDF.

Run from the app/ directory:
    python tests/test_invoice_sample.py
Creates:
    invoices/SAMPLE-001.pdf  (single item, minimal data)
    invoices/SAMPLE-002.pdf  (60 items, full customer data -> long roll)
    invoices/SAMPLE-003.pdf  (object-style lines, discounts/tax/partial pay)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.invoice import amount_in_words, generate_invoice_pdf  # noqa: E402


def sample_single_item() -> Path:
    out = Path("invoices/SAMPLE-001.pdf")
    generate_invoice_pdf(
        "SAMPLE-001",
        [{"name": "Basmati Rice 5kg Bag", "qty": 1, "unit_type": "piece",
          "unit_price": 2450.0, "total": 2450.0}],
        out,
        customer={"name": "Ahmed Traders"},
        subtotal=2450.0,
        tax_percent=17,
        username="admin",
        payment_method="Cash",
    )
    return out


def sample_multi_page() -> Path:
    out = Path("invoices/SAMPLE-002.pdf")
    lines = [
        {
            "name": f"Product {i:03d}",
            "sku": f"SKU-{i:04d}",
            "description": ("Long description that should wrap nicely inside "
                            "the table cell without breaking the layout " * (i % 2 + 1))[:90],
            "qty": 1.5 if i % 3 == 0 else i % 10 + 1,
            "unit_type": "kg" if i % 3 == 0 else "piece",
            "unit_price": 125.5 * (i % 7 + 1),
            "total": (1.5 if i % 3 == 0 else i % 10 + 1) * 125.5 * (i % 7 + 1),
        }
        for i in range(1, 61)
    ]
    subtotal = sum(l["total"] for l in lines)
    discount = subtotal * 0.05
    tax = (subtotal - discount) * 0.17
    generate_invoice_pdf(
        "SAMPLE-002",
        lines,
        out,
        customer={"name": "Kasur Wholesale Mart", "address": "Shop 12, Main Bazaar, Kasur",
                  "phone": "0300-1234567", "email": "sales@kwmart.pk", "tax_id": "NTN 1234567-8"},
        subtotal=subtotal,
        discount_amount=discount,
        discount_type="Percentage",
        discount_value=5,
        tax_percent=17,
        tax_amount=tax,
        username="admin",
        payment_method="Online",
        payment_account="Meezan Bank",
        invoice_date=datetime.now(),
        due_date=datetime.now() + timedelta(days=15),
        shipping=500.0,
        amount_paid=10000.0,
        notes="Goods once sold will only be exchanged within 7 days with receipt.",
    )
    return out


class _ObjLine:
    """Simulates an ORM/object-style invoice line."""

    def __init__(self, name, quantity, unit_price):
        self.product_name = name
        self.quantity = quantity
        self.unit_price = unit_price
        self.unit_type = "piece"


def sample_object_lines() -> Path:
    out = Path("invoices/SAMPLE-003.pdf")
    lines = [_ObjLine("Sugar 1kg", 3, 145.0), _ObjLine("Cooking Oil 1L", 2, 540.0)]
    generate_invoice_pdf(
        "SAMPLE-003",
        lines,
        out,
        customer={},  # empty customer -> "Walk-in Customer"
        discount_type="Fixed",
        discount_value=100,
        tax_percent=0,
        amount_paid=500.0,
        status="Partially Paid",
    )
    return out


if __name__ == "__main__":
    print("amount_in_words(1234567.89) =", amount_in_words(1234567.89))
    for path in (sample_single_item(), sample_multi_page(), sample_object_lines()):
        print("Generated:", path.resolve())
